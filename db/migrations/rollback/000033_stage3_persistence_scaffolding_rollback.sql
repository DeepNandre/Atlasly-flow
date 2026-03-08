-- Rollback for Stage 3 Slice 5 persistence scaffolding

BEGIN;

DROP INDEX IF EXISTS idx_financial_events_org_instruction_occurred;
DROP INDEX IF EXISTS ux_reconciliation_runs_org_provider_started;

ALTER TABLE IF EXISTS reconciliation_runs
  DROP CONSTRAINT IF EXISTS chk_reconciliation_run_status;

ALTER TABLE IF EXISTS payout_instructions
  DROP CONSTRAINT IF EXISTS chk_payout_instruction_state;

DROP INDEX IF EXISTS idx_stage3_outbox_publish_state_created;
DROP TABLE IF EXISTS stage3_event_outbox;

COMMIT;
