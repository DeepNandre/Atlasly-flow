-- Stage 2 Slice 6 rollback
-- Reverts db/migrations/000028_stage2_status_projection_cache.sql

begin;

drop table if exists permit_status_projections;

commit;
