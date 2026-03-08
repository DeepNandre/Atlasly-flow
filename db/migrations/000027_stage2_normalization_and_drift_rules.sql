-- Stage 2 Slice 5
-- Purpose: add runtime-configurable normalization rules and drift alert persistence.
-- Contract safety: shared event names/versions and API paths are unchanged.

begin;

create table if not exists status_normalization_rules (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null,
  connector text,
  ahj_id text,
  raw_pattern text not null,
  match_type text not null default 'regex',
  normalized_status text not null,
  confidence_score numeric(4,3) not null,
  priority integer not null default 100,
  is_active boolean not null default true,
  ruleset_version text not null default 'v1',
  created_by uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (connector is null or connector in ('accela_api', 'opengov_api', 'cloudpermit_portal_runner')),
  check (match_type in ('exact', 'regex', 'lexical')),
  check (normalized_status in ('submitted', 'in_review', 'corrections_required', 'approved', 'issued', 'expired')),
  check (confidence_score >= 0 and confidence_score <= 1),
  check (priority > 0)
);

create index if not exists idx_status_norm_rules_lookup
  on status_normalization_rules (organization_id, connector, ahj_id, is_active, priority asc);

create table if not exists status_drift_alerts (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null,
  permit_id uuid,
  connector text,
  ahj_id text,
  drift_type text not null,
  severity text not null default 'medium',
  status text not null default 'open',
  details_json jsonb not null default '{}'::jsonb,
  detected_at timestamptz not null default now(),
  resolved_at timestamptz,
  resolved_by uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (connector is null or connector in ('accela_api', 'opengov_api', 'cloudpermit_portal_runner')),
  check (drift_type in ('mapping_drift', 'source_drift', 'timeline_gap')),
  check (severity in ('low', 'medium', 'high')),
  check (status in ('open', 'acknowledged', 'resolved')),
  check (
    (status = 'resolved' and resolved_at is not null and resolved_by is not null)
    or (status <> 'resolved')
  )
);

create index if not exists idx_status_drift_alerts_org_detected
  on status_drift_alerts (organization_id, detected_at desc);

create index if not exists idx_status_drift_alerts_open
  on status_drift_alerts (organization_id, status, severity, detected_at desc)
  where status <> 'resolved';

commit;
