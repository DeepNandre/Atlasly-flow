-- Stage 1B Slice 1 migration
-- Purpose: deterministic ticket generation, routing persistence, and reassignment feedback integrity.
-- Contract safety: does not rename/remove shared enums, event names, or API paths.

begin;

-- Stage 1B task metadata.
alter table tasks
  add column if not exists source_extraction_id uuid,
  add column if not exists auto_assigned boolean not null default false,
  add column if not exists assignment_confidence numeric(5,4);

alter table tasks
  drop constraint if exists tasks_assignment_confidence_range_chk;
alter table tasks
  add constraint tasks_assignment_confidence_range_chk
  check (
    assignment_confidence is null
    or (assignment_confidence >= 0 and assignment_confidence <= 1)
  );

alter table tasks
  drop constraint if exists tasks_source_extraction_fk;
alter table tasks
  add constraint tasks_source_extraction_fk
  foreign key (source_extraction_id) references comment_extractions(id);

-- One generated task per approved extraction item.
create unique index if not exists ux_tasks_org_source_extraction
  on tasks (organization_id, source_extraction_id)
  where source_extraction_id is not null;

-- Routing rule store.
create table if not exists routing_rules (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  project_id uuid null references projects(id) on delete cascade,
  is_active boolean not null default false,
  priority integer not null check (priority >= 0),
  discipline text null,
  project_role text null,
  trade_partner_id uuid null,
  ahj_id text null,
  assignee_user_id uuid null references users(id),
  assignee_team_id uuid null,
  confidence_base numeric(5,4) not null default 0.7000 check (confidence_base >= 0 and confidence_base <= 1),
  effective_from timestamptz not null default now(),
  effective_to timestamptz null,
  version integer not null default 1 check (version > 0),
  rule_hash text not null,
  created_by uuid not null references users(id),
  updated_by uuid not null references users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint routing_rules_assignee_xor_chk check (
    (assignee_user_id is not null and assignee_team_id is null)
    or (assignee_user_id is null and assignee_team_id is not null)
  ),
  constraint routing_rules_effective_window_chk check (
    effective_to is null or effective_to > effective_from
  )
);

create index if not exists idx_routing_rules_project_discipline_active
  on routing_rules(project_id, discipline, is_active);

create unique index if not exists ux_routing_rules_active_priority_hash
  on routing_rules (organization_id, project_id, priority, rule_hash)
  where is_active = true;

-- Reassignment feedback capture.
create table if not exists task_assignment_feedback (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  project_id uuid not null references projects(id) on delete cascade,
  task_id uuid not null references tasks(id) on delete cascade,
  from_assignee_id uuid not null references users(id),
  to_assignee_id uuid not null references users(id),
  source_rule_id uuid null references routing_rules(id) on delete set null,
  source_confidence numeric(5,4) null check (source_confidence is null or (source_confidence >= 0 and source_confidence <= 1)),
  feedback_reason_code text not null check (
    feedback_reason_code in (
      'WRONG_DISCIPLINE',
      'WRONG_TRADE_PARTNER',
      'WRONG_PROJECT_ROLE',
      'ASSIGNEE_UNAVAILABLE',
      'MISSING_RULE',
      'RULE_PRIORITY_ISSUE',
      'TEMP_CAPACITY_REDIRECT',
      'OTHER_VERIFIED'
    )
  ),
  feedback_subreason text null,
  actor_user_id uuid not null references users(id),
  was_auto_assigned boolean not null default false,
  feature_snapshot jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint task_assignment_feedback_assignee_change_chk check (from_assignee_id <> to_assignee_id)
);

create index if not exists idx_task_assignment_feedback_org_created
  on task_assignment_feedback(organization_id, created_at);

-- SLA policy + escalation state.
create table if not exists routing_sla_policies (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  project_id uuid null references projects(id) on delete cascade,
  name text not null,
  ack_minutes_l1 integer not null default 120 check (ack_minutes_l1 > 0),
  ack_minutes_l2 integer not null default 240 check (ack_minutes_l2 > 0),
  ack_minutes_l3 integer not null default 480 check (ack_minutes_l3 > 0),
  business_hours_only boolean not null default false,
  suppression_windows jsonb not null default '[]'::jsonb,
  max_levels integer not null default 3 check (max_levels between 1 and 3),
  created_by uuid null references users(id),
  updated_by uuid null references users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, project_id, name)
);

create table if not exists assignment_escalations (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  project_id uuid not null references projects(id) on delete cascade,
  task_id uuid not null references tasks(id) on delete cascade,
  policy_id uuid not null references routing_sla_policies(id) on delete restrict,
  current_level integer not null default 1 check (current_level between 1 and 3),
  assigned_at timestamptz not null,
  ack_due_at timestamptz not null,
  next_escalation_at timestamptz null,
  last_notified_at timestamptz null,
  resolved_at timestamptz null,
  status text not null default 'OPEN' check (status in ('OPEN', 'ACKNOWLEDGED', 'ESCALATED', 'RESOLVED', 'CANCELLED')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_assignment_escalations_open_schedule
  on assignment_escalations(status, next_escalation_at)
  where status in ('OPEN', 'ESCALATED');

-- Idempotent generation run ledger.
create table if not exists task_generation_runs (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  project_id uuid not null references projects(id) on delete cascade,
  letter_id uuid not null references comment_letters(id) on delete cascade,
  idempotency_key text not null,
  request_hash text not null,
  status text not null check (status in ('IN_PROGRESS', 'COMPLETED', 'FAILED')),
  created_count integer not null default 0 check (created_count >= 0),
  existing_count integer not null default 0 check (existing_count >= 0),
  task_ids jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  completed_at timestamptz null,
  unique (organization_id, idempotency_key)
);

create index if not exists idx_task_generation_runs_org_letter_created
  on task_generation_runs(organization_id, letter_id, created_at desc);

-- Guard: only approved extraction snapshots can create tasks,
-- and extraction's organization/project must match the task.
create or replace function stage1b_enforce_task_source_extraction()
returns trigger
language plpgsql
as $$
declare
  extraction_status text;
  letter_org_id uuid;
  letter_project_id uuid;
begin
  if new.source_extraction_id is null then
    return new;
  end if;

  select ce.status, cl.organization_id, cl.project_id
    into extraction_status, letter_org_id, letter_project_id
  from comment_extractions ce
  join comment_letters cl on cl.id = ce.letter_id
  where ce.id = new.source_extraction_id;

  if extraction_status is null then
    raise exception 'source_extraction_id % not found', new.source_extraction_id;
  end if;

  if extraction_status <> 'approved_snapshot' then
    raise exception 'source_extraction_id % is not approved_snapshot (status=%)', new.source_extraction_id, extraction_status;
  end if;

  if letter_org_id <> new.organization_id then
    raise exception 'source_extraction_id % organization mismatch', new.source_extraction_id;
  end if;

  if letter_project_id <> new.project_id then
    raise exception 'source_extraction_id % project mismatch', new.source_extraction_id;
  end if;

  return new;
end;
$$;

drop trigger if exists trg_stage1b_tasks_source_guard on tasks;
create trigger trg_stage1b_tasks_source_guard
  before insert or update of source_extraction_id, organization_id, project_id
  on tasks
  for each row
  execute function stage1b_enforce_task_source_extraction();

-- Stage 1B event operability index; preserves canonical names/versions from shared contracts.
create index if not exists idx_domain_events_stage1b_pending
  on domain_events(status, created_at)
  where status in ('pending', 'failed')
    and event_type in (
      'tasks.bulk_created_from_extractions',
      'task.auto_assigned',
      'task.assignment_overdue'
    );

commit;
