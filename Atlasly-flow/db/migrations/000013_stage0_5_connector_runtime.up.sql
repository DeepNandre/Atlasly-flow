BEGIN;

CREATE OR REPLACE FUNCTION connector_error_classification_is_allowed(p_classification text)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT p_classification IN (
    'auth.invalid_credentials',
    'auth.expired_token',
    'rate_limit.exceeded',
    'upstream.timeout',
    'upstream.unavailable',
    'schema.mismatch',
    'data.validation_failed',
    'permission.denied',
    'internal.transient',
    'internal.fatal'
  );
$$;

CREATE OR REPLACE FUNCTION connector_error_default_retryable(p_classification text)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT p_classification IN (
    'rate_limit.exceeded',
    'upstream.timeout',
    'upstream.unavailable',
    'internal.transient'
  );
$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'connector_runs_status_chk'
  ) THEN
    ALTER TABLE connector_runs
      ADD CONSTRAINT connector_runs_status_chk
      CHECK (run_status IN ('queued', 'running', 'succeeded', 'partial', 'failed', 'cancelled'));
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'connector_runs_run_mode_values_chk'
  ) THEN
    ALTER TABLE connector_runs
      ADD CONSTRAINT connector_runs_run_mode_values_chk
      CHECK (run_mode IN ('delta', 'full'));
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'connector_runs_trigger_type_values_chk'
  ) THEN
    ALTER TABLE connector_runs
      ADD CONSTRAINT connector_runs_trigger_type_values_chk
      CHECK (trigger_type IN ('manual', 'scheduled', 'webhook', 'replay'));
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'connector_runs_records_nonnegative_chk'
  ) THEN
    ALTER TABLE connector_runs
      ADD CONSTRAINT connector_runs_records_nonnegative_chk
      CHECK (records_fetched >= 0 AND records_synced >= 0 AND records_failed >= 0);
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'connector_runs_record_bounds_chk'
  ) THEN
    ALTER TABLE connector_runs
      ADD CONSTRAINT connector_runs_record_bounds_chk
      CHECK (records_synced <= records_fetched);
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'connector_runs_terminal_fields_chk'
  ) THEN
    ALTER TABLE connector_runs
      ADD CONSTRAINT connector_runs_terminal_fields_chk
      CHECK (
        (run_status IN ('queued', 'running') AND ended_at IS NULL)
        OR
        (run_status IN ('succeeded', 'partial', 'failed', 'cancelled') AND ended_at IS NOT NULL)
      );
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'connector_errors_classification_allowed_chk'
  ) THEN
    ALTER TABLE connector_errors
      ADD CONSTRAINT connector_errors_classification_allowed_chk
      CHECK (connector_error_classification_is_allowed(classification));
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_connector_runs_org_status_created_at
  ON connector_runs (organization_id, run_status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_connector_errors_org_classification_created_at
  ON connector_errors (organization_id, classification, created_at DESC);

CREATE OR REPLACE FUNCTION start_connector_run(
  p_organization_id uuid,
  p_connector_name text,
  p_trigger_type text,
  p_run_mode text DEFAULT 'delta',
  p_cursor_before jsonb DEFAULT NULL
)
RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
  v_run_id uuid;
BEGIN
  IF p_organization_id IS NULL THEN
    RAISE EXCEPTION 'organization_id is required';
  END IF;

  IF p_connector_name IS NULL OR length(trim(p_connector_name)) = 0 THEN
    RAISE EXCEPTION 'connector_name is required';
  END IF;

  IF p_trigger_type IS NULL OR length(trim(p_trigger_type)) = 0 THEN
    RAISE EXCEPTION 'trigger_type is required';
  END IF;

  INSERT INTO connector_runs (
    organization_id,
    connector_name,
    run_status,
    trigger_type,
    run_mode,
    started_at,
    cursor_before
  ) VALUES (
    p_organization_id,
    p_connector_name,
    'running',
    p_trigger_type,
    p_run_mode,
    now(),
    p_cursor_before
  )
  RETURNING id INTO v_run_id;

  RETURN v_run_id;
END;
$$;

CREATE OR REPLACE FUNCTION complete_connector_run(
  p_run_id uuid,
  p_final_status text,
  p_records_fetched integer DEFAULT 0,
  p_records_synced integer DEFAULT 0,
  p_records_failed integer DEFAULT 0,
  p_cursor_after jsonb DEFAULT NULL,
  p_error_summary jsonb DEFAULT NULL
)
RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
  v_started_at timestamptz;
BEGIN
  IF p_run_id IS NULL THEN
    RAISE EXCEPTION 'run_id is required';
  END IF;

  IF p_final_status NOT IN ('succeeded', 'partial', 'failed', 'cancelled') THEN
    RAISE EXCEPTION 'invalid final status: %', p_final_status;
  END IF;

  IF p_records_fetched < 0 OR p_records_synced < 0 OR p_records_failed < 0 THEN
    RAISE EXCEPTION 'record counters must be non-negative';
  END IF;

  IF p_records_synced > p_records_fetched THEN
    RAISE EXCEPTION 'records_synced cannot exceed records_fetched';
  END IF;

  SELECT started_at
  INTO v_started_at
  FROM connector_runs
  WHERE id = p_run_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'connector run % not found', p_run_id;
  END IF;

  UPDATE connector_runs
  SET
    run_status = p_final_status,
    ended_at = now(),
    duration_ms = GREATEST(0, (extract(epoch FROM (now() - COALESCE(v_started_at, created_at))) * 1000)::integer),
    records_fetched = p_records_fetched,
    records_synced = p_records_synced,
    records_failed = p_records_failed,
    cursor_after = p_cursor_after,
    error_summary = p_error_summary,
    updated_at = now()
  WHERE id = p_run_id
    AND run_status IN ('queued', 'running');

  IF NOT FOUND THEN
    RAISE EXCEPTION 'connector run % is already terminal', p_run_id;
  END IF;

  RETURN p_run_id;
END;
$$;

CREATE OR REPLACE FUNCTION record_connector_error(
  p_connector_run_id uuid,
  p_classification text,
  p_message text,
  p_external_code text DEFAULT NULL,
  p_payload_excerpt_redacted jsonb DEFAULT NULL,
  p_external_record_id text DEFAULT NULL,
  p_is_retryable boolean DEFAULT NULL
)
RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
  v_org_id uuid;
  v_error_id uuid;
  v_is_retryable boolean;
BEGIN
  SELECT organization_id
  INTO v_org_id
  FROM connector_runs
  WHERE id = p_connector_run_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'connector run % not found', p_connector_run_id;
  END IF;

  IF p_classification IS NULL OR length(trim(p_classification)) = 0 THEN
    RAISE EXCEPTION 'classification is required';
  END IF;

  IF p_message IS NULL OR length(trim(p_message)) = 0 THEN
    RAISE EXCEPTION 'message is required';
  END IF;

  v_is_retryable := COALESCE(p_is_retryable, connector_error_default_retryable(p_classification));

  INSERT INTO connector_errors (
    organization_id,
    connector_run_id,
    external_record_id,
    classification,
    external_code,
    message,
    payload_excerpt_redacted,
    is_retryable
  ) VALUES (
    v_org_id,
    p_connector_run_id,
    p_external_record_id,
    p_classification,
    p_external_code,
    p_message,
    p_payload_excerpt_redacted,
    v_is_retryable
  )
  RETURNING id INTO v_error_id;

  RETURN v_error_id;
END;
$$;

COMMIT;
