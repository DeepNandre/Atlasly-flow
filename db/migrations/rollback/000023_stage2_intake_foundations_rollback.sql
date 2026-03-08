-- Stage 2 Slice 1 rollback
-- Reverts db/migrations/000023_stage2_intake_foundations.sql

begin;

drop table if exists permit_applications;
drop table if exists intake_sessions;

commit;
