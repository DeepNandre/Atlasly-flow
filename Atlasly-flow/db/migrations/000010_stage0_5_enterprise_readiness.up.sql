-- Stage 0.5 Slice 1 migration
-- Purpose: enterprise readiness foundational schema.
-- Prerequisite: Stage 0 base tables (organizations, users, tasks) already exist.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS webhook_subscriptions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  target_url TEXT NOT NULL,
  event_types JSONB NOT NULL DEFAULT '[]'::jsonb,
  signing_secret_ciphertext TEXT NOT NULL,
  signing_secret_last_rotated_at TIMESTAMPTZ,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_by UUID,
  updated_by UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT webhook_subscriptions_target_url_not_empty CHECK (length(trim(target_url)) > 0)
);

CREATE TABLE IF NOT EXISTS webhook_deliveries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  subscription_id UUID NOT NULL REFERENCES webhook_subscriptions(id) ON DELETE CASCADE,
  event_id UUID NOT NULL,
  event_name TEXT NOT NULL,
  attempt INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL,
  next_retry_at TIMESTAMPTZ,
  response_code INTEGER,
  response_latency_ms INTEGER,
  error_code TEXT,
  error_detail TEXT,
  payload JSONB NOT NULL,
  delivered_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT webhook_deliveries_attempt_positive CHECK (attempt > 0),
  CONSTRAINT webhook_deliveries_status_not_empty CHECK (length(trim(status)) > 0),
  CONSTRAINT webhook_deliveries_response_latency_nonnegative CHECK (response_latency_ms IS NULL OR response_latency_ms >= 0),
  CONSTRAINT webhook_deliveries_delivery_attempt_unique UNIQUE (subscription_id, event_id, attempt)
);

CREATE TABLE IF NOT EXISTS connector_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  connector_name TEXT NOT NULL,
  run_status TEXT NOT NULL,
  trigger_type TEXT NOT NULL,
  run_mode TEXT NOT NULL,
  started_at TIMESTAMPTZ,
  ended_at TIMESTAMPTZ,
  duration_ms INTEGER,
  records_fetched INTEGER NOT NULL DEFAULT 0,
  records_synced INTEGER NOT NULL DEFAULT 0,
  records_failed INTEGER NOT NULL DEFAULT 0,
  cursor_before JSONB,
  cursor_after JSONB,
  error_summary JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT connector_runs_connector_name_not_empty CHECK (length(trim(connector_name)) > 0),
  CONSTRAINT connector_runs_run_status_not_empty CHECK (length(trim(run_status)) > 0),
  CONSTRAINT connector_runs_trigger_type_not_empty CHECK (length(trim(trigger_type)) > 0),
  CONSTRAINT connector_runs_run_mode_not_empty CHECK (length(trim(run_mode)) > 0),
  CONSTRAINT connector_runs_duration_nonnegative CHECK (duration_ms IS NULL OR duration_ms >= 0)
);

CREATE TABLE IF NOT EXISTS connector_errors (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  connector_run_id UUID NOT NULL REFERENCES connector_runs(id) ON DELETE CASCADE,
  external_record_id TEXT,
  classification TEXT NOT NULL,
  external_code TEXT,
  message TEXT NOT NULL,
  payload_excerpt_redacted JSONB,
  is_retryable BOOLEAN NOT NULL DEFAULT FALSE,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT connector_errors_classification_not_empty CHECK (length(trim(classification)) > 0),
  CONSTRAINT connector_errors_message_not_empty CHECK (length(trim(message)) > 0)
);

CREATE TABLE IF NOT EXISTS dashboard_snapshots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  snapshot_at TIMESTAMPTZ NOT NULL,
  freshness_seconds INTEGER NOT NULL,
  source_max_event_at TIMESTAMPTZ,
  is_backfill BOOLEAN NOT NULL DEFAULT FALSE,
  metrics JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT dashboard_snapshots_freshness_nonnegative CHECK (freshness_seconds >= 0)
);

CREATE TABLE IF NOT EXISTS api_credentials (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  created_by UUID,
  name TEXT NOT NULL,
  key_prefix TEXT NOT NULL,
  key_hash TEXT NOT NULL,
  scopes JSONB NOT NULL DEFAULT '[]'::jsonb,
  expires_at TIMESTAMPTZ,
  rotated_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  last_used_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT api_credentials_name_not_empty CHECK (length(trim(name)) > 0),
  CONSTRAINT api_credentials_key_prefix_not_empty CHECK (length(trim(key_prefix)) > 0),
  CONSTRAINT api_credentials_key_hash_not_empty CHECK (length(trim(key_hash)) > 0)
);

CREATE TABLE IF NOT EXISTS task_templates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  template JSONB NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_by UUID,
  updated_by UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT task_templates_name_not_empty CHECK (length(trim(name)) > 0)
);

CREATE TABLE IF NOT EXISTS security_audit_exports (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  requested_by UUID NOT NULL,
  generated_at TIMESTAMPTZ,
  time_range_start TIMESTAMPTZ NOT NULL,
  time_range_end TIMESTAMPTZ NOT NULL,
  checksum TEXT,
  storage_uri TEXT,
  access_log_ref TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT security_audit_exports_time_range_valid CHECK (time_range_end >= time_range_start),
  CONSTRAINT security_audit_exports_status_not_empty CHECK (length(trim(status)) > 0)
);

-- Required Stage 0.5 indexes from stage spec.
CREATE INDEX IF NOT EXISTS idx_webhook_subscriptions_org_active
  ON webhook_subscriptions (organization_id, is_active);

CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_org_created_at
  ON webhook_deliveries (organization_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_connector_runs_org_created_at
  ON connector_runs (organization_id, created_at DESC);

-- Operational helper indexes.
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_subscription_status
  ON webhook_deliveries (subscription_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_connector_errors_run_id_occurred
  ON connector_errors (connector_run_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_dashboard_snapshots_org_snapshot_at
  ON dashboard_snapshots (organization_id, snapshot_at DESC);

CREATE INDEX IF NOT EXISTS idx_api_credentials_org_revoked_at
  ON api_credentials (organization_id, revoked_at, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_task_templates_org_active
  ON task_templates (organization_id, is_active, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_security_audit_exports_org_created_at
  ON security_audit_exports (organization_id, created_at DESC);
