-- Stage 1A Slice 6 migration
-- Adds pipeline entrypoint helpers for POST /comment-letters and extraction-finalization emission.
-- No shared event/API name changes.

BEGIN;

CREATE OR REPLACE FUNCTION stage1a_create_comment_letter(
  p_organization_id uuid,
  p_project_id uuid,
  p_document_id uuid,
  p_created_by uuid,
  p_idempotency_key text,
  p_source_filename text DEFAULT NULL
)
RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
  v_letter_id uuid;
BEGIN
  IF p_idempotency_key IS NULL OR length(btrim(p_idempotency_key)) < 8 THEN
    RAISE EXCEPTION 'idempotency_key must be present and >= 8 chars';
  END IF;

  SELECT id INTO v_letter_id
  FROM comment_letters
  WHERE organization_id = p_organization_id
    AND idempotency_key = p_idempotency_key;

  IF v_letter_id IS NOT NULL THEN
    RETURN v_letter_id;
  END IF;

  INSERT INTO comment_letters (
    organization_id,
    project_id,
    document_id,
    created_by,
    extraction_status,
    source_filename,
    idempotency_key,
    started_at
  ) VALUES (
    p_organization_id,
    p_project_id,
    p_document_id,
    p_created_by,
    'ingest_received',
    p_source_filename,
    p_idempotency_key,
    now()
  ) RETURNING id INTO v_letter_id;

  BEGIN
    PERFORM stage1a_emit_event(
      v_letter_id,
      'comment_letter.parsing_started',
      jsonb_build_object(
        'letter_id', v_letter_id,
        'document_id', p_document_id,
        'started_at', now()
      ),
      'stage1a-parser-worker',
      NULL
    );
  EXCEPTION WHEN unique_violation THEN
    NULL;
  END;

  RETURN v_letter_id;
EXCEPTION WHEN unique_violation THEN
  SELECT id INTO v_letter_id
  FROM comment_letters
  WHERE organization_id = p_organization_id
    AND (
      idempotency_key = p_idempotency_key
      OR document_id = p_document_id
    )
  ORDER BY created_at ASC
  LIMIT 1;

  IF v_letter_id IS NULL THEN
    RAISE;
  END IF;

  RETURN v_letter_id;
END
$$;

CREATE OR REPLACE FUNCTION stage1a_finalize_extraction(
  p_letter_id uuid,
  p_document_id uuid,
  p_extraction_count integer,
  p_avg_confidence numeric,
  p_requires_review_count integer
)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
  v_letter comment_letters%ROWTYPE;
BEGIN
  IF p_extraction_count < 0 THEN
    RAISE EXCEPTION 'extraction_count must be >= 0';
  END IF;

  IF p_requires_review_count < 0 THEN
    RAISE EXCEPTION 'requires_review_count must be >= 0';
  END IF;

  IF p_avg_confidence < 0 OR p_avg_confidence > 1 THEN
    RAISE EXCEPTION 'avg_confidence must be in [0,1]';
  END IF;

  SELECT * INTO v_letter
  FROM comment_letters
  WHERE id = p_letter_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Letter % not found', p_letter_id;
  END IF;

  IF v_letter.document_id <> p_document_id THEN
    RAISE EXCEPTION 'Letter % document mismatch', p_letter_id;
  END IF;

  IF v_letter.extraction_status = 'normalizing_validating' THEN
    UPDATE comment_letters
    SET extraction_status = 'review_queueing',
        completed_at = now()
    WHERE id = p_letter_id;
  ELSIF v_letter.extraction_status <> 'review_queueing' THEN
    RAISE EXCEPTION 'Letter % must be in normalizing_validating or review_queueing; got %', p_letter_id, v_letter.extraction_status;
  END IF;

  BEGIN
    PERFORM stage1a_emit_event(
      p_letter_id,
      'comment_letter.extraction_completed',
      jsonb_build_object(
        'letter_id', p_letter_id,
        'document_id', p_document_id,
        'extraction_count', p_extraction_count,
        'avg_confidence', round(p_avg_confidence::numeric, 3),
        'requires_review_count', p_requires_review_count,
        'completed_at', now()
      ),
      'stage1a-parser-worker',
      NULL
    );
  EXCEPTION WHEN unique_violation THEN
    -- Idempotent retry.
    NULL;
  END;
END
$$;

COMMIT;
