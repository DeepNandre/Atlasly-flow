BEGIN;

DROP TRIGGER IF EXISTS permits_status_transition_trg ON permits;
DROP FUNCTION IF EXISTS permits_enforce_status_transition();
DROP FUNCTION IF EXISTS app_is_valid_permit_status_transition(permit_status, permit_status);

DROP TRIGGER IF EXISTS tasks_increment_version_trg ON tasks;
DROP FUNCTION IF EXISTS increment_task_version();

DROP TRIGGER IF EXISTS tasks_set_updated_at_trg ON tasks;
DROP TRIGGER IF EXISTS permits_set_updated_at_trg ON permits;
DROP TRIGGER IF EXISTS projects_set_updated_at_trg ON projects;
DROP FUNCTION IF EXISTS set_updated_at();

DROP TABLE IF EXISTS task_comments;
DROP TABLE IF EXISTS tasks;
DROP TABLE IF EXISTS permits;
DROP TABLE IF EXISTS project_contacts;
DROP TABLE IF EXISTS projects;
DROP TABLE IF EXISTS ahj_profiles;

COMMIT;

