-- Slice 3 contract test: document/version/tag constraints and sequencing.

DO $$
DECLARE
  u1 uuid;
  u2 uuid;
  org1 uuid;
  org2 uuid;
  ws1 uuid;
  ws2 uuid;
  p1 uuid;
  d1 uuid;
BEGIN
  INSERT INTO users(email, full_name) VALUES ('slice3-owner1@example.com', 'Slice3 Owner 1') RETURNING id INTO u1;
  INSERT INTO users(email, full_name) VALUES ('slice3-owner2@example.com', 'Slice3 Owner 2') RETURNING id INTO u2;

  INSERT INTO organizations(name, slug, created_by)
  VALUES ('Slice3 Org One', 'slice3-org-one', u1)
  RETURNING id INTO org1;

  INSERT INTO organizations(name, slug, created_by)
  VALUES ('Slice3 Org Two', 'slice3-org-two', u2)
  RETURNING id INTO org2;

  INSERT INTO workspaces(organization_id, name, is_default)
  VALUES (org1, 'Default', true)
  RETURNING id INTO ws1;

  INSERT INTO workspaces(organization_id, name, is_default)
  VALUES (org2, 'Default', true)
  RETURNING id INTO ws2;

  INSERT INTO projects(organization_id, workspace_id, name, created_by)
  VALUES (org1, ws1, 'Slice3 Project', u1)
  RETURNING id INTO p1;

  INSERT INTO documents(organization_id, project_id, title, category, created_by)
  VALUES (org1, p1, 'Architectural Plans', 'plans', u1)
  RETURNING id INTO d1;

  -- First version must be 1.
  BEGIN
    INSERT INTO document_versions(
      organization_id, document_id, version_no, storage_key, storage_bucket,
      file_name, file_size_bytes, mime_type, checksum_sha256, uploaded_by
    ) VALUES (
      org1, d1, 2, 'org1/p1/d1/v2.pdf', 'permits-docs',
      'v2.pdf', 2048, 'application/pdf', 'sha-v2', u1
    );
    RAISE EXCEPTION 'expected version sequence check to fail on first insert with version 2';
  EXCEPTION WHEN check_violation THEN
    NULL;
  END;

  INSERT INTO document_versions(
    organization_id, document_id, version_no, storage_key, storage_bucket,
    file_name, file_size_bytes, mime_type, checksum_sha256, uploaded_by
  ) VALUES (
    org1, d1, 1, 'org1/p1/d1/v1.pdf', 'permits-docs',
    'v1.pdf', 1024, 'application/pdf', 'sha-v1', u1
  );

  -- Cross-tenant insert must fail.
  BEGIN
    INSERT INTO document_versions(
      organization_id, document_id, version_no, storage_key, storage_bucket,
      file_name, file_size_bytes, mime_type, checksum_sha256, uploaded_by
    ) VALUES (
      org2, d1, 1, 'org2/p9/d1/v1.pdf', 'permits-docs',
      'x-v1.pdf', 1024, 'application/pdf', 'sha-cross', u2
    );
    RAISE EXCEPTION 'expected cross-tenant document version insert to fail';
  EXCEPTION WHEN foreign_key_violation THEN
    NULL;
  END;

  INSERT INTO document_versions(
    organization_id, document_id, version_no, storage_key, storage_bucket,
    file_name, file_size_bytes, mime_type, checksum_sha256, uploaded_by, ocr_status
  ) VALUES (
    org1, d1, 2, 'org1/p1/d1/v2.pdf', 'permits-docs',
    'v2.pdf', 3072, 'application/pdf', 'sha-v2-ok', u1, 'queued_for_ocr'
  );

  -- Duplicate storage location must fail.
  BEGIN
    INSERT INTO document_versions(
      organization_id, document_id, version_no, storage_key, storage_bucket,
      file_name, file_size_bytes, mime_type, checksum_sha256, uploaded_by
    ) VALUES (
      org1, d1, 3, 'org1/p1/d1/v2.pdf', 'permits-docs',
      'dup.pdf', 4096, 'application/pdf', 'sha-dup', u1
    );
    RAISE EXCEPTION 'expected duplicate storage location to fail';
  EXCEPTION WHEN unique_violation THEN
    NULL;
  END;

  INSERT INTO document_tags(organization_id, document_id, tag)
  VALUES (org1, d1, 'architectural');

  BEGIN
    INSERT INTO document_tags(organization_id, document_id, tag)
    VALUES (org1, d1, 'architectural');
    RAISE EXCEPTION 'expected duplicate document tag to fail';
  EXCEPTION WHEN unique_violation THEN
    NULL;
  END;
END $$;

DO $$
DECLARE
  d documents%ROWTYPE;
  v document_versions%ROWTYPE;
BEGIN
  SELECT *
  INTO d
  FROM documents
  WHERE title = 'Architectural Plans'
  ORDER BY created_at DESC
  LIMIT 1;

  IF d.latest_version_no <> 2 THEN
    RAISE EXCEPTION 'expected latest_version_no=2, got %', d.latest_version_no;
  END IF;

  SELECT *
  INTO v
  FROM document_versions
  WHERE document_id = d.id
  ORDER BY version_no DESC
  LIMIT 1;

  IF v.ocr_status <> 'queued_for_ocr' THEN
    RAISE EXCEPTION 'expected latest ocr_status=queued_for_ocr, got %', v.ocr_status;
  END IF;

  IF v.virus_scan_status <> 'pending' THEN
    RAISE EXCEPTION 'expected default virus_scan_status=pending, got %', v.virus_scan_status;
  END IF;
END $$;

SELECT
  EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'document_versions_sequence_trg'
  ) AS has_document_sequence_trigger,
  EXISTS (
    SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = 'document_versions_ocr_work_queue_idx'
  ) AS has_ocr_work_queue_index;

