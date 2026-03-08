BEGIN;

DROP FUNCTION IF EXISTS mark_security_audit_export_failed(uuid, text);
DROP FUNCTION IF EXISTS mark_security_audit_export_completed(uuid, uuid, text, text, text, timestamptz);
DROP FUNCTION IF EXISTS mark_security_audit_export_running(uuid, uuid);
DROP FUNCTION IF EXISTS request_security_audit_export(uuid, uuid, timestamptz, timestamptz, text);
DROP FUNCTION IF EXISTS archive_task_template(uuid, uuid);
DROP FUNCTION IF EXISTS update_task_template(uuid, text, text, jsonb, uuid);
DROP FUNCTION IF EXISTS create_task_template(uuid, text, text, jsonb, uuid);
DROP FUNCTION IF EXISTS is_org_owner_or_admin(uuid, uuid);

DROP INDEX IF EXISTS idx_security_audit_exports_requested_by_created;
DROP INDEX IF EXISTS idx_security_audit_exports_org_status_created;

ALTER TABLE security_audit_exports
  DROP CONSTRAINT IF EXISTS security_audit_exports_export_type_chk,
  DROP CONSTRAINT IF EXISTS security_audit_exports_status_values_chk,
  DROP COLUMN IF EXISTS generated_by,
  DROP COLUMN IF EXISTS failure_reason,
  DROP COLUMN IF EXISTS failed_at,
  DROP COLUMN IF EXISTS completed_at,
  DROP COLUMN IF EXISTS started_at,
  DROP COLUMN IF EXISTS export_type;

DROP INDEX IF EXISTS idx_task_templates_org_name_active;

ALTER TABLE task_templates
  DROP CONSTRAINT IF EXISTS task_templates_template_object_chk,
  DROP CONSTRAINT IF EXISTS task_templates_version_positive_chk,
  DROP COLUMN IF EXISTS archived_by,
  DROP COLUMN IF EXISTS archived_at,
  DROP COLUMN IF EXISTS version;

COMMIT;
