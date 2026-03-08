BEGIN;

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

CREATE TABLE ahj_profiles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  name text NOT NULL,
  jurisdiction_type text NOT NULL,
  region text NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ahj_profiles_org_id_id_unique UNIQUE (organization_id, id),
  CONSTRAINT ahj_profiles_name_nonempty_chk CHECK (length(trim(name)) > 0),
  CONSTRAINT ahj_profiles_jurisdiction_type_nonempty_chk CHECK (length(trim(jurisdiction_type)) > 0)
);

CREATE TABLE projects (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  workspace_id uuid NOT NULL,
  ahj_profile_id uuid NULL,
  name text NOT NULL,
  project_code text NULL,
  address jsonb NOT NULL DEFAULT '{}'::jsonb,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by uuid NOT NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT projects_org_id_id_unique UNIQUE (organization_id, id),
  CONSTRAINT projects_workspace_fk
    FOREIGN KEY (organization_id, workspace_id)
    REFERENCES workspaces(organization_id, id),
  CONSTRAINT projects_ahj_fk
    FOREIGN KEY (organization_id, ahj_profile_id)
    REFERENCES ahj_profiles(organization_id, id),
  CONSTRAINT projects_name_nonempty_chk CHECK (length(trim(name)) > 0)
);

CREATE UNIQUE INDEX projects_org_project_code_unique
  ON projects (organization_id, project_code)
  WHERE project_code IS NOT NULL;

CREATE TABLE project_contacts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  project_id uuid NOT NULL,
  name text NOT NULL,
  email citext NULL,
  phone text NULL,
  company text NULL,
  role text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT project_contacts_org_id_id_unique UNIQUE (organization_id, id),
  CONSTRAINT project_contacts_project_fk
    FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id)
    ON DELETE CASCADE,
  CONSTRAINT project_contacts_name_nonempty_chk CHECK (length(trim(name)) > 0)
);

CREATE TABLE permits (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  project_id uuid NOT NULL,
  permit_type text NOT NULL,
  status permit_status NOT NULL DEFAULT 'draft',
  submitted_at timestamptz NULL,
  issued_at timestamptz NULL,
  expired_at timestamptz NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by uuid NOT NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT permits_org_id_id_unique UNIQUE (organization_id, id),
  CONSTRAINT permits_project_fk
    FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id)
    ON DELETE CASCADE,
  CONSTRAINT permits_permit_type_nonempty_chk CHECK (length(trim(permit_type)) > 0)
);

CREATE TABLE tasks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  project_id uuid NOT NULL,
  permit_id uuid NULL,
  title text NOT NULL,
  description text NULL,
  discipline text NULL,
  status task_status NOT NULL DEFAULT 'todo',
  assignee_user_id uuid NULL REFERENCES users(id),
  due_date date NULL,
  priority smallint NOT NULL DEFAULT 3,
  created_by uuid NOT NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  version integer NOT NULL DEFAULT 1,
  CONSTRAINT tasks_org_id_id_unique UNIQUE (organization_id, id),
  CONSTRAINT tasks_project_fk
    FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id)
    ON DELETE CASCADE,
  CONSTRAINT tasks_permit_fk
    FOREIGN KEY (organization_id, permit_id)
    REFERENCES permits(organization_id, id),
  CONSTRAINT tasks_title_nonempty_chk CHECK (length(trim(title)) > 0),
  CONSTRAINT tasks_priority_chk CHECK (priority BETWEEN 1 AND 5),
  CONSTRAINT tasks_version_chk CHECK (version >= 1)
);

CREATE TABLE task_comments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  task_id uuid NOT NULL,
  author_user_id uuid NOT NULL REFERENCES users(id),
  body text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT task_comments_org_id_id_unique UNIQUE (organization_id, id),
  CONSTRAINT task_comments_task_fk
    FOREIGN KEY (organization_id, task_id)
    REFERENCES tasks(organization_id, id)
    ON DELETE CASCADE,
  CONSTRAINT task_comments_body_nonempty_chk CHECK (length(trim(body)) > 0)
);

CREATE INDEX ahj_profiles_org_id_id_idx
  ON ahj_profiles (organization_id, id);

CREATE INDEX projects_org_id_id_idx
  ON projects (organization_id, id);

CREATE INDEX project_contacts_org_id_id_idx
  ON project_contacts (organization_id, id);

CREATE INDEX permits_org_id_id_idx
  ON permits (organization_id, id);

CREATE INDEX tasks_org_id_id_idx
  ON tasks (organization_id, id);

CREATE INDEX task_comments_org_id_id_idx
  ON task_comments (organization_id, id);

CREATE INDEX permits_project_status_idx
  ON permits (project_id, status);

CREATE INDEX tasks_project_status_idx
  ON tasks (project_id, status);

CREATE INDEX task_comments_task_created_at_desc_idx
  ON task_comments (task_id, created_at DESC);

CREATE TRIGGER projects_set_updated_at_trg
  BEFORE UPDATE ON projects
  FOR EACH ROW
  EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER permits_set_updated_at_trg
  BEFORE UPDATE ON permits
  FOR EACH ROW
  EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER tasks_set_updated_at_trg
  BEFORE UPDATE ON tasks
  FOR EACH ROW
  EXECUTE FUNCTION set_updated_at();

CREATE OR REPLACE FUNCTION increment_task_version()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.version = OLD.version + 1;
  RETURN NEW;
END;
$$;

CREATE TRIGGER tasks_increment_version_trg
  BEFORE UPDATE ON tasks
  FOR EACH ROW
  EXECUTE FUNCTION increment_task_version();

CREATE OR REPLACE FUNCTION app_is_valid_permit_status_transition(
  p_old permit_status,
  p_new permit_status
)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT CASE
    WHEN p_old = p_new THEN true
    WHEN p_old = 'draft' THEN p_new IN ('submitted')
    WHEN p_old = 'submitted' THEN p_new IN ('in_review')
    WHEN p_old = 'in_review' THEN p_new IN ('corrections_required', 'approved', 'issued', 'expired')
    WHEN p_old = 'corrections_required' THEN p_new IN ('submitted', 'expired')
    WHEN p_old = 'approved' THEN p_new IN ('issued', 'expired')
    WHEN p_old = 'issued' THEN p_new IN ('expired')
    WHEN p_old = 'expired' THEN false
    ELSE false
  END;
$$;

CREATE OR REPLACE FUNCTION permits_enforce_status_transition()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NOT app_is_valid_permit_status_transition(OLD.status, NEW.status) THEN
    RAISE EXCEPTION
      'invalid permit status transition from % to %',
      OLD.status,
      NEW.status
      USING ERRCODE = '23514';
  END IF;

  IF OLD.status <> NEW.status THEN
    IF NEW.status = 'submitted' AND NEW.submitted_at IS NULL THEN
      NEW.submitted_at = now();
    END IF;

    IF NEW.status = 'issued' AND NEW.issued_at IS NULL THEN
      NEW.issued_at = now();
    END IF;

    IF NEW.status = 'expired' AND NEW.expired_at IS NULL THEN
      NEW.expired_at = now();
    END IF;
  END IF;

  RETURN NEW;
END;
$$;

CREATE TRIGGER permits_status_transition_trg
  BEFORE UPDATE OF status ON permits
  FOR EACH ROW
  EXECUTE FUNCTION permits_enforce_status_transition();

COMMIT;

