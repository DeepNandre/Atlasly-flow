-- Slice 7 contract test: future-moat instrumentation tables and tenant-safe FKs.

DO $$
DECLARE
  u1 uuid := '71000000-0000-0000-0000-000000000001';
  u2 uuid := '71000000-0000-0000-0000-000000000002';
  org1 uuid := '72000000-0000-0000-0000-000000000001';
  org2 uuid := '72000000-0000-0000-0000-000000000002';
  ws1 uuid := '73000000-0000-0000-0000-000000000001';
  ws2 uuid := '73000000-0000-0000-0000-000000000002';
  p1 uuid := '74000000-0000-0000-0000-000000000001';
  p2 uuid := '74000000-0000-0000-0000-000000000002';
  permit1 uuid := '75000000-0000-0000-0000-000000000001';
  permit2 uuid := '75000000-0000-0000-0000-000000000002';
  review1 uuid := '76000000-0000-0000-0000-000000000001';
  comment1 uuid := '77000000-0000-0000-0000-000000000001';
BEGIN
  INSERT INTO users(id, email, full_name) VALUES
    (u1, 'slice7-owner1@example.com', 'Slice7 Owner 1'),
    (u2, 'slice7-owner2@example.com', 'Slice7 Owner 2');

  INSERT INTO organizations(id, name, slug, created_by) VALUES
    (org1, 'Slice7 Org One', 'slice7-org-one', u1),
    (org2, 'Slice7 Org Two', 'slice7-org-two', u2);

  INSERT INTO workspaces(id, organization_id, name, is_default) VALUES
    (ws1, org1, 'Default', true),
    (ws2, org2, 'Default', true);

  INSERT INTO projects(id, organization_id, workspace_id, name, created_by) VALUES
    (p1, org1, ws1, 'Slice7 Project 1', u1),
    (p2, org2, ws2, 'Slice7 Project 2', u2);

  INSERT INTO permits(id, organization_id, project_id, permit_type, created_by) VALUES
    (permit1, org1, p1, 'building', u1),
    (permit2, org2, p2, 'building', u2);

  INSERT INTO permit_reviews(id, organization_id, permit_id, review_cycle, reviewer, outcome)
  VALUES (review1, org1, permit1, 1, 'city reviewer', 'needs-corrections');

  INSERT INTO ahj_comments(id, organization_id, permit_review_id, citation_text, discipline, severity)
  VALUES (comment1, org1, review1, 'Provide egress width details.', 'architectural', 'high');

  INSERT INTO code_citations(organization_id, ahj_comment_id, code_system, section, excerpt)
  VALUES (org1, comment1, 'IBC', '1005.3.2', 'Egress width requirements...');

  INSERT INTO review_outcomes(organization_id, permit_review_id, resolution_status, resolved_by, metadata)
  VALUES (org1, review1, 'open', u1, '{"ticket_id":"T-123"}'::jsonb);

  -- Cross-tenant review reference must fail.
  BEGIN
    INSERT INTO ahj_comments(organization_id, permit_review_id, citation_text)
    VALUES (org2, review1, 'Cross tenant should fail');
    RAISE EXCEPTION 'expected cross-tenant permit_review reference to fail';
  EXCEPTION WHEN foreign_key_violation THEN
    NULL;
  END;

  -- Duplicate review cycle on same permit must fail.
  BEGIN
    INSERT INTO permit_reviews(organization_id, permit_id, review_cycle)
    VALUES (org1, permit1, 1);
    RAISE EXCEPTION 'expected duplicate review cycle per permit to fail';
  EXCEPTION WHEN unique_violation THEN
    NULL;
  END;
END $$;

SELECT
  EXISTS (
    SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = 'permit_reviews_cycle_unique'
  ) AS has_permit_reviews_cycle_unique,
  EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename = 'permit_reviews' AND policyname = 'permit_reviews_select_pol'
  ) AS has_permit_reviews_rls;

