BEGIN;

CREATE TABLE users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email citext NOT NULL UNIQUE,
  full_name text NOT NULL,
  status text NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT users_status_chk CHECK (status IN ('active', 'invited', 'disabled'))
);

CREATE TABLE organizations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  slug citext NOT NULL UNIQUE,
  created_by uuid NOT NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE workspaces (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  name text NOT NULL,
  is_default boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT workspaces_org_name_unique UNIQUE (organization_id, name),
  CONSTRAINT workspaces_org_id_id_unique UNIQUE (organization_id, id)
);

CREATE UNIQUE INDEX workspaces_one_default_per_org_uidx
  ON workspaces (organization_id)
  WHERE is_default;

CREATE TABLE user_identities (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  provider text NOT NULL,
  provider_subject text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT user_identities_provider_subject_unique UNIQUE (provider, provider_subject),
  CONSTRAINT user_identities_user_provider_unique UNIQUE (user_id, provider)
);

CREATE TABLE memberships (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  workspace_id uuid NULL,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role membership_role NOT NULL,
  invited_by uuid NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT memberships_workspace_org_fk
    FOREIGN KEY (organization_id, workspace_id)
    REFERENCES workspaces(organization_id, id)
    ON DELETE CASCADE
);

-- org-level membership uniqueness (workspace_id is null)
CREATE UNIQUE INDEX memberships_org_level_unique
  ON memberships (organization_id, user_id)
  WHERE workspace_id IS NULL;

-- workspace-level membership uniqueness (workspace_id is not null)
CREATE UNIQUE INDEX memberships_workspace_level_unique
  ON memberships (organization_id, workspace_id, user_id)
  WHERE workspace_id IS NOT NULL;

CREATE INDEX workspaces_org_id_id_idx
  ON workspaces (organization_id, id);

CREATE INDEX memberships_org_id_id_idx
  ON memberships (organization_id, id);

CREATE INDEX memberships_org_user_idx
  ON memberships (organization_id, user_id);

COMMIT;

