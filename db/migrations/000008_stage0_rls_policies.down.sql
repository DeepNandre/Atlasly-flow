BEGIN;

DROP POLICY IF EXISTS notification_jobs_write_pol ON notification_jobs;
DROP POLICY IF EXISTS notification_jobs_select_pol ON notification_jobs;

DROP POLICY IF EXISTS domain_events_write_pol ON domain_events;
DROP POLICY IF EXISTS domain_events_select_pol ON domain_events;

DROP POLICY IF EXISTS audit_events_insert_pol ON audit_events;
DROP POLICY IF EXISTS audit_events_select_pol ON audit_events;

DROP POLICY IF EXISTS document_tags_write_pol ON document_tags;
DROP POLICY IF EXISTS document_tags_select_pol ON document_tags;

DROP POLICY IF EXISTS document_versions_write_pol ON document_versions;
DROP POLICY IF EXISTS document_versions_select_pol ON document_versions;

DROP POLICY IF EXISTS documents_write_pol ON documents;
DROP POLICY IF EXISTS documents_select_pol ON documents;

DROP POLICY IF EXISTS task_comments_delete_pol ON task_comments;
DROP POLICY IF EXISTS task_comments_insert_pol ON task_comments;
DROP POLICY IF EXISTS task_comments_select_pol ON task_comments;

DROP POLICY IF EXISTS tasks_delete_pol ON tasks;
DROP POLICY IF EXISTS tasks_update_delete_pol ON tasks;
DROP POLICY IF EXISTS tasks_insert_pol ON tasks;
DROP POLICY IF EXISTS tasks_select_pol ON tasks;

DROP POLICY IF EXISTS permits_write_pol ON permits;
DROP POLICY IF EXISTS permits_select_pol ON permits;

DROP POLICY IF EXISTS project_contacts_write_pol ON project_contacts;
DROP POLICY IF EXISTS project_contacts_select_pol ON project_contacts;

DROP POLICY IF EXISTS projects_write_pol ON projects;
DROP POLICY IF EXISTS projects_select_pol ON projects;

DROP POLICY IF EXISTS ahj_profiles_write_pol ON ahj_profiles;
DROP POLICY IF EXISTS ahj_profiles_select_pol ON ahj_profiles;

DROP POLICY IF EXISTS memberships_write_pol ON memberships;
DROP POLICY IF EXISTS memberships_select_pol ON memberships;

DROP POLICY IF EXISTS workspaces_write_pol ON workspaces;
DROP POLICY IF EXISTS workspaces_select_pol ON workspaces;

ALTER TABLE workspaces NO FORCE ROW LEVEL SECURITY;
ALTER TABLE memberships NO FORCE ROW LEVEL SECURITY;
ALTER TABLE ahj_profiles NO FORCE ROW LEVEL SECURITY;
ALTER TABLE projects NO FORCE ROW LEVEL SECURITY;
ALTER TABLE project_contacts NO FORCE ROW LEVEL SECURITY;
ALTER TABLE permits NO FORCE ROW LEVEL SECURITY;
ALTER TABLE tasks NO FORCE ROW LEVEL SECURITY;
ALTER TABLE task_comments NO FORCE ROW LEVEL SECURITY;
ALTER TABLE documents NO FORCE ROW LEVEL SECURITY;
ALTER TABLE document_versions NO FORCE ROW LEVEL SECURITY;
ALTER TABLE document_tags NO FORCE ROW LEVEL SECURITY;
ALTER TABLE audit_events NO FORCE ROW LEVEL SECURITY;
ALTER TABLE domain_events NO FORCE ROW LEVEL SECURITY;
ALTER TABLE notification_jobs NO FORCE ROW LEVEL SECURITY;

ALTER TABLE workspaces DISABLE ROW LEVEL SECURITY;
ALTER TABLE memberships DISABLE ROW LEVEL SECURITY;
ALTER TABLE ahj_profiles DISABLE ROW LEVEL SECURITY;
ALTER TABLE projects DISABLE ROW LEVEL SECURITY;
ALTER TABLE project_contacts DISABLE ROW LEVEL SECURITY;
ALTER TABLE permits DISABLE ROW LEVEL SECURITY;
ALTER TABLE tasks DISABLE ROW LEVEL SECURITY;
ALTER TABLE task_comments DISABLE ROW LEVEL SECURITY;
ALTER TABLE documents DISABLE ROW LEVEL SECURITY;
ALTER TABLE document_versions DISABLE ROW LEVEL SECURITY;
ALTER TABLE document_tags DISABLE ROW LEVEL SECURITY;
ALTER TABLE audit_events DISABLE ROW LEVEL SECURITY;
ALTER TABLE domain_events DISABLE ROW LEVEL SECURITY;
ALTER TABLE notification_jobs DISABLE ROW LEVEL SECURITY;

DROP FUNCTION IF EXISTS app_is_task_assignee(uuid, uuid);
DROP FUNCTION IF EXISTS app_can_access_project(uuid, uuid);
DROP FUNCTION IF EXISTS app_has_org_access(uuid);
DROP FUNCTION IF EXISTS app_has_org_role(uuid, membership_role[]);
DROP FUNCTION IF EXISTS app_current_user_id();
DROP FUNCTION IF EXISTS app_current_organization_id();

COMMIT;

