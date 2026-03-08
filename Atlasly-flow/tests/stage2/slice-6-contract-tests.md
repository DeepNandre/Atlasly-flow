# Stage 2 Slice 6 Contract and API Runtime Tests

Date: 2026-03-03  
Owner: Agent-5

## Scope
- Runtime API stubs for:
  - `POST /connectors/{ahj}/poll`
  - `GET /permits/{permitId}/status-timeline`
- Status projection cache schema for fast status reads.

## Tests
1. Connector poll API behavior.
- Happy path returns `202`.
- Idempotent replay returns same run with `200`.
- Invalid AHJ path or missing connector fails with `422`.

2. Timeline API behavior.
- Returns normalized timeline entries with provenance fields.
- Supports `from` filter and `limit`.
- Enforces tenant isolation (`403`).
- Validates query params (`422`).

3. Projection cache migration.
- `permit_status_projections` table exists with canonical status check.
- Rollback drops projection table cleanly.

## Execution commands
- `python3 -m unittest tests/stage2/test_stage2_slice6_apis.py`
- `python3 -m unittest tests/stage2/test_stage2_slice6_contracts.py`
