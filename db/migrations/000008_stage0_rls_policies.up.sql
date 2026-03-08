BEGIN;

CREATE OR REPLACE FUNCTION app_current_organization_id()
RETURNS uuid
LANGUAGE sql
STABLE
AS $$
  SELECT NULLIF(current_setting('app.current_organization_id', true), '')::uuid;
$$;

CREATE OR REPLACE FUNCTION app_current_user_id()
RETURNS uuid
LANGUAGE sql
STABLE
AS $$
  SELECT NULLIF(current_setting('app.current_user_id', true), '')::uuid;
$$;

CREATE OR REPLACE FUNCTION app_has_org_role(org_id uuid, allowed membership_role[])
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM memberships m
    WHERE m.organization_id = org_id
      AND m.user_id = app_current_user_id()
      AND m.role = ANY(allowed)
  );
$$;

CREATE OR REPLACE FUNCTION app_has_org_access(org_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT app_has_org_role(
    org_id,
    ARRAY['owner', 'admin', 'pm', 'reviewer', 'subcontractor']::membership_role[]
  );
$$;

CREATE OR REPLACE FUNCTION app_can_access_project(org_id uuid, project_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM projects p
    LEFT JOIN memberships m_org
      ON m_org.organization_id = p.organization_id
     AND m_org.workspace_id IS NULL
     AND m_org.user_id = app_current_user_id()
    LEFT JOIN memberships m_ws
      ON m_ws.organization_id = p.organization_id
     AND m_ws.workspace_id = p.workspace_id
     AND m_ws.user_id = app_current_user_id()
    WHERE p.organization_id = org_id
      AND p.id = project_id
      AND (m_org.id IS NOT NULL OR m_ws.id IS NOT NULL)
  );
$$;

CREATE OR REPLACE FUNCTION app_is_task_assignee(org_id uuid, task_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM tasks t
    WHERE t.organization_id = org_id
      AND t.id = task_id
      AND t.assignee_user_id = app_current_user_id()
  );
$$;

ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE ahj_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE permits ENABLE ROW LEVEL SECURITY;
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE task_comments ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_tags ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE domain_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE notification_jobs ENABLE ROW LEVEL SECURITY;

ALTER TABLE workspaces FORCE ROW LEVEL SECURITY;
ALTER TABLE memberships FORCE ROW LEVEL SECURITY;
ALTER TABLE ahj_profiles FORCE ROW LEVEL SECURITY;
ALTER TABLE projects FORCE ROW LEVEL SECURITY;
ALTER TABLE project_contacts FORCE ROW LEVEL SECURITY;
ALTER TABLE permits FORCE ROW LEVEL SECURITY;
ALTER TABLE tasks FORCE ROW LEVEL SECURITY;
ALTER TABLE task_comments FORCE ROW LEVEL SECURITY;
ALTER TABLE documents FORCE ROW LEVEL SECURITY;
ALTER TABLE document_versions FORCE ROW LEVEL SECURITY;
ALTER TABLE document_tags FORCE ROW LEVEL SECURITY;
ALTER TABLE audit_events FORCE ROW LEVEL SECURITY;
ALTER TABLE domain_events FORCE ROW LEVEL SECURITY;
ALTER TABLE notification_jobs FORCE ROW LEVEL SECURITY;

CREATE POLICY workspaces_select_pol
  ON workspaces FOR SELECT
  USING (
    organization_id = app_current_organization_id()
    AND app_has_org_access(organization_id)
  );

CREATE POLICY workspaces_write_pol
  ON workspaces FOR ALL
  USING (
    organization_id = app_current_organization_id()
    AND app_has_org_role(organization_id, ARRAY['owner', 'admin']::membership_role[])
  )
  WITH CHECK (
    organization_id = app_current_organization_id()
    AND app_has_org_role(organization_id, ARRAY['owner', 'admin']::membership_role[])
  );

CREATE POLICY memberships_select_pol
  ON memberships FOR SELECT
  USING (
    organization_id = app_current_organization_id()
    AND (
      user_id = app_current_user_id()
      OR app_has_org_role(organization_id, ARRAY['owner', 'admin']::membership_role[])
    )
  );

CREATE POLICY memberships_write_pol
  ON memberships FOR ALL
  USING (
    organization_id = app_current_organization_id()
    AND app_has_org_role(organization_id, ARRAY['owner', 'admin']::membership_role[])
  )
  WITH CHECK (
    organization_id = app_current_organization_id()
    AND app_has_org_role(organization_id, ARRAY['owner', 'admin']::membership_role[])
  );

CREATE POLICY ahj_profiles_select_pol
  ON ahj_profiles FOR SELECT
  USING (
    organization_id = app_current_organization_id()
    AND app_has_org_access(organization_id)
  );

CREATE POLICY ahj_profiles_write_pol
  ON ahj_profiles FOR ALL
  USING (
    organization_id = app_current_organization_id()
    AND app_has_org_role(organization_id, ARRAY['owner', 'admin', 'pm']::membership_role[])
  )
  WITH CHECK (
    organization_id = app_current_organization_id()
    AND app_has_org_role(organization_id, ARRAY['owner', 'admin', 'pm']::membership_role[])
  );

CREATE POLICY projects_select_pol
  ON projects FOR SELECT
  USING (
    organization_id = app_current_organization_id()
    AND app_can_access_project(organization_id, id)
  );

CREATE POLICY projects_write_pol
  ON projects FOR ALL
  USING (
    organization_id = app_current_organization_id()
    AND app_has_org_role(organization_id, ARRAY['owner', 'admin', 'pm']::membership_role[])
  )
  WITH CHECK (
    organization_id = app_current_organization_id()
    AND app_has_org_role(organization_id, ARRAY['owner', 'admin', 'pm']::membership_role[])
  );

CREATE POLICY project_contacts_select_pol
  ON project_contacts FOR SELECT
  USING (
    organization_id = app_current_organization_id()
    AND app_can_access_project(organization_id, project_id)
  );

CREATE POLICY project_contacts_write_pol
  ON project_contacts FOR ALL
  USING (
    organization_id = app_current_organization_id()
    AND app_has_org_role(organization_id, ARRAY['owner', 'admin', 'pm']::membership_role[])
  )
  WITH CHECK (
    organization_id = app_current_organization_id()
    AND app_has_org_role(organization_id, ARRAY['owner', 'admin', 'pm']::membership_role[])
  );

CREATE POLICY permits_select_pol
  ON permits FOR SELECT
  USING (
    organization_id = app_current_organization_id()
    AND app_can_access_project(organization_id, project_id)
  );

CREATE POLICY permits_write_pol
  ON permits FOR ALL
  USING (
    organization_id = app_current_organization_id()
    AND app_has_org_role(organization_id, ARRAY['owner', 'admin', 'pm']::membership_role[])
  )
  WITH CHECK (
    organization_id = app_current_organization_id()
    AND app_has_org_role(organization_id, ARRAY['owner', 'admin', 'pm']::membership_role[])
  );

CREATE POLICY tasks_select_pol
  ON tasks FOR SELECT
  USING (
    organization_id = app_current_organization_id()
    AND app_can_access_project(organization_id, project_id)
  );

CREATE POLICY tasks_insert_pol
  ON tasks FOR INSERT
  WITH CHECK (
    organization_id = app_current_organization_id()
    AND app_can_access_project(organization_id, project_id)
    AND app_has_org_role(organization_id, ARRAY['owner', 'admin', 'pm', 'reviewer']::membership_role[])
  );

CREATE POLICY tasks_update_delete_pol
  ON tasks FOR UPDATE
  USING (
    organization_id = app_current_organization_id()
    AND app_can_access_project(organization_id, project_id)
    AND (
      app_has_org_role(organization_id, ARRAY['owner', 'admin', 'pm', 'reviewer']::membership_role[])
      OR (
        app_has_org_role(organization_id, ARRAY['subcontractor']::membership_role[])
        AND app_is_task_assignee(organization_id, id)
      )
    )
  )
  WITH CHECK (
    organization_id = app_current_organization_id()
    AND app_can_access_project(organization_id, project_id)
    AND (
      app_has_org_role(organization_id, ARRAY['owner', 'admin', 'pm', 'reviewer']::membership_role[])
      OR (
        app_has_org_role(organization_id, ARRAY['subcontractor']::membership_role[])
        AND app_is_task_assignee(organization_id, id)
      )
    )
  );

CREATE POLICY tasks_delete_pol
  ON tasks FOR DELETE
  USING (
    organization_id = app_current_organization_id()
    AND app_can_access_project(organization_id, project_id)
    AND app_has_org_role(organization_id, ARRAY['owner', 'admin', 'pm']::membership_role[])
  );

CREATE POLICY task_comments_select_pol
  ON task_comments FOR SELECT
  USING (
    organization_id = app_current_organization_id()
    AND EXISTS (
      SELECT 1
      FROM tasks t
      WHERE t.organization_id = task_comments.organization_id
        AND t.id = task_comments.task_id
        AND app_can_access_project(t.organization_id, t.project_id)
    )
  );

CREATE POLICY task_comments_insert_pol
  ON task_comments FOR INSERT
  WITH CHECK (
    organization_id = app_current_organization_id()
    AND app_has_org_access(organization_id)
    AND EXISTS (
      SELECT 1
      FROM tasks t
      WHERE t.organization_id = task_comments.organization_id
        AND t.id = task_comments.task_id
        AND app_can_access_project(t.organization_id, t.project_id)
    )
  );

CREATE POLICY task_comments_delete_pol
  ON task_comments FOR DELETE
  USING (
    organization_id = app_current_organization_id()
    AND app_has_org_role(organization_id, ARRAY['owner', 'admin', 'pm', 'reviewer']::membership_role[])
  );

CREATE POLICY documents_select_pol
  ON documents FOR SELECT
  USING (
    organization_id = app_current_organization_id()
    AND app_can_access_project(organization_id, project_id)
  );

CREATE POLICY documents_write_pol
  ON documents FOR ALL
  USING (
    organization_id = app_current_organization_id()
    AND app_has_org_role(organization_id, ARRAY['owner', 'admin', 'pm', 'reviewer']::membership_role[])
  )
  WITH CHECK (
    organization_id = app_current_organization_id()
    AND app_has_org_role(organization_id, ARRAY['owner', 'admin', 'pm', 'reviewer']::membership_role[])
  );

CREATE POLICY document_versions_select_pol
  ON document_versions FOR SELECT
  USING (
    organization_id = app_current_organization_id()
    AND EXISTS (
      SELECT 1
      FROM documents d
      WHERE d.organization_id = document_versions.organization_id
        AND d.id = document_versions.document_id
        AND app_can_access_project(d.organization_id, d.project_id)
    )
  );

CREATE POLICY document_versions_write_pol
  ON document_versions FOR ALL
  USING (
    organization_id = app_current_organization_id()
    AND app_has_org_role(organization_id, ARRAY['owner', 'admin', 'pm', 'reviewer']::membership_role[])
  )
  WITH CHECK (
    organization_id = app_current_organization_id()
    AND app_has_org_role(organization_id, ARRAY['owner', 'admin', 'pm', 'reviewer']::membership_role[])
  );

CREATE POLICY document_tags_select_pol
  ON document_tags FOR SELECT
  USING (
    organization_id = app_current_organization_id()
    AND EXISTS (
      SELECT 1
      FROM documents d
      WHERE d.organization_id = document_tags.organization_id
        AND d.id = document_tags.document_id
        AND app_can_access_project(d.organization_id, d.project_id)
    )
  );

CREATE POLICY document_tags_write_pol
  ON document_tags FOR ALL
  USING (
    organization_id = app_current_organization_id()
    AND app_has_org_role(organization_id, ARRAY['owner', 'admin', 'pm', 'reviewer']::membership_role[])
  )
  WITH CHECK (
    organization_id = app_current_organization_id()
    AND app_has_org_role(organization_id, ARRAY['owner', 'admin', 'pm', 'reviewer']::membership_role[])
  );

CREATE POLICY audit_events_select_pol
  ON audit_events FOR SELECT
  USING (
    organization_id = app_current_organization_id()
    AND app_has_org_access(organization_id)
  );

CREATE POLICY audit_events_insert_pol
  ON audit_events FOR INSERT
  WITH CHECK (
    organization_id = app_current_organization_id()
    AND app_has_org_access(organization_id)
  );

CREATE POLICY domain_events_select_pol
  ON domain_events FOR SELECT
  USING (
    organization_id = app_current_organization_id()
    AND app_has_org_access(organization_id)
  );

CREATE POLICY domain_events_write_pol
  ON domain_events FOR ALL
  USING (
    organization_id = app_current_organization_id()
    AND app_has_org_role(organization_id, ARRAY['owner', 'admin', 'pm']::membership_role[])
  )
  WITH CHECK (
    organization_id = app_current_organization_id()
    AND app_has_org_role(organization_id, ARRAY['owner', 'admin', 'pm']::membership_role[])
  );

CREATE POLICY notification_jobs_select_pol
  ON notification_jobs FOR SELECT
  USING (
    organization_id = app_current_organization_id()
    AND app_has_org_access(organization_id)
  );

CREATE POLICY notification_jobs_write_pol
  ON notification_jobs FOR ALL
  USING (
    organization_id = app_current_organization_id()
    AND app_has_org_role(organization_id, ARRAY['owner', 'admin', 'pm']::membership_role[])
  )
  WITH CHECK (
    organization_id = app_current_organization_id()
    AND app_has_org_role(organization_id, ARRAY['owner', 'admin', 'pm']::membership_role[])
  );

COMMIT;

