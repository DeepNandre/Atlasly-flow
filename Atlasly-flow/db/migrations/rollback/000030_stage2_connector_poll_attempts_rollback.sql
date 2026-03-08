-- Stage 2 Slice 8 rollback
-- Reverts db/migrations/000030_stage2_connector_poll_attempts.sql

begin;

drop table if exists connector_poll_attempts;

commit;
