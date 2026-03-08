-- Stage 1B Slice 1 rollback
-- Prefer forward-fix in production. Use only when Stage 1B writers are disabled.

begin;

drop index if exists idx_domain_events_stage1b_pending;

drop trigger if exists trg_stage1b_tasks_source_guard on tasks;
drop function if exists stage1b_enforce_task_source_extraction();

drop index if exists idx_task_generation_runs_org_letter_created;
drop table if exists task_generation_runs;

drop index if exists idx_assignment_escalations_open_schedule;
drop table if exists assignment_escalations;

drop table if exists routing_sla_policies;

drop index if exists idx_task_assignment_feedback_org_created;
drop table if exists task_assignment_feedback;

drop index if exists ux_routing_rules_active_priority_hash;
drop index if exists idx_routing_rules_project_discipline_active;
drop table if exists routing_rules;

drop index if exists ux_tasks_org_source_extraction;

alter table tasks
  drop constraint if exists tasks_source_extraction_fk;

alter table tasks
  drop constraint if exists tasks_assignment_confidence_range_chk;

alter table tasks
  drop column if exists assignment_confidence,
  drop column if exists auto_assigned,
  drop column if exists source_extraction_id;

commit;
