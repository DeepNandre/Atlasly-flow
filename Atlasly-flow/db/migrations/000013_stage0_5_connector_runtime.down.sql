BEGIN;

DROP FUNCTION IF EXISTS record_connector_error(uuid, text, text, text, jsonb, text, boolean);
DROP FUNCTION IF EXISTS complete_connector_run(uuid, text, integer, integer, integer, jsonb, jsonb);
DROP FUNCTION IF EXISTS start_connector_run(uuid, text, text, text, jsonb);

DROP INDEX IF EXISTS idx_connector_errors_org_classification_created_at;
DROP INDEX IF EXISTS idx_connector_runs_org_status_created_at;

ALTER TABLE connector_errors
  DROP CONSTRAINT IF EXISTS connector_errors_classification_allowed_chk;

ALTER TABLE connector_runs
  DROP CONSTRAINT IF EXISTS connector_runs_terminal_fields_chk,
  DROP CONSTRAINT IF EXISTS connector_runs_record_bounds_chk,
  DROP CONSTRAINT IF EXISTS connector_runs_records_nonnegative_chk,
  DROP CONSTRAINT IF EXISTS connector_runs_trigger_type_values_chk,
  DROP CONSTRAINT IF EXISTS connector_runs_run_mode_values_chk,
  DROP CONSTRAINT IF EXISTS connector_runs_status_chk;

DROP FUNCTION IF EXISTS connector_error_default_retryable(text);
DROP FUNCTION IF EXISTS connector_error_classification_is_allowed(text);

COMMIT;
