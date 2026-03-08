BEGIN;

DROP FUNCTION IF EXISTS get_latest_dashboard_snapshot(uuid);
DROP FUNCTION IF EXISTS upsert_dashboard_snapshot(uuid, timestamptz, timestamptz, jsonb, boolean);
DROP FUNCTION IF EXISTS rotate_api_credential(uuid, uuid, text, text, text, text[], timestamptz);
DROP FUNCTION IF EXISTS revoke_api_credential(uuid, uuid, text);
DROP FUNCTION IF EXISTS create_api_credential(uuid, uuid, text, text, text, text[], timestamptz);

DROP INDEX IF EXISTS idx_dashboard_snapshots_org_freshness;
DROP INDEX IF EXISTS idx_dashboard_snapshots_org_snapshot_at_unique;
DROP INDEX IF EXISTS idx_api_credentials_org_prefix_active;

ALTER TABLE dashboard_snapshots
  DROP CONSTRAINT IF EXISTS dashboard_snapshots_metrics_shape_chk;

ALTER TABLE api_credentials
  DROP CONSTRAINT IF EXISTS api_credentials_hash_length_chk,
  DROP CONSTRAINT IF EXISTS api_credentials_expiry_after_creation_chk,
  DROP CONSTRAINT IF EXISTS api_credentials_scopes_allowed_chk,
  DROP COLUMN IF EXISTS last_used_ip,
  DROP COLUMN IF EXISTS revoked_by,
  DROP COLUMN IF EXISTS revoked_reason;

DROP FUNCTION IF EXISTS dashboard_metrics_shape_valid(jsonb);
DROP FUNCTION IF EXISTS api_scopes_are_allowed(jsonb);
DROP FUNCTION IF EXISTS api_scope_is_allowed(text);

COMMIT;
