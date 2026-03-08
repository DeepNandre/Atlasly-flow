-- Rollback for Stage 1A Slice 5 migration
BEGIN;

DROP FUNCTION IF EXISTS stage1a_get_approval_snapshot(uuid);
DROP FUNCTION IF EXISTS stage1a_list_comment_extractions(uuid);
DROP FUNCTION IF EXISTS stage1a_get_comment_letter_status(uuid);

COMMIT;
