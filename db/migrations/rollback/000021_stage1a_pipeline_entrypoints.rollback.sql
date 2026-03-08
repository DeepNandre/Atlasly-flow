-- Rollback for Stage 1A Slice 6 migration
BEGIN;

DROP FUNCTION IF EXISTS stage1a_finalize_extraction(uuid, uuid, integer, numeric, integer);
DROP FUNCTION IF EXISTS stage1a_create_comment_letter(uuid, uuid, uuid, uuid, text, text);

COMMIT;
