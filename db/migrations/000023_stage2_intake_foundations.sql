-- Stage 2 Slice 1
-- Purpose: establish intake and permit-application persistence foundations.
-- Contract safety: this migration does not rename or remove shared enums/events/APIs.

begin;

-- Optional extension for UUID generation in local/dev databases.
create extension if not exists pgcrypto;

-- Intake session state machine for guided permit intake.
create table if not exists intake_sessions (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null,
  project_id uuid not null,
  permit_type text not null,
  ahj_id text,
  current_step text not null,
  answers_json jsonb not null default '{}'::jsonb,
  status text not null default 'in_progress',
  version integer not null default 1,
  completed_at timestamptz,
  created_by uuid,
  updated_by uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (permit_type in ('commercial_ti', 'rooftop_solar', 'electrical_service_upgrade')),
  check (status in ('in_progress', 'completed', 'abandoned')),
  check (
    (status = 'completed' and completed_at is not null)
    or (status <> 'completed')
  )
);

create index if not exists idx_intake_sessions_project_step
  on intake_sessions (project_id, current_step);

create index if not exists idx_intake_sessions_org_project_created
  on intake_sessions (organization_id, project_id, created_at desc);

-- Canonical application payload generated from intake and project metadata.
create table if not exists permit_applications (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null,
  project_id uuid not null,
  permit_id uuid not null,
  intake_session_id uuid not null references intake_sessions(id) on delete restrict,
  permit_type text not null,
  ahj_id text not null,
  application_payload_json jsonb not null,
  validation_summary_json jsonb not null default '{"status":"pass","errors":[],"warnings":[]}'::jsonb,
  requirements_version_id uuid,
  mapping_bundle_version text,
  generator_version text not null default 'v1',
  generated_at timestamptz not null default now(),
  created_by uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (permit_type in ('commercial_ti', 'rooftop_solar', 'electrical_service_upgrade'))
);

create index if not exists idx_permit_applications_permit_generated
  on permit_applications (permit_id, generated_at desc);

create index if not exists idx_permit_applications_org_project
  on permit_applications (organization_id, project_id, generated_at desc);

commit;
