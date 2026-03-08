# Stage 1B: Ticketing and Routing

## Title
Stage 1B: Automated Ticket Creation and Discipline Routing

## Goal
Turn approved extraction records into actionable workflow tasks and route them to the right owners with minimal manual triage.

## Scope (In)
- One-click conversion from approved extractions to workflow tasks.
- Rule-based assignment by discipline, project role, and trade partner mapping.
- SLA reminders, reassignment, and escalation support.
- Feedback loop to capture manual routing corrections.

## Out of Scope
- Full AHJ portal synchronization.
- Municipal form generation.
- Fintech payout events.

## Dependencies
- Stage 1A extraction approval flow complete.
- Stage 0 task and notification primitives complete.
- Stage 0.5 connector framework for outbound assignment notifications.

## Data model changes

### Schema changes
- New tables: `routing_rules`, `task_assignment_feedback`, `assignment_escalations`.
- Additional columns: `tasks.source_extraction_id`, `tasks.auto_assigned`, `tasks.assignment_confidence`.
- Indexes:
  - `(project_id, discipline, is_active)` on `routing_rules`.
  - `(organization_id, created_at)` on `task_assignment_feedback`.

## APIs / interfaces

### REST endpoints
- `POST /comment-letters/{letterId}/create-tasks`: create tasks from approved extractions.
- `POST /routing-rules`: create/update assignment rule.
- `GET /routing-rules`: list effective routing rules by project/org.
- `POST /tasks/{taskId}/reassign`: manual override and feedback capture.
- `GET /api/stage1b/routing-audit`: explainable routing decisions and reassignment reason analytics.
- `POST /api/stage1b/escalation-tick`: retry-safe escalation scheduler tick (idempotent by tick key).

### Event contracts
- Producer: task generation service -> `tasks.bulk_created_from_extractions` with `letter_id`, `task_ids`, `created_count`.
- Producer: routing engine -> `task.auto_assigned` with `task_id`, `assignee_id`, `rule_id`, `confidence`.
- Producer: reminder service -> `task.assignment_overdue` with `task_id`, `assignee_id`, `overdue_by_hours`.

### Security constraints
- Rule management restricted to `owner`, `admin`, and `pm` roles.
- Reassignment requires project membership and task write permission.
- External notifications include least-privilege links and expiring tokens.

## Operational requirements
- Idempotent task generation to prevent duplicate tickets.
- Escalation scheduler for unacknowledged assignments.
- Routing simulation tool to preview assignment outcomes before enabling a rule.

## Acceptance criteria
- KPI: auto-assignment success >= 80% without manual reassignment for pilot customers.
- KPI: median triage time from letter approval to fully assigned tasks <= 10 minutes.
- Exit criteria: assignment overrides are tracked and available for model/rule tuning.

## Risks and mitigations
- Risk: ambiguous discipline mapping causes wrong assignee.
  - Mitigation: confidence threshold with manual review fallback queue.
- Risk: duplicate tasks from retries.
  - Mitigation: deterministic idempotency key by `letter_id` + `comment_id`.
- Risk: notification fatigue.
  - Mitigation: digest mode and suppression windows per user.

## Milestones (Week-by-week)
- Week 1: routing rule schema and task generation endpoint.
- Week 2: auto-assignment engine and confidence thresholds.
- Week 3: escalation/reminder workflows and reassignment feedback capture.
- Week 4: pilot KPI validation and hardening.
