-- Slice 1 contract test: canonical permit_status and memberships tenancy uniqueness.

DO $$
DECLARE
  actual text[];
  expected text[] := ARRAY[
    'draft',
    'submitted',
    'in_review',
    'corrections_required',
    'approved',
    'issued',
    'expired'
  ];
  u1 uuid;
  u2 uuid;
  org1 uuid;
  org2 uuid;
  ws1 uuid;
BEGIN
  SELECT array_agg(e.enumlabel ORDER BY e.enumsortorder)
  INTO actual
  FROM pg_enum e
  JOIN pg_type t ON t.oid = e.enumtypid
  WHERE t.typname = 'permit_status';

  IF actual IS DISTINCT FROM expected THEN
    RAISE EXCEPTION 'permit_status mismatch. expected=% actual=%', expected, actual;
  END IF;

  IF EXISTS (
    SELECT 1
    FROM pg_enum e
    JOIN pg_type t ON t.oid = e.enumtypid
    WHERE t.typname = 'permit_status' AND e.enumlabel = 'rejected'
  ) THEN
    RAISE EXCEPTION 'permit_status must not include rejected';
  END IF;

  INSERT INTO users(email, full_name) VALUES ('owner1@example.com', 'Owner 1') RETURNING id INTO u1;
  INSERT INTO users(email, full_name) VALUES ('owner2@example.com', 'Owner 2') RETURNING id INTO u2;

  INSERT INTO organizations(name, slug, created_by)
  VALUES ('Org One', 'org-one', u1)
  RETURNING id INTO org1;

  INSERT INTO organizations(name, slug, created_by)
  VALUES ('Org Two', 'org-two', u2)
  RETURNING id INTO org2;

  INSERT INTO workspaces(organization_id, name, is_default)
  VALUES (org1, 'Default', true)
  RETURNING id INTO ws1;

  INSERT INTO memberships(organization_id, workspace_id, user_id, role)
  VALUES (org1, NULL, u1, 'owner');

  -- Duplicate org-level membership must fail.
  BEGIN
    INSERT INTO memberships(organization_id, workspace_id, user_id, role)
    VALUES (org1, NULL, u1, 'admin');
    RAISE EXCEPTION 'expected duplicate org-level membership to fail';
  EXCEPTION WHEN unique_violation THEN
    NULL;
  END;

  INSERT INTO memberships(organization_id, workspace_id, user_id, role)
  VALUES (org1, ws1, u1, 'owner');

  -- Duplicate workspace-level membership must fail.
  BEGIN
    INSERT INTO memberships(organization_id, workspace_id, user_id, role)
    VALUES (org1, ws1, u1, 'pm');
    RAISE EXCEPTION 'expected duplicate workspace-level membership to fail';
  EXCEPTION WHEN unique_violation THEN
    NULL;
  END;

  -- Workspace/org mismatch must fail due to composite FK.
  BEGIN
    INSERT INTO memberships(organization_id, workspace_id, user_id, role)
    VALUES (org2, ws1, u2, 'owner');
    RAISE EXCEPTION 'expected cross-org workspace membership to fail';
  EXCEPTION WHEN foreign_key_violation THEN
    NULL;
  END;
END $$;

SELECT
  EXISTS (
    SELECT 1
    FROM pg_indexes
    WHERE schemaname = 'public'
      AND indexname = 'memberships_org_level_unique'
  ) AS has_memberships_org_level_unique,
  EXISTS (
    SELECT 1
    FROM pg_indexes
    WHERE schemaname = 'public'
      AND indexname = 'memberships_workspace_level_unique'
  ) AS has_memberships_workspace_level_unique;

