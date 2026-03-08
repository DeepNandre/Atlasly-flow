-- Stage 2 Slice 4 rollback
-- Reverts db/migrations/000026_stage2_sync_ops_controls.sql

begin;

drop table if exists status_transition_reviews;
drop table if exists status_reconciliation_runs;

commit;
