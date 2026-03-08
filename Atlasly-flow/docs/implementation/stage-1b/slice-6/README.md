# Stage 1B Slice 6

Status: Built
Date: 2026-03-03
Owner: Agent-4

## Scope
- Implement end-to-end Stage 1B workflow orchestration:
  - task generation
  - deterministic routing attempt
  - manual queue fallback
  - escalation timer bootstrap
- Implement notification policy handling (immediate/digest/suppression).
- Implement KPI snapshot computations for routing quality, triage velocity, and operability.

## Contract-change note
- None.
- Canonical contracts remain unchanged:
  - APIs:
    - `POST /comment-letters/{letterId}/create-tasks`
    - `POST /tasks/{taskId}/reassign`
  - Events:
    - `tasks.bulk_created_from_extractions` v1
    - `task.auto_assigned` v1
    - `task.assignment_overdue` v1

## Artifacts
- Workflow orchestration: `scripts/stage1b/workflow_orchestrator.py`
- Notification policy: `scripts/stage1b/notification_policy.py`
- KPI metrics: `scripts/stage1b/kpi_metrics.py`
- Store/counter updates: `scripts/stage1b/ticketing_service.py`
- Tests: `tests/stage1b/test_stage1b_slice5_workflow_notifications_kpis.py`

## Rollback Notes
- App-layer only; no new schema changes.
- Safe rollback: revert this slice files and retain Slice 1-5 DB and contract artifacts.
