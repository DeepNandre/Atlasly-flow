# Stage 1B Slice 7

Status: Built
Date: 2026-03-03
Owner: Agent-4

## Scope
- Close the runtime integration gap for Stage 1B by adding API entrypoint wrappers and worker binding functions.
- Add service-boundary tests validating status/error mapping and overdue worker notifications.
- Add Stage 1B apply/test/rollback shell scripts to make stage operations executable from one command path.

## Contract-change note
- None.
- Shared API paths unchanged:
  - `POST /comment-letters/{letterId}/create-tasks`
  - `POST /tasks/{taskId}/reassign`
- Shared events unchanged:
  - `tasks.bulk_created_from_extractions` v1
  - `task.auto_assigned` v1
  - `task.assignment_overdue` v1

## Artifacts
- Runtime API:
  - `scripts/stage1b/runtime_api.py`
- Runtime tests:
  - `tests/stage1b/test_stage1b_slice6_runtime_api.py`
- Stage scripts:
  - `scripts/stage1b-apply.sh`
  - `scripts/stage1b-test.sh`
  - `scripts/stage1b-rollback.sh`

## Rollback Notes
- App-layer/runtime rollback: revert `scripts/stage1b/runtime_api.py` and runtime tests.
- DB rollback remains `db/migrations/rollback/000022_stage1b_ticketing_routing.rollback.sql`.
