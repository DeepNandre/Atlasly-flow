-- Rollback for Stage 1A Slice 2 migration
BEGIN;

DROP INDEX IF EXISTS idx_comment_letter_event_emissions_letter_emitted;
DROP TABLE IF EXISTS comment_letter_event_emissions;

DROP TRIGGER IF EXISTS trg_stage1a_comment_letters_transition ON comment_letters;
DROP FUNCTION IF EXISTS stage1a_comment_letters_enforce_transition();
DROP FUNCTION IF EXISTS stage1a_is_valid_transition(text, text);

COMMIT;
