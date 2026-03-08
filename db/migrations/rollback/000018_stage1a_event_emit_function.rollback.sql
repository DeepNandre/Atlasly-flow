-- Rollback for Stage 1A Slice 3 migration
BEGIN;

DROP FUNCTION IF EXISTS stage1a_emit_event(uuid, text, jsonb, text, text);
DROP FUNCTION IF EXISTS stage1a_build_event_idempotency_key(uuid, text, integer);

COMMIT;
