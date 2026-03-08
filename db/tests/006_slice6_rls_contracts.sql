-- Slice 6 contract test: tenant isolation with RLS policies.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_tenant_test') THEN
    CREATE ROLE app_tenant_test NOINHERIT;
  END IF;
END $$;

GRANT USAGE ON SCHEMA public TO app_tenant_test;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_tenant_test;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_tenant_test;

INSERT INTO users(id, email, full_name) VALUES
  ('61000000-0000-0000-0000-000000000001', 'slice6-owner1@example.com', 'Slice6 Owner 1'),
  ('61000000-0000-0000-0000-000000000002', 'slice6-owner2@example.com', 'Slice6 Owner 2'),
  ('61000000-0000-0000-0000-000000000003', 'slice6-sub1@example.com', 'Slice6 Sub 1');

INSERT INTO organizations(id, name, slug, created_by) VALUES
  ('62000000-0000-0000-0000-000000000001', 'Slice6 Org One', 'slice6-org-one', '61000000-0000-0000-0000-000000000001'),
  ('62000000-0000-0000-0000-000000000002', 'Slice6 Org Two', 'slice6-org-two', '61000000-0000-0000-0000-000000000002');

INSERT INTO workspaces(id, organization_id, name, is_default) VALUES
  ('63000000-0000-0000-0000-000000000001', '62000000-0000-0000-0000-000000000001', 'Default', true),
  ('63000000-0000-0000-0000-000000000002', '62000000-0000-0000-0000-000000000002', 'Default', true);

INSERT INTO memberships(id, organization_id, workspace_id, user_id, role) VALUES
  ('64000000-0000-0000-0000-000000000001', '62000000-0000-0000-0000-000000000001', NULL, '61000000-0000-0000-0000-000000000001', 'owner'),
  ('64000000-0000-0000-0000-000000000002', '62000000-0000-0000-0000-000000000002', NULL, '61000000-0000-0000-0000-000000000002', 'owner'),
  ('64000000-0000-0000-0000-000000000003', '62000000-0000-0000-0000-000000000001', NULL, '61000000-0000-0000-0000-000000000003', 'subcontractor');

INSERT INTO projects(id, organization_id, workspace_id, name, created_by) VALUES
  ('65000000-0000-0000-0000-000000000001', '62000000-0000-0000-0000-000000000001', '63000000-0000-0000-0000-000000000001', 'Slice6 Project 1', '61000000-0000-0000-0000-000000000001'),
  ('65000000-0000-0000-0000-000000000002', '62000000-0000-0000-0000-000000000002', '63000000-0000-0000-0000-000000000002', 'Slice6 Project 2', '61000000-0000-0000-0000-000000000002');

INSERT INTO tasks(id, organization_id, project_id, title, assignee_user_id, created_by) VALUES
  ('66000000-0000-0000-0000-000000000001', '62000000-0000-0000-0000-000000000001', '65000000-0000-0000-0000-000000000001', 'Assigned Task', '61000000-0000-0000-0000-000000000003', '61000000-0000-0000-0000-000000000001'),
  ('66000000-0000-0000-0000-000000000002', '62000000-0000-0000-0000-000000000001', '65000000-0000-0000-0000-000000000001', 'Other Task', '61000000-0000-0000-0000-000000000001', '61000000-0000-0000-0000-000000000001');

SET ROLE app_tenant_test;
SELECT set_config('app.current_user_id', '61000000-0000-0000-0000-000000000001', false);
SELECT set_config('app.current_organization_id', '62000000-0000-0000-0000-000000000001', false);

DO $$
DECLARE
  visible_projects integer;
BEGIN
  SELECT count(*)
  INTO visible_projects
  FROM projects
  WHERE id IN (
    '65000000-0000-0000-0000-000000000001',
    '65000000-0000-0000-0000-000000000002'
  );

  IF visible_projects <> 1 THEN
    RAISE EXCEPTION 'expected exactly one visible project for org1 owner, got %', visible_projects;
  END IF;
END $$;

DO $$
BEGIN
  BEGIN
    INSERT INTO projects(id, organization_id, workspace_id, name, created_by)
    VALUES (
      '65000000-0000-0000-0000-000000000099',
      '62000000-0000-0000-0000-000000000002',
      '63000000-0000-0000-0000-000000000002',
      'Cross Org Insert',
      '61000000-0000-0000-0000-000000000001'
    );
    RAISE EXCEPTION 'expected RLS insert denial for cross-org project';
  EXCEPTION WHEN insufficient_privilege THEN
    NULL;
  END;
END $$;

SELECT set_config('app.current_user_id', '61000000-0000-0000-0000-000000000003', false);
SELECT set_config('app.current_organization_id', '62000000-0000-0000-0000-000000000001', false);

UPDATE tasks
SET status = 'in_progress'
WHERE id = '66000000-0000-0000-0000-000000000001';

DO $$
DECLARE
  affected integer;
BEGIN
  UPDATE tasks
  SET status = 'done'
  WHERE id = '66000000-0000-0000-0000-000000000002';

  GET DIAGNOSTICS affected = ROW_COUNT;
  IF affected <> 0 THEN
    RAISE EXCEPTION 'expected zero-row update for non-assigned subcontractor task update, got % rows', affected;
  END IF;
END $$;

RESET ROLE;

SELECT
  EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename = 'projects' AND policyname = 'projects_select_pol'
  ) AS has_projects_rls_policy,
  EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename = 'tasks' AND policyname = 'tasks_update_delete_pol'
  ) AS has_tasks_rls_policy;
