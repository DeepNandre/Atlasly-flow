-- Stage 2 Slice 2 rollback
-- Reverts db/migrations/000024_stage2_requirements_mappings_connectors.sql

begin;

drop table if exists connector_credentials;
drop table if exists application_field_mappings;
drop table if exists ahj_requirements;

commit;
