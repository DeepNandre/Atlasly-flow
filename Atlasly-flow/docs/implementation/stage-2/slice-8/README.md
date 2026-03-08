# Stage 2 Slice 8

Status: Implemented  
Date: 2026-03-03  
Owner: Agent-5

## Scope
- Add persistence-backed Stage 2 repository abstraction (`Stage2Repository`).
- Add persisted runtime variants for intake and sync APIs.
- Add persisted status observation + projection + review queue handling.
- Add connector runtime retry diagnostics migration (`connector_poll_attempts`).

## Contract Safety
- No shared enum/event/API contract names were changed.
- Canonical contracts preserved:
  - `POST /intake-sessions`
  - `PATCH /intake-sessions/{sessionId}`
  - `POST /permits/{permitId}/applications/generate`
  - `POST /connectors/{ahj}/poll`
  - `GET /permits/{permitId}/status-timeline`
  - `intake.completed` v1
  - `permit.application_generated` v1
  - `permit.status_observed` v1
  - `permit.status_changed` v1

## Files
- Repository:
  - `scripts/stage2/repositories.py`
- Runtime updates:
  - `scripts/stage2/intake_api.py`
  - `scripts/stage2/sync_api.py`
  - `scripts/stage2/status_sync.py`
  - `scripts/stage2/reconciliation_runtime.py`
  - `scripts/stage2/connector_runtime.py`
- Migration:
  - `db/migrations/000030_stage2_connector_poll_attempts.sql`
- Rollback SQL:
  - `db/migrations/rollback/000030_stage2_connector_poll_attempts_rollback.sql`
- Tests:
  - `tests/stage2/test_stage2_slice8_persistence_integration.py`
  - `tests/stage2/test_stage2_slice8_9_contracts.py`
- Rollback runbook:
  - `docs/implementation/stage-2/slice-8/rollback.md`
