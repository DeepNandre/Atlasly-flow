-- Stage 2 Slice 3
-- Purpose: add connector polling run tracking, status event capture, and source provenance.
-- Contract safety: shared enum/event/API names remain unchanged.

begin;

create table if not exists portal_sync_runs (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null,
  connector text not null,
  ahj_id text not null,
  run_started_at timestamptz not null default now(),
  run_finished_at timestamptz,
  status text not null default 'running',
  checkpoint jsonb,
  error_summary jsonb,
  trigger_source text not null default 'scheduler',
  created_by uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (connector in ('accela_api', 'opengov_api', 'cloudpermit_portal_runner')),
  check (status in ('running', 'succeeded', 'failed', 'partial', 'cancelled')),
  check (
    (run_finished_at is null and status = 'running')
    or (run_finished_at is not null and status <> 'running')
  )
);

create index if not exists idx_portal_sync_runs_connector_org_started
  on portal_sync_runs (connector, organization_id, run_started_at);

create index if not exists idx_portal_sync_runs_org_status_started
  on portal_sync_runs (organization_id, status, run_started_at desc);

create table if not exists permit_status_events (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null,
  permit_id uuid not null,
  sync_run_id uuid references portal_sync_runs(id) on delete set null,
  raw_status text not null,
  normalized_status text,
  source text not null,
  confidence numeric(4,3) not null,
  observed_at timestamptz not null,
  parser_version text,
  event_hash text not null,
  ingestion_payload jsonb,
  created_at timestamptz not null default now(),
  check (confidence >= 0 and confidence <= 1),
  check (
    normalized_status is null
    or normalized_status in ('submitted', 'in_review', 'corrections_required', 'approved', 'issued', 'expired')
  ),
  check (char_length(event_hash) >= 16)
);

create index if not exists idx_permit_status_events_permit_observed
  on permit_status_events (permit_id, observed_at);

create index if not exists idx_permit_status_events_org_source_observed
  on permit_status_events (organization_id, source, observed_at desc);

create unique index if not exists uq_permit_status_events_org_hash
  on permit_status_events (organization_id, event_hash);

create table if not exists status_source_provenance (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null,
  status_event_id uuid not null references permit_status_events(id) on delete cascade,
  source_type text not null,
  source_ref text not null,
  source_payload_hash text not null,
  parser_version text,
  extracted_at timestamptz,
  ingested_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  check (source_type in ('api', 'portal', 'vendor', 'manual')),
  check (char_length(source_payload_hash) >= 16)
);

create index if not exists idx_status_source_provenance_event_ingested
  on status_source_provenance (status_event_id, ingested_at desc);

create index if not exists idx_status_source_provenance_org_type
  on status_source_provenance (organization_id, source_type, ingested_at desc);

commit;
