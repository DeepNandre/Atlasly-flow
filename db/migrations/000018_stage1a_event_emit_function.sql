-- Stage 1A Slice 3 migration
-- Adds deterministic event emission helper with emission-point guardrails and optional Stage 0 outbox write-through.
-- No change to shared event names/envelope fields/API contracts.

BEGIN;

CREATE OR REPLACE FUNCTION stage1a_build_event_idempotency_key(
  p_letter_id uuid,
  p_event_type text,
  p_event_version integer DEFAULT 1
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT p_letter_id::text || ':' || p_event_type || ':v' || p_event_version::text;
$$;

CREATE OR REPLACE FUNCTION stage1a_emit_event(
  p_letter_id uuid,
  p_event_type text,
  p_payload jsonb DEFAULT '{}'::jsonb,
  p_produced_by text DEFAULT 'stage1a-parser-worker',
  p_trace_id text DEFAULT NULL
)
RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
  v_letter comment_letters%ROWTYPE;
  v_event_id uuid := gen_random_uuid();
  v_event_version integer := 1;
  v_idempotency_key text;
BEGIN
  SELECT * INTO v_letter FROM comment_letters WHERE id = p_letter_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Letter % not found', p_letter_id;
  END IF;

  IF p_event_type NOT IN (
    'comment_letter.parsing_started',
    'comment_letter.extraction_completed',
    'comment_letter.approved'
  ) THEN
    RAISE EXCEPTION 'Unsupported Stage 1A event_type: %', p_event_type;
  END IF;

  -- Enforce canonical emission points.
  IF p_event_type = 'comment_letter.parsing_started'
     AND v_letter.extraction_status NOT IN ('ingest_received', 'ocr_precheck') THEN
    RAISE EXCEPTION 'Invalid parsing_started emission for status %', v_letter.extraction_status;
  END IF;

  IF p_event_type = 'comment_letter.extraction_completed'
     AND v_letter.extraction_status <> 'review_queueing' THEN
    RAISE EXCEPTION 'Invalid extraction_completed emission for status %; expected review_queueing', v_letter.extraction_status;
  END IF;

  IF p_event_type = 'comment_letter.approved'
     AND v_letter.extraction_status NOT IN ('approval_snapshot', 'completed') THEN
    RAISE EXCEPTION 'Invalid approved emission for status %', v_letter.extraction_status;
  END IF;

  v_idempotency_key := stage1a_build_event_idempotency_key(p_letter_id, p_event_type, v_event_version);

  INSERT INTO comment_letter_event_emissions (
    id,
    letter_id,
    event_type,
    event_version,
    idempotency_key,
    payload,
    emitted_at
  ) VALUES (
    v_event_id,
    p_letter_id,
    p_event_type,
    v_event_version,
    v_idempotency_key,
    p_payload,
    now()
  );

  -- Optional bridge to Stage 0 outbox, only when table exists and org is resolvable.
  IF to_regclass('public.domain_events') IS NOT NULL
     AND EXISTS (SELECT 1 FROM organizations o WHERE o.id = v_letter.organization_id) THEN
    INSERT INTO domain_events (
      id,
      organization_id,
      aggregate_type,
      aggregate_id,
      event_type,
      event_version,
      idempotency_key,
      trace_id,
      occurred_at,
      payload,
      status,
      created_at
    ) VALUES (
      gen_random_uuid(),
      v_letter.organization_id,
      'comment_letter',
      p_letter_id,
      p_event_type,
      v_event_version,
      v_idempotency_key,
      p_trace_id,
      now(),
      p_payload,
      'pending',
      now()
    ) ON CONFLICT DO NOTHING;
  END IF;

  RETURN v_event_id;
END
$$;

COMMIT;
