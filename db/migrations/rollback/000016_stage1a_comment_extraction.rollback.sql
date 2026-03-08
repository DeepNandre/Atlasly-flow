-- Rollback for Stage 1A Slice 1 migration
BEGIN;

DROP INDEX IF EXISTS idx_extraction_reviews_letter_reviewed_at;
DROP INDEX IF EXISTS idx_comment_letters_org_status;
DROP INDEX IF EXISTS idx_comment_letters_project_created_at;
DROP INDEX IF EXISTS idx_comment_extractions_letter_status;

DROP TABLE IF EXISTS extraction_feedback;
DROP TABLE IF EXISTS extraction_reviews;
DROP TABLE IF EXISTS comment_extractions;
DROP TABLE IF EXISTS comment_letters;

COMMIT;
