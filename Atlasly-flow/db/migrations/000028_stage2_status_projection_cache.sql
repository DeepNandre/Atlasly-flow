-- Stage 2 Slice 6
-- Purpose: add status projection cache for timeline/current-status reads.
-- Contract safety: shared event names/versions and API paths are unchanged.

begin;

create table if not exists permit_status_projections (
  permit_id uuid primary key,
  organization_id uuid not null,
  current_status text not null,
  source_event_id uuid references permit_status_events(id) on delete set null,
  confidence numeric(4,3) not null default 1.0,
  updated_at timestamptz not null default now(),
  check (current_status in ('submitted', 'in_review', 'corrections_required', 'approved', 'issued', 'expired')),
  check (confidence >= 0 and confidence <= 1)
);

create index if not exists idx_permit_status_projections_org_status_updated
  on permit_status_projections (organization_id, current_status, updated_at desc);

commit;
