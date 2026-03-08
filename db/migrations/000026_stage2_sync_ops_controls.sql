-- Stage 2 Slice 4
-- Purpose: add reconciliation run tracking and invalid-transition review queue.
-- Contract safety: no shared enum/event/API names are changed.

begin;

create table if not exists status_reconciliation_runs (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null,
  connector text,
  ahj_id text,
  run_started_at timestamptz not null default now(),
  run_finished_at timestamptz,
  status text not null default 'running',
  totals_json jsonb not null default '{"checked":0,"matched":0,"drifted":0}'::jsonb,
  mismatch_summary_json jsonb not null default '[]'::jsonb,
  ruleset_version text not null,
  created_by uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (connector is null or connector in ('accela_api', 'opengov_api', 'cloudpermit_portal_runner')),
  check (status in ('running', 'matched', 'mismatched', 'failed', 'partial')),
  check (
    (run_finished_at is null and status = 'running')
    or (run_finished_at is not null and status <> 'running')
  )
);

create index if not exists idx_status_recon_runs_org_started
  on status_reconciliation_runs (organization_id, run_started_at desc);

create index if not exists idx_status_recon_runs_connector_started
  on status_reconciliation_runs (connector, organization_id, run_started_at desc)
  where connector is not null;

create table if not exists status_transition_reviews (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null,
  permit_id uuid not null,
  status_event_id uuid not null references permit_status_events(id) on delete cascade,
  from_status text not null,
  to_status text not null,
  rejection_reason text not null,
  resolution_state text not null default 'open',
  resolution_notes text,
  resolved_by uuid,
  resolved_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (from_status in ('submitted', 'in_review', 'corrections_required', 'approved', 'issued', 'expired')),
  check (to_status in ('submitted', 'in_review', 'corrections_required', 'approved', 'issued', 'expired')),
  check (resolution_state in ('open', 'accepted_override', 'dismissed')),
  check (
    (resolution_state = 'open' and resolved_at is null and resolved_by is null)
    or (resolution_state <> 'open' and resolved_at is not null and resolved_by is not null)
  )
);

create index if not exists idx_status_transition_reviews_permit_state
  on status_transition_reviews (permit_id, resolution_state, created_at desc);

create unique index if not exists uq_status_transition_reviews_event_once
  on status_transition_reviews (status_event_id);

commit;
