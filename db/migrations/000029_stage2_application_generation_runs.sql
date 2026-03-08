-- Stage 2 Slice 7
-- Purpose: add generation-run idempotency tracking for permit application generation.
-- Contract safety: shared event names/versions and API paths are unchanged.

begin;

create table if not exists permit_application_generation_runs (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null,
  permit_id uuid not null,
  intake_session_id uuid not null references intake_sessions(id) on delete restrict,
  form_template_id text not null,
  idempotency_key text not null,
  run_status text not null default 'completed',
  generated_application_id uuid references permit_applications(id) on delete set null,
  created_at timestamptz not null default now(),
  unique (organization_id, idempotency_key),
  check (run_status in ('completed', 'failed', 'replayed'))
);

create index if not exists idx_permit_app_generation_runs_permit_created
  on permit_application_generation_runs (permit_id, created_at desc);

commit;
