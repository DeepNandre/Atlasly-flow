-- Rollback for Stage 1A Slice 4 migration
BEGIN;

DROP FUNCTION IF EXISTS stage1a_approve_comment_letter(uuid, uuid);
DROP INDEX IF EXISTS idx_comment_letter_approval_snapshots_approved_at;
DROP TABLE IF EXISTS comment_letter_approval_snapshots;

COMMIT;
