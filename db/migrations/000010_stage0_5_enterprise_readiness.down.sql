-- Stage 0.5 Slice 1 rollback migration
-- Rolls back schema introduced in 000010_stage0_5_enterprise_readiness.up.sql.

DROP TABLE IF EXISTS security_audit_exports;
DROP TABLE IF EXISTS task_templates;
DROP TABLE IF EXISTS api_credentials;
DROP TABLE IF EXISTS dashboard_snapshots;
DROP TABLE IF EXISTS connector_errors;
DROP TABLE IF EXISTS connector_runs;
DROP TABLE IF EXISTS webhook_deliveries;
DROP TABLE IF EXISTS webhook_subscriptions;
