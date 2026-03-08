-- Stage 2 Slice 7 rollback
-- Reverts db/migrations/000029_stage2_application_generation_runs.sql

begin;

drop table if exists permit_application_generation_runs;

commit;
