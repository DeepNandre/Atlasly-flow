BEGIN;

CREATE TABLE IF NOT EXISTS webhook_dead_letters (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  subscription_id uuid NOT NULL REFERENCES webhook_subscriptions(id) ON DELETE CASCADE,
  delivery_id uuid NOT NULL REFERENCES webhook_deliveries(id) ON DELETE CASCADE,
  event_id uuid NOT NULL,
  event_name text NOT NULL,
  final_attempt integer NOT NULL,
  error_code text,
  error_detail text,
  payload jsonb NOT NULL,
  first_attempt_at timestamptz,
  dead_lettered_at timestamptz NOT NULL DEFAULT now(),
  replay_status text NOT NULL DEFAULT 'not_requested',
  replayed_at timestamptz,
  replay_job_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT webhook_dead_letters_delivery_unique UNIQUE (delivery_id),
  CONSTRAINT webhook_dead_letters_final_attempt_positive CHECK (final_attempt > 0),
  CONSTRAINT webhook_dead_letters_replay_status_chk
    CHECK (replay_status IN ('not_requested', 'queued', 'replayed', 'discarded'))
);

CREATE TABLE IF NOT EXISTS webhook_replay_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  requested_by uuid,
  replay_scope text NOT NULL,
  subscription_id uuid,
  event_id uuid,
  source_dead_letter_id uuid REFERENCES webhook_dead_letters(id) ON DELETE SET NULL,
  status text NOT NULL DEFAULT 'queued',
  reason text,
  max_deliveries integer NOT NULL DEFAULT 100,
  created_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  ended_at timestamptz,
  processed_count integer NOT NULL DEFAULT 0,
  failed_count integer NOT NULL DEFAULT 0,
  error_detail text,
  CONSTRAINT webhook_replay_jobs_scope_chk
    CHECK (replay_scope IN ('delivery', 'subscription', 'event')),
  CONSTRAINT webhook_replay_jobs_status_chk
    CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
  CONSTRAINT webhook_replay_jobs_max_deliveries_chk
    CHECK (max_deliveries > 0 AND max_deliveries <= 10000),
  CONSTRAINT webhook_replay_jobs_counts_chk
    CHECK (processed_count >= 0 AND failed_count >= 0)
);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'webhook_deliveries_status_chk'
  ) THEN
    ALTER TABLE webhook_deliveries
      ADD CONSTRAINT webhook_deliveries_status_chk
      CHECK (status IN (
        'pending',
        'retrying',
        'delivered',
        'failed_retryable',
        'failed_non_retryable',
        'dead_lettered'
      ));
  END IF;
END $$;

ALTER TABLE webhook_deliveries
  ADD COLUMN IF NOT EXISTS first_attempt_at timestamptz,
  ADD COLUMN IF NOT EXISTS last_attempt_at timestamptz,
  ADD COLUMN IF NOT EXISTS terminal_at timestamptz,
  ADD COLUMN IF NOT EXISTS max_attempts integer NOT NULL DEFAULT 7,
  ADD COLUMN IF NOT EXISTS retry_count integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS is_terminal boolean NOT NULL DEFAULT false;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'webhook_deliveries_max_attempts_chk'
  ) THEN
    ALTER TABLE webhook_deliveries
      ADD CONSTRAINT webhook_deliveries_max_attempts_chk
      CHECK (max_attempts > 0 AND max_attempts <= 20);
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'webhook_deliveries_retry_count_chk'
  ) THEN
    ALTER TABLE webhook_deliveries
      ADD CONSTRAINT webhook_deliveries_retry_count_chk
      CHECK (retry_count >= 0 AND retry_count <= max_attempts);
  END IF;
END $$;

UPDATE webhook_deliveries
SET first_attempt_at = COALESCE(first_attempt_at, created_at)
WHERE first_attempt_at IS NULL;

ALTER TABLE webhook_deliveries
  ALTER COLUMN first_attempt_at SET NOT NULL;

ALTER TABLE webhook_deliveries
  ALTER COLUMN first_attempt_at SET DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_retry_queue
  ON webhook_deliveries (status, next_retry_at)
  WHERE status = 'retrying';

CREATE INDEX IF NOT EXISTS idx_webhook_dead_letters_org_dead_lettered_at
  ON webhook_dead_letters (organization_id, dead_lettered_at DESC);

CREATE INDEX IF NOT EXISTS idx_webhook_replay_jobs_org_status_created
  ON webhook_replay_jobs (organization_id, status, created_at DESC);

CREATE OR REPLACE FUNCTION webhook_retry_delay_seconds(p_next_retry_number integer)
RETURNS integer
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT CASE p_next_retry_number
    WHEN 1 THEN 30
    WHEN 2 THEN 120
    WHEN 3 THEN 600
    WHEN 4 THEN 1800
    WHEN 5 THEN 7200
    WHEN 6 THEN 28800
    ELSE NULL
  END;
$$;

CREATE OR REPLACE FUNCTION webhook_failure_is_retryable(
  p_response_code integer,
  p_error_code text DEFAULT NULL
)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT CASE
    WHEN p_response_code IS NULL THEN TRUE
    WHEN p_response_code IN (408, 429) THEN TRUE
    WHEN p_response_code >= 500 THEN TRUE
    ELSE FALSE
  END;
$$;

CREATE OR REPLACE FUNCTION enqueue_webhook_retry(
  p_delivery_id uuid,
  p_error_code text,
  p_error_detail text,
  p_response_code integer DEFAULT NULL
)
RETURNS TABLE (
  delivery_id uuid,
  status text,
  next_retry_at timestamptz,
  dead_letter_id uuid
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_delivery webhook_deliveries%ROWTYPE;
  v_retryable boolean;
  v_next_retry_number integer;
  v_delay_seconds integer;
  v_dead_letter_id uuid;
BEGIN
  SELECT *
  INTO v_delivery
  FROM webhook_deliveries
  WHERE id = p_delivery_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'delivery % not found', p_delivery_id;
  END IF;

  IF v_delivery.is_terminal THEN
    RETURN QUERY
    SELECT v_delivery.id, v_delivery.status, v_delivery.next_retry_at, NULL::uuid;
    RETURN;
  END IF;

  v_retryable := webhook_failure_is_retryable(p_response_code, p_error_code);
  v_next_retry_number := v_delivery.retry_count + 1;
  v_delay_seconds := webhook_retry_delay_seconds(v_next_retry_number);

  IF v_retryable AND v_next_retry_number < v_delivery.max_attempts AND v_delay_seconds IS NOT NULL THEN
    RETURN QUERY
    UPDATE webhook_deliveries d
    SET
      status = 'retrying',
      retry_count = v_next_retry_number,
      next_retry_at = now() + make_interval(secs => v_delay_seconds),
      last_attempt_at = now(),
      response_code = p_response_code,
      error_code = p_error_code,
      error_detail = p_error_detail,
      updated_at = now()
    WHERE d.id = p_delivery_id
    RETURNING d.id, d.status, d.next_retry_at, NULL::uuid;
    RETURN;
  END IF;

  UPDATE webhook_deliveries
  SET
    status = 'dead_lettered',
    is_terminal = true,
    terminal_at = now(),
    next_retry_at = NULL,
    last_attempt_at = now(),
    retry_count = LEAST(v_next_retry_number, max_attempts),
    response_code = p_response_code,
    error_code = p_error_code,
    error_detail = p_error_detail,
    updated_at = now()
  WHERE id = p_delivery_id;

  INSERT INTO webhook_dead_letters (
    organization_id,
    subscription_id,
    delivery_id,
    event_id,
    event_name,
    final_attempt,
    error_code,
    error_detail,
    payload,
    first_attempt_at,
    dead_lettered_at
  ) VALUES (
    v_delivery.organization_id,
    v_delivery.subscription_id,
    v_delivery.id,
    v_delivery.event_id,
    v_delivery.event_name,
    LEAST(v_next_retry_number, v_delivery.max_attempts),
    p_error_code,
    p_error_detail,
    v_delivery.payload,
    v_delivery.first_attempt_at,
    now()
  )
  ON CONFLICT ON CONSTRAINT webhook_dead_letters_delivery_unique DO UPDATE
  SET
    final_attempt = EXCLUDED.final_attempt,
    error_code = EXCLUDED.error_code,
    error_detail = EXCLUDED.error_detail,
    dead_lettered_at = EXCLUDED.dead_lettered_at
  RETURNING id INTO v_dead_letter_id;

  delivery_id := v_delivery.id;
  status := 'dead_lettered';
  next_retry_at := NULL;
  dead_letter_id := v_dead_letter_id;
  RETURN NEXT;
END;
$$;

CREATE OR REPLACE FUNCTION request_webhook_replay_for_dead_letter(
  p_dead_letter_id uuid,
  p_requested_by uuid,
  p_reason text DEFAULT NULL
)
RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
  v_dl webhook_dead_letters%ROWTYPE;
  v_job_id uuid;
BEGIN
  SELECT *
  INTO v_dl
  FROM webhook_dead_letters
  WHERE id = p_dead_letter_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'dead letter % not found', p_dead_letter_id;
  END IF;

  INSERT INTO webhook_replay_jobs (
    organization_id,
    requested_by,
    replay_scope,
    subscription_id,
    event_id,
    source_dead_letter_id,
    status,
    reason,
    max_deliveries
  ) VALUES (
    v_dl.organization_id,
    p_requested_by,
    'delivery',
    v_dl.subscription_id,
    v_dl.event_id,
    v_dl.id,
    'queued',
    p_reason,
    1
  )
  RETURNING id INTO v_job_id;

  UPDATE webhook_dead_letters
  SET
    replay_status = 'queued',
    replay_job_id = v_job_id
  WHERE id = v_dl.id;

  RETURN v_job_id;
END;
$$;

COMMIT;
