# Stage 1B Slice 4

Status: Built
Date: 2026-03-03
Owner: Agent-4

## Scope
- Add executable Stage 1B handler/service scaffolding for:
  - `POST /comment-letters/{letterId}/create-tasks`
  - `POST /tasks/{taskId}/reassign`
- Wire deterministic idempotency behavior (`201 create`, `200 replay`, `409 conflict`).
- Enforce reassignment feedback integrity and role/tenant checks.
- Validate outbox event emission for canonical Stage 1B event contracts.

## Contract-change note
- None.
- Shared contracts unchanged:
  - `tasks.bulk_created_from_extractions` v1
  - `task.auto_assigned` v1
  - `task.assignment_overdue` v1

## Artifacts
- Service scaffolding: `scripts/stage1b/ticketing_service.py`
- Integration-style tests: `tests/stage1b/test_stage1b_slice3_ticketing_service.py`

## Rollback Notes
- This slice is app-layer scaffolding only (no schema changes).
- Safe rollback: revert these two files and keep Slice 1-3 artifacts intact.
