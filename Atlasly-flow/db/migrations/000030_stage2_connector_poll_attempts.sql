-- Stage 2 Slice 8
-- Purpose: connector runtime retry visibility and diagnostics.
-- Contract safety: shared event names/versions and API paths are unchanged.

begin;

create table if not exists connector_poll_attempts (
  id uuid primary key default gen_random_uuid(),
  sync_run_id uuid not null references portal_sync_runs(id) on delete cascade,
  attempt_number integer not null,
  status text not null,
  error_message text,
  attempted_at timestamptz not null default now(),
  finished_at timestamptz,
  check (attempt_number > 0),
  check (status in ('started', 'succeeded', 'failed', 'retrying'))
);

create unique index if not exists uq_connector_poll_attempts_run_attempt
  on connector_poll_attempts (sync_run_id, attempt_number);

create index if not exists idx_connector_poll_attempts_run_attempted
  on connector_poll_attempts (sync_run_id, attempted_at desc);

commit;
