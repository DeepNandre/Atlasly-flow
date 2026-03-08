# Stage 1B Slice 3

Status: Built
Date: 2026-03-03
Owner: Agent-4

## Scope
- Lock API contracts for deterministic create-tasks and reassignment endpoints.
- Add executable behavior tests for idempotent replay and reassignment feedback validation.
- Strengthen DB contract test for generation-run idempotency uniqueness.

## Contract-change note
- None.
- Shared event names/versions unchanged:
  - `tasks.bulk_created_from_extractions` v1
  - `task.auto_assigned` v1
  - `task.assignment_overdue` v1
- API paths unchanged:
  - `POST /comment-letters/{letterId}/create-tasks`
  - `POST /tasks/{taskId}/reassign`

## Artifacts
- OpenAPI:
  - `contracts/stage1b/apis/create-tasks.v1.openapi.yaml`
  - `contracts/stage1b/apis/reassign-task.v1.openapi.yaml`
- API behavior module:
  - `scripts/stage1b/tasking_api.py`
- Tests:
  - `tests/stage1b/test_stage1b_slice2_api_contracts.py`
  - `db/tests/002_stage1b_contracts.sql` (extended)

## Rollback Notes
- Revert new API behavior module and tests only if they block CI; no runtime schema impact.
- Keep Stage 1B migration artifacts from Slice 2 in place.
