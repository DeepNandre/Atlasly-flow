-- Stage 2 Slice 9 rollback
-- Reverts db/migrations/000031_stage2_event_outbox.sql

begin;

drop table if exists stage2_event_outbox;

commit;
