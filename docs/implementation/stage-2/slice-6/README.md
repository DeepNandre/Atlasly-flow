# Stage 2 Slice 6

Status: Implemented  
Date: 2026-03-03  
Owner: Agent-5

## Scope
- Implement executable API stubs for Stage 2 parity contracts:
  - `POST /connectors/{ahj}/poll`
  - `GET /permits/{permitId}/status-timeline`
- Wire APIs to Stage 2 sync runtime store with tenant checks and validation.
- Add projection cache schema for current-status reads.

## Contract Safety
- No shared enum/event/API contract names were changed in this slice.
- Canonical contracts preserved:
  - `POST /connectors/{ahj}/poll`
  - `GET /permits/{permitId}/status-timeline`
  - `permit.status_observed` v1
  - `permit.status_changed` v1

## Files
- Runtime API:
  - `scripts/stage2/sync_api.py`
- Runtime sync core update:
  - `scripts/stage2/status_sync.py`
- Migration:
  - `db/migrations/000028_stage2_status_projection_cache.sql`
- Rollback SQL:
  - `db/migrations/rollback/000028_stage2_status_projection_cache_rollback.sql`
- Tests:
  - `tests/stage2/test_stage2_slice6_apis.py`
  - `tests/stage2/test_stage2_slice6_contracts.py`
  - `tests/stage2/slice-6-contract-tests.md`
- Rollback runbook:
  - `docs/implementation/stage-2/slice-6/rollback.md`
