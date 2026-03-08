-- Stage 2 Slice 5 rollback
-- Reverts db/migrations/000027_stage2_normalization_and_drift_rules.sql

begin;

drop table if exists status_drift_alerts;
drop table if exists status_normalization_rules;

commit;
