-- Stage 1B Slice 1 foundation migration (draft)
-- Purpose: deterministic task-generation idempotency and routing persistence.
-- Contract note: no event/API renames; uses existing domain_events envelope.

begin;

-- 1) Task columns required by Stage 1B
alter table tasks
  add column if not exists source_extraction_id uuid,
  add column if not exists auto_assigned boolean not null default false,
  add column if not exists assignment_confidence numeric(5,4);

alter table tasks
  drop constraint if exists tasks_assignment_confidence_range;
alter table tasks
  add constraint tasks_assignment_confidence_range
  check (
    assignment_confidence is null
    or (assignment_confidence >= 0 and assignment_confidence <= 1)
  );

-- FK to Stage 1A extraction records.
alter table tasks
  drop constraint if exists tasks_source_extraction_fk;
alter table tasks
  add constraint tasks_source_extraction_fk
  foreign key (source_extraction_id) references comment_extractions(id);

-- One task per extraction item per org under retries/races.
create unique index if not exists ux_tasks_org_source_extraction
  on tasks (organization_id, source_extraction_id)
  where source_extraction_id is not null;

-- 2) Routing rules
create table if not exists routing_rules (
  id uuid primary key,
  organization_id uuid not null,
  project_id uuid null,
  is_active boolean not null default false,
  priority integer not null,
  discipline text null,
  project_role text null,
  trade_partner_id uuid null,
  ahj_id uuid null,
  assignee_user_id uuid null,
  assignee_team_id uuid null,
  confidence_base numeric(5,4) not null default 0.7000,
  effective_from timestamptz not null default now(),
  effective_to timestamptz null,
  version integer not null default 1,
  rule_hash text not null,
  created_by uuid not null,
  updated_by uuid not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint routing_rules_priority_positive check (priority >= 0),
  constraint routing_rules_confidence_base_range check (confidence_base >= 0 and confidence_base <= 1),
  constraint routing_rules_assignee_xor check (
    (assignee_user_id is not null and assignee_team_id is null)
    or (assignee_user_id is null and assignee_team_id is not null)
  )
);

create index if not exists idx_routing_rules_project_discipline_active
  on routing_rules (project_id, discipline, is_active);

create unique index if not exists ux_routing_rules_active_priority_hash
  on routing_rules (organization_id, project_id, priority, rule_hash)
  where is_active = true;

-- 3) Reassignment feedback capture
create table if not exists task_assignment_feedback (
  id uuid primary key,
  organization_id uuid not null,
  project_id uuid not null,
  task_id uuid not null references tasks(id) on delete cascade,
  from_assignee_id uuid not null,
  to_assignee_id uuid not null,
  source_rule_id uuid null references routing_rules(id),
  source_confidence numeric(5,4) null,
  feedback_reason_code text not null,
  feedback_subreason text null,
  actor_user_id uuid not null,
  was_auto_assigned boolean not null default false,
  feature_snapshot jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint task_assignment_feedback_confidence_range check (
    source_confidence is null or (source_confidence >= 0 and source_confidence <= 1)
  ),
  constraint task_assignment_feedback_reassign_target_change check (
    from_assignee_id <> to_assignee_id
  ),
  constraint task_assignment_feedback_reason_code check (
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
  )
);

create index if not exists idx_task_assignment_feedback_org_created
  on task_assignment_feedback (organization_id, created_at);

-- 4) Escalation persistence
create table if not exists assignment_escalations (
  id uuid primary key,
  organization_id uuid not null,
  project_id uuid not null,
  task_id uuid not null references tasks(id) on delete cascade,
  policy_id uuid not null,
  current_level integer not null default 1,
  assigned_at timestamptz not null,
  ack_due_at timestamptz not null,
  next_escalation_at timestamptz null,
  last_notified_at timestamptz null,
  resolved_at timestamptz null,
  status text not null default 'OPEN',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint assignment_escalations_level_range check (current_level between 1 and 3),
  constraint assignment_escalations_status_valid check (
    status in ('OPEN', 'ACKNOWLEDGED', 'ESCALATED', 'RESOLVED', 'CANCELLED')
  )
);

create index if not exists idx_assignment_escalations_open_schedule
  on assignment_escalations (status, next_escalation_at)
  where status in ('OPEN', 'ESCALATED');

-- 5) Idempotent task generation run ledger
create table if not exists task_generation_runs (
  id uuid primary key,
  organization_id uuid not null,
  project_id uuid not null,
  letter_id uuid not null,
  idempotency_key text not null,
  request_hash text not null,
  status text not null,
  created_count integer not null default 0,
  existing_count integer not null default 0,
  task_ids jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  completed_at timestamptz null,
  constraint task_generation_runs_status_valid
    check (status in ('IN_PROGRESS', 'COMPLETED', 'FAILED')),
  constraint task_generation_runs_counts_non_negative
    check (created_count >= 0 and existing_count >= 0),
  unique (organization_id, idempotency_key)
);

create index if not exists idx_task_generation_runs_letter_created
  on task_generation_runs (organization_id, letter_id, created_at desc);

-- 6) Ensure source extraction is approved and tenant/project aligned.
create or replace function enforce_task_source_extraction_approved()
returns trigger
language plpgsql
as $$
declare
  extraction_status text;
  extraction_org_id uuid;
  extraction_project_id uuid;
begin
  if new.source_extraction_id is null then
    return new;
  end if;

  select ce.status, ce.organization_id, cl.project_id
    into extraction_status, extraction_org_id, extraction_project_id
  from comment_extractions ce
  join comment_letters cl on cl.id = ce.letter_id
  where ce.id = new.source_extraction_id;

  if extraction_status is null then
    raise exception 'source_extraction_id % not found', new.source_extraction_id;
  end if;

  if extraction_status <> 'approved' then
    raise exception 'source_extraction_id % is not approved (status=%)', new.source_extraction_id, extraction_status;
  end if;

  if extraction_org_id <> new.organization_id then
    raise exception 'source_extraction_id % organization mismatch', new.source_extraction_id;
  end if;

  if extraction_project_id <> new.project_id then
    raise exception 'source_extraction_id % project mismatch', new.source_extraction_id;
  end if;

  return new;
end;
$$;

drop trigger if exists trg_tasks_source_must_be_approved on tasks;
create trigger trg_tasks_source_must_be_approved
  before insert or update of source_extraction_id, organization_id, project_id
  on tasks
  for each row
  execute function enforce_task_source_extraction_approved();

-- 7) Outbox dedupe for Stage 1B generation event emission.
-- Assumes domain_events exists from Stage 0 with unique(organization_id, idempotency_key).
create index if not exists idx_domain_events_stage1b_pending
  on domain_events (status, created_at)
  where status in ('pending', 'failed')
    and event_type in (
      'tasks.bulk_created_from_extractions',
      'task.auto_assigned',
      'task.assignment_overdue'
    );

commit;
