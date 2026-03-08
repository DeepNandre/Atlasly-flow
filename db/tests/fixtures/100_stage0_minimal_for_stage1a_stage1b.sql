-- Minimal Stage 0 tables required for Stage 1A + Stage 1B migration contract testing.
-- This fixture is for local test harness only.

begin;

create table if not exists projects (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  name text not null,
  permit_type text not null,
  status text not null default 'active',
  created_by uuid not null references users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (status in ('active', 'archived'))
);

create index if not exists idx_projects_org_created
  on projects (organization_id, created_at desc);

create table if not exists documents (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  project_id uuid not null references projects(id) on delete cascade,
  latest_version_no integer not null default 0 check (latest_version_no >= 0),
  title text not null,
  category text,
  created_by uuid not null references users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_documents_project_created
  on documents (project_id, created_at desc);

create table if not exists tasks (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  project_id uuid not null references projects(id) on delete cascade,
  permit_id uuid null,
  title text not null,
  description text,
  discipline text,
  status task_status not null default 'todo',
  assignee_user_id uuid null references users(id),
  due_date date null,
  priority smallint not null default 3 check (priority between 1 and 5),
  created_by uuid not null references users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  version integer not null default 1
);

create index if not exists idx_tasks_project_status_updated
  on tasks(project_id, status, updated_at desc);

create table if not exists domain_events (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  aggregate_type text not null,
  aggregate_id uuid not null,
  event_type text not null,
  event_version integer not null,
  idempotency_key text not null,
  trace_id text,
  occurred_at timestamptz not null,
  payload jsonb not null,
  status event_status not null default 'pending',
  publish_attempts integer not null default 0,
  published_at timestamptz null,
  created_at timestamptz not null default now(),
  unique (organization_id, idempotency_key)
);

create index if not exists idx_domain_events_status_created
  on domain_events (status, created_at)
  where status in ('pending', 'failed');

create table if not exists event_consumer_dedup (
  consumer_name text not null,
  event_id uuid not null references domain_events(id) on delete cascade,
  processed_at timestamptz not null default now(),
  primary key (consumer_name, event_id)
);

commit;
