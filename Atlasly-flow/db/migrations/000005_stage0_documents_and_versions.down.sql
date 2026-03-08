BEGIN;

DROP TRIGGER IF EXISTS document_versions_sequence_trg ON document_versions;
DROP TRIGGER IF EXISTS documents_set_updated_at_trg ON documents;
DROP FUNCTION IF EXISTS enforce_document_version_sequence();

DROP TABLE IF EXISTS document_tags;
DROP TABLE IF EXISTS document_versions;
DROP TABLE IF EXISTS documents;

COMMIT;

