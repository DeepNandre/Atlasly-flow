BEGIN;

CREATE OR REPLACE FUNCTION api_scope_is_allowed(p_scope text)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT p_scope IN (
    'webhooks:read',
    'webhooks:write',
    'connectors:read',
    'connectors:run',
    'dashboard:read',
    'tasks:read',
    'tasks:write',
    'audit:read'
  );
$$;

CREATE OR REPLACE FUNCTION api_scopes_are_allowed(p_scopes jsonb)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT
    jsonb_typeof(p_scopes) = 'array'
    AND jsonb_array_length(p_scopes) > 0
    AND NOT EXISTS (
      SELECT 1
      FROM jsonb_array_elements_text(p_scopes) AS s(scope)
      WHERE NOT api_scope_is_allowed(s.scope)
    );
$$;

CREATE OR REPLACE FUNCTION dashboard_metrics_shape_valid(p_metrics jsonb)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT
    jsonb_typeof(p_metrics) = 'object'
    AND p_metrics ? 'permits_total'
    AND p_metrics ? 'permit_cycle_time_p50_days'
    AND p_metrics ? 'permit_cycle_time_p90_days'
    AND p_metrics ? 'corrections_rate'
    AND p_metrics ? 'approval_rate_30d'
    AND p_metrics ? 'task_sla_breach_rate'
    AND p_metrics ? 'connector_health_score'
    AND p_metrics ? 'webhook_delivery_success_rate';
$$;

ALTER TABLE api_credentials
  ADD COLUMN IF NOT EXISTS revoked_reason text,
  ADD COLUMN IF NOT EXISTS revoked_by uuid,
  ADD COLUMN IF NOT EXISTS last_used_ip inet;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'api_credentials_scopes_allowed_chk'
  ) THEN
    ALTER TABLE api_credentials
      ADD CONSTRAINT api_credentials_scopes_allowed_chk
      CHECK (api_scopes_are_allowed(scopes));
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'api_credentials_expiry_after_creation_chk'
  ) THEN
    ALTER TABLE api_credentials
      ADD CONSTRAINT api_credentials_expiry_after_creation_chk
      CHECK (expires_at IS NULL OR expires_at > created_at);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'api_credentials_hash_length_chk'
  ) THEN
    ALTER TABLE api_credentials
      ADD CONSTRAINT api_credentials_hash_length_chk
      CHECK (length(key_hash) >= 32);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'dashboard_snapshots_metrics_shape_chk'
  ) THEN
    ALTER TABLE dashboard_snapshots
      ADD CONSTRAINT dashboard_snapshots_metrics_shape_chk
      CHECK (dashboard_metrics_shape_valid(metrics));
  END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_api_credentials_org_prefix_active
  ON api_credentials (organization_id, key_prefix)
  WHERE revoked_at IS NULL;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM dashboard_snapshots
    GROUP BY organization_id, snapshot_at
    HAVING COUNT(*) > 1
  ) THEN
    RAISE EXCEPTION 'cannot enforce unique dashboard snapshot key: duplicate (organization_id, snapshot_at) rows exist';
  END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_dashboard_snapshots_org_snapshot_at_unique
  ON dashboard_snapshots (organization_id, snapshot_at);

CREATE INDEX IF NOT EXISTS idx_dashboard_snapshots_org_freshness
  ON dashboard_snapshots (organization_id, freshness_seconds, snapshot_at DESC);

CREATE OR REPLACE FUNCTION create_api_credential(
  p_organization_id uuid,
  p_created_by uuid,
  p_name text,
  p_key_prefix text,
  p_key_hash text,
  p_scopes text[],
  p_expires_at timestamptz DEFAULT NULL
)
RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
  v_scopes jsonb;
  v_id uuid;
BEGIN
  IF p_organization_id IS NULL THEN
    RAISE EXCEPTION 'organization_id is required';
  END IF;

  IF p_name IS NULL OR length(trim(p_name)) = 0 THEN
    RAISE EXCEPTION 'name is required';
  END IF;

  IF p_key_prefix IS NULL OR length(trim(p_key_prefix)) = 0 THEN
    RAISE EXCEPTION 'key_prefix is required';
  END IF;

  IF p_key_hash IS NULL OR length(trim(p_key_hash)) = 0 THEN
    RAISE EXCEPTION 'key_hash is required';
  END IF;

  IF p_scopes IS NULL OR array_length(p_scopes, 1) IS NULL THEN
    RAISE EXCEPTION 'scopes must not be empty';
  END IF;

  IF p_expires_at IS NOT NULL AND p_expires_at > now() + interval '365 days' THEN
    RAISE EXCEPTION 'expires_at cannot exceed 365 days';
  END IF;

  v_scopes := to_jsonb(p_scopes);

  INSERT INTO api_credentials (
    organization_id,
    created_by,
    name,
    key_prefix,
    key_hash,
    scopes,
    expires_at,
    created_at,
    updated_at
  ) VALUES (
    p_organization_id,
    p_created_by,
    p_name,
    p_key_prefix,
    p_key_hash,
    v_scopes,
    p_expires_at,
    now(),
    now()
  )
  RETURNING id INTO v_id;

  RETURN v_id;
END;
$$;

CREATE OR REPLACE FUNCTION revoke_api_credential(
  p_credential_id uuid,
  p_revoked_by uuid,
  p_reason text
)
RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
  v_id uuid;
BEGIN
  IF p_credential_id IS NULL THEN
    RAISE EXCEPTION 'credential_id is required';
  END IF;

  UPDATE api_credentials
  SET
    revoked_at = now(),
    revoked_by = p_revoked_by,
    revoked_reason = p_reason,
    updated_at = now()
  WHERE id = p_credential_id
    AND revoked_at IS NULL
  RETURNING id INTO v_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'credential % not found or already revoked', p_credential_id;
  END IF;

  RETURN v_id;
END;
$$;

CREATE OR REPLACE FUNCTION rotate_api_credential(
  p_old_credential_id uuid,
  p_rotated_by uuid,
  p_new_name text,
  p_new_key_prefix text,
  p_new_key_hash text,
  p_new_scopes text[],
  p_new_expires_at timestamptz DEFAULT NULL
)
RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
  v_old_org_id uuid;
  v_new_id uuid;
BEGIN
  SELECT organization_id
  INTO v_old_org_id
  FROM api_credentials
  WHERE id = p_old_credential_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'old credential % not found', p_old_credential_id;
  END IF;

  PERFORM revoke_api_credential(p_old_credential_id, p_rotated_by, 'rotated');

  v_new_id := create_api_credential(
    v_old_org_id,
    p_rotated_by,
    p_new_name,
    p_new_key_prefix,
    p_new_key_hash,
    p_new_scopes,
    p_new_expires_at
  );

  UPDATE api_credentials
  SET rotated_at = now(),
      updated_at = now()
  WHERE id = p_old_credential_id;

  RETURN v_new_id;
END;
$$;

CREATE OR REPLACE FUNCTION upsert_dashboard_snapshot(
  p_organization_id uuid,
  p_snapshot_at timestamptz,
  p_source_max_event_at timestamptz,
  p_metrics jsonb,
  p_is_backfill boolean DEFAULT false
)
RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
  v_id uuid;
  v_freshness integer;
BEGIN
  IF p_organization_id IS NULL THEN
    RAISE EXCEPTION 'organization_id is required';
  END IF;

  IF p_snapshot_at IS NULL THEN
    RAISE EXCEPTION 'snapshot_at is required';
  END IF;

  IF p_source_max_event_at IS NULL THEN
    v_freshness := GREATEST(0, extract(epoch FROM (now() - p_snapshot_at))::integer);
  ELSE
    v_freshness := GREATEST(0, extract(epoch FROM (now() - p_source_max_event_at))::integer);
  END IF;

  INSERT INTO dashboard_snapshots (
    organization_id,
    snapshot_at,
    freshness_seconds,
    source_max_event_at,
    is_backfill,
    metrics,
    created_at
  ) VALUES (
    p_organization_id,
    p_snapshot_at,
    v_freshness,
    p_source_max_event_at,
    p_is_backfill,
    p_metrics,
    now()
  )
  ON CONFLICT (organization_id, snapshot_at)
  DO UPDATE SET
    freshness_seconds = EXCLUDED.freshness_seconds,
    source_max_event_at = EXCLUDED.source_max_event_at,
    is_backfill = EXCLUDED.is_backfill,
    metrics = EXCLUDED.metrics
  RETURNING id INTO v_id;

  RETURN v_id;
END;
$$;

CREATE OR REPLACE FUNCTION get_latest_dashboard_snapshot(
  p_organization_id uuid
)
RETURNS TABLE (
  snapshot_id uuid,
  snapshot_at timestamptz,
  freshness_seconds integer,
  source_max_event_at timestamptz,
  is_backfill boolean,
  metrics jsonb
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    ds.id,
    ds.snapshot_at,
    ds.freshness_seconds,
    ds.source_max_event_at,
    ds.is_backfill,
    ds.metrics
  FROM dashboard_snapshots ds
  WHERE ds.organization_id = p_organization_id
  ORDER BY ds.snapshot_at DESC
  LIMIT 1;
$$;

COMMIT;
