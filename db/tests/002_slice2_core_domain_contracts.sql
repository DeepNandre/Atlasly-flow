-- Slice 2 contract test: core domain tenancy constraints and permit status transitions.

DO $$
DECLARE
  u1 uuid;
  u2 uuid;
  org1 uuid;
  org2 uuid;
  ws1 uuid;
  ws2 uuid;
  ahj1 uuid;
  p1 uuid;
  p2 uuid;
  t1 uuid;
BEGIN
  INSERT INTO users(email, full_name) VALUES ('slice2-owner1@example.com', 'Slice2 Owner 1') RETURNING id INTO u1;
  INSERT INTO users(email, full_name) VALUES ('slice2-owner2@example.com', 'Slice2 Owner 2') RETURNING id INTO u2;

  INSERT INTO organizations(name, slug, created_by)
  VALUES ('Slice2 Org One', 'slice2-org-one', u1)
  RETURNING id INTO org1;

  INSERT INTO organizations(name, slug, created_by)
  VALUES ('Slice2 Org Two', 'slice2-org-two', u2)
  RETURNING id INTO org2;

  INSERT INTO workspaces(organization_id, name, is_default)
  VALUES (org1, 'Default', true)
  RETURNING id INTO ws1;

  INSERT INTO workspaces(organization_id, name, is_default)
  VALUES (org2, 'Default', true)
  RETURNING id INTO ws2;

  INSERT INTO ahj_profiles(organization_id, name, jurisdiction_type, region)
  VALUES (org1, 'City of Austin', 'city', 'TX')
  RETURNING id INTO ahj1;

  -- Cross-tenant workspace reference in projects must fail.
  BEGIN
    INSERT INTO projects(organization_id, workspace_id, name, created_by)
    VALUES (org1, ws2, 'Bad Cross Tenant Project', u1);
    RAISE EXCEPTION 'expected cross-tenant workspace fk failure';
  EXCEPTION WHEN foreign_key_violation THEN
    NULL;
  END;

  INSERT INTO projects(organization_id, workspace_id, ahj_profile_id, name, project_code, created_by)
  VALUES (org1, ws1, ahj1, 'Warehouse Retrofit', 'WR-001', u1)
  RETURNING id INTO p1;

  INSERT INTO projects(organization_id, workspace_id, name, project_code, created_by)
  VALUES (org2, ws2, 'Secondary Project', 'WR-001', u2)
  RETURNING id INTO p2;

  -- project_code uniqueness is tenant scoped, so same code across different orgs is allowed.
  IF p1 IS NULL OR p2 IS NULL THEN
    RAISE EXCEPTION 'expected both projects to be created';
  END IF;

  INSERT INTO permits(organization_id, project_id, permit_type, created_by)
  VALUES (org1, p1, 'building', u1)
  RETURNING id INTO t1;

  -- Valid transition: draft -> submitted
  UPDATE permits SET status = 'submitted' WHERE id = t1;

  -- Invalid transition: submitted -> approved (must pass through in_review)
  BEGIN
    UPDATE permits SET status = 'approved' WHERE id = t1;
    RAISE EXCEPTION 'expected invalid transition submitted -> approved to fail';
  EXCEPTION WHEN check_violation THEN
    NULL;
  END;

  -- Valid transition chain
  UPDATE permits SET status = 'in_review' WHERE id = t1;
  UPDATE permits SET status = 'corrections_required' WHERE id = t1;
  UPDATE permits SET status = 'submitted' WHERE id = t1;
  UPDATE permits SET status = 'in_review' WHERE id = t1;
  UPDATE permits SET status = 'approved' WHERE id = t1;
  UPDATE permits SET status = 'issued' WHERE id = t1;
  UPDATE permits SET status = 'expired' WHERE id = t1;

  -- Expired is terminal.
  BEGIN
    UPDATE permits SET status = 'issued' WHERE id = t1;
    RAISE EXCEPTION 'expected expired -> issued to fail';
  EXCEPTION WHEN check_violation THEN
    NULL;
  END;
END $$;

DO $$
DECLARE
  p permits%ROWTYPE;
BEGIN
  SELECT * INTO p
  FROM permits
  WHERE permit_type = 'building'
  ORDER BY created_at DESC
  LIMIT 1;

  IF p.status <> 'expired' THEN
    RAISE EXCEPTION 'expected final permit status to be expired, got %', p.status;
  END IF;

  IF p.submitted_at IS NULL OR p.issued_at IS NULL OR p.expired_at IS NULL THEN
    RAISE EXCEPTION
      'expected submitted_at, issued_at, expired_at timestamps to be set (submitted_at=%, issued_at=%, expired_at=%)',
      p.submitted_at, p.issued_at, p.expired_at;
  END IF;
END $$;

SELECT
  EXISTS (
    SELECT 1
    FROM pg_proc
    WHERE proname = 'app_is_valid_permit_status_transition'
  ) AS has_permit_transition_fn,
  EXISTS (
    SELECT 1
    FROM pg_trigger
    WHERE tgname = 'permits_status_transition_trg'
  ) AS has_permit_transition_trigger;

