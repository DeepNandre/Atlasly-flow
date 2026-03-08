-- Stage 2 Slice 3 rollback
-- Reverts db/migrations/000025_stage2_status_sync_foundations.sql

begin;

drop table if exists status_source_provenance;
drop table if exists permit_status_events;
drop table if exists portal_sync_runs;

commit;
