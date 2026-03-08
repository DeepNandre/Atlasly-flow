# Stage 2 Slice 3

Status: Implemented  
Date: 2026-03-03  
Owner: Agent-5

## Scope
- Add connector polling run persistence (`portal_sync_runs`).
- Add normalized/raw status event storage with dedupe (`permit_status_events`).
- Add source provenance table for timeline auditability (`status_source_provenance`).
- Add timeline read contract and `permit.status_observed` event schema.

## Contract Safety
- No shared enum/event/API contract names were changed in this slice.
- Canonical contracts preserved:
  - `POST /connectors/{ahj}/poll`
  - `GET /permits/{permitId}/status-timeline`
  - `permit.status_observed` v1

## Files
- Migration:
  - `db/migrations/000025_stage2_status_sync_foundations.sql`
- Rollback SQL:
  - `db/migrations/rollback/000025_stage2_status_sync_foundations_rollback.sql`
- API contract:
  - `contracts/stage2/status-timeline.v1.openapi.yaml`
- Event schema:
  - `contracts/stage2/permit.status_observed.v1.schema.json`
- Contract tests:
  - `tests/stage2/test_stage2_slice3_contracts.py`
  - `tests/stage2/slice-3-contract-tests.md`
- Rollback runbook:
  - `docs/implementation/stage-2/slice-3/rollback.md`
