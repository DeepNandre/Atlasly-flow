# Stage 1B Slice 1 Rollback Runbook

Date: 2026-03-03
Owner: Agent-4

## Rollback Goals
- Stop automated task generation/routing safely.
- Preserve data integrity and auditability.
- Avoid duplicate or orphaned task records.

## Trigger Conditions
- Spike in generation failures.
- Duplicate task invariant breach.
- Event publish/consume instability on Stage 1B events.
- Reassignment writes failing integrity checks.

## Runtime Rollback (No Data Loss)
1. Disable feature flag `routing_auto_assign_enabled` for all projects.
2. Pause scheduler for assignment escalation jobs.
3. Keep `POST /comment-letters/{letterId}/create-tasks` behind admin-only control or disable temporarily.
4. Route all new tasks to manual triage queue.

## Data Safety Checks
- Verify uniqueness invariant still holds:
  - no duplicates by `(organization_id, source_extraction_id)`.
- Verify no stuck generation runs:
  - `task_generation_runs.status = 'IN_PROGRESS'` older than threshold.
- Verify outbox health:
  - pending/failed `domain_events` for Stage 1B types do not grow unbounded.

## Schema Rollback Guidance
- Prefer forward-fix over destructive rollback.
- If forced rollback is required:
  - first disable writers and schedulers.
  - archive `routing_rules`, `task_assignment_feedback`, `assignment_escalations`, `task_generation_runs`.
  - only then drop added objects in reverse dependency order.
- Do not drop `tasks.source_extraction_id` until archive confirms recovery path.

## Recovery Path
1. Re-enable create-tasks in manual approval mode only.
2. Replay failed `domain_events` with dedupe protections.
3. Re-enable auto-assignment per pilot project after contract tests pass.
