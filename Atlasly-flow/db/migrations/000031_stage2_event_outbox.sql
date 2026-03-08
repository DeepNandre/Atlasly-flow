-- Stage 2 Slice 9
-- Purpose: dedicated Stage 2 event outbox for connector/intake/application events.
-- Contract safety: shared event names/versions and API paths are unchanged.

begin;

create table if not exists stage2_event_outbox (
  event_id uuid primary key default gen_random_uuid(),
  organization_id uuid not null,
  event_type text not null,
  event_version integer not null,
  aggregate_type text not null,
  aggregate_id text not null,
  idempotency_key text not null,
  trace_id text not null,
  payload jsonb not null,
  occurred_at timestamptz not null,
  produced_by text not null,
  publish_state text not null default 'pending',
  publish_attempts integer not null default 0,
  published_at timestamptz,
  created_at timestamptz not null default now(),
  check (event_version > 0),
  check (publish_state in ('pending', 'published', 'failed', 'dead_letter')),
  unique (organization_id, idempotency_key, event_type)
);

create index if not exists idx_stage2_outbox_publish_state_created
  on stage2_event_outbox (publish_state, created_at)
  where publish_state in ('pending', 'failed');

commit;
