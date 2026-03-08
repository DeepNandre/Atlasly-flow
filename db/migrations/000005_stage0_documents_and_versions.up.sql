BEGIN;

CREATE TABLE documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  project_id uuid NOT NULL,
  latest_version_no integer NOT NULL DEFAULT 0,
  title text NOT NULL,
  category text NULL,
  created_by uuid NOT NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT documents_org_id_id_unique UNIQUE (organization_id, id),
  CONSTRAINT documents_project_fk
    FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id)
    ON DELETE CASCADE,
  CONSTRAINT documents_latest_version_no_chk CHECK (latest_version_no >= 0),
  CONSTRAINT documents_title_nonempty_chk CHECK (length(trim(title)) > 0)
);

CREATE TABLE document_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  document_id uuid NOT NULL,
  version_no integer NOT NULL,
  storage_key text NOT NULL,
  storage_bucket text NOT NULL,
  file_name text NOT NULL,
  file_size_bytes bigint NOT NULL,
  mime_type text NOT NULL,
  checksum_sha256 text NOT NULL,
  uploaded_by uuid NOT NULL REFERENCES users(id),
  uploaded_at timestamptz NOT NULL DEFAULT now(),
  virus_scan_status text NOT NULL DEFAULT 'pending',
  virus_scan_completed_at timestamptz NULL,
  ocr_status document_ocr_status NOT NULL DEFAULT 'uploaded',
  ocr_page_count integer NULL,
  ocr_error_code text NULL,
  ocr_completed_at timestamptz NULL,
  CONSTRAINT document_versions_org_id_id_unique UNIQUE (organization_id, id),
  CONSTRAINT document_versions_document_version_unique UNIQUE (document_id, version_no),
  CONSTRAINT document_versions_storage_location_unique UNIQUE (storage_bucket, storage_key),
  CONSTRAINT document_versions_document_fk
    FOREIGN KEY (organization_id, document_id)
    REFERENCES documents(organization_id, id)
    ON DELETE CASCADE,
  CONSTRAINT document_versions_version_no_chk CHECK (version_no > 0),
  CONSTRAINT document_versions_file_size_bytes_chk CHECK (file_size_bytes > 0),
  CONSTRAINT document_versions_file_name_nonempty_chk CHECK (length(trim(file_name)) > 0),
  CONSTRAINT document_versions_mime_type_nonempty_chk CHECK (length(trim(mime_type)) > 0),
  CONSTRAINT document_versions_checksum_nonempty_chk CHECK (length(trim(checksum_sha256)) > 0),
  CONSTRAINT document_versions_virus_scan_status_chk CHECK (
    virus_scan_status IN ('pending', 'clean', 'infected', 'failed')
  )
);

CREATE TABLE document_tags (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  document_id uuid NOT NULL,
  tag text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT document_tags_org_id_id_unique UNIQUE (organization_id, id),
  CONSTRAINT document_tags_document_tag_unique UNIQUE (document_id, tag),
  CONSTRAINT document_tags_document_fk
    FOREIGN KEY (organization_id, document_id)
    REFERENCES documents(organization_id, id)
    ON DELETE CASCADE,
  CONSTRAINT document_tags_tag_nonempty_chk CHECK (length(trim(tag)) > 0)
);

CREATE INDEX documents_org_id_id_idx
  ON documents (organization_id, id);

CREATE INDEX documents_project_id_idx
  ON documents (project_id);

CREATE INDEX document_versions_org_id_id_idx
  ON document_versions (organization_id, id);

CREATE INDEX document_versions_document_version_desc_idx
  ON document_versions (document_id, version_no DESC);

CREATE INDEX document_versions_ocr_work_queue_idx
  ON document_versions (ocr_status, uploaded_at)
  WHERE ocr_status IN ('queued_for_ocr', 'processing');

CREATE INDEX document_versions_virus_scan_pending_idx
  ON document_versions (virus_scan_status, uploaded_at)
  WHERE virus_scan_status IN ('pending', 'failed');

CREATE INDEX document_tags_org_id_id_idx
  ON document_tags (organization_id, id);

CREATE OR REPLACE FUNCTION enforce_document_version_sequence()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  current_latest integer;
BEGIN
  SELECT latest_version_no
  INTO current_latest
  FROM documents
  WHERE id = NEW.document_id
    AND organization_id = NEW.organization_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION
      'document % not found in organization %',
      NEW.document_id,
      NEW.organization_id
      USING ERRCODE = '23503';
  END IF;

  IF NEW.version_no <> current_latest + 1 THEN
    RAISE EXCEPTION
      'invalid document version sequence for document %, expected %, got %',
      NEW.document_id,
      current_latest + 1,
      NEW.version_no
      USING ERRCODE = '23514';
  END IF;

  UPDATE documents
  SET latest_version_no = NEW.version_no,
      updated_at = now()
  WHERE id = NEW.document_id
    AND organization_id = NEW.organization_id;

  RETURN NEW;
END;
$$;

CREATE TRIGGER documents_set_updated_at_trg
  BEFORE UPDATE ON documents
  FOR EACH ROW
  EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER document_versions_sequence_trg
  BEFORE INSERT ON document_versions
  FOR EACH ROW
  EXECUTE FUNCTION enforce_document_version_sequence();

COMMIT;

