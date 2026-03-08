# Stage 2 Slice 7 Intake/Application Runtime Tests

Date: 2026-03-03  
Owner: Agent-5

## Scope
- Runtime stubs for:
  - `POST /intake-sessions`
  - `PATCH /intake-sessions/{sessionId}`
  - `POST /permits/{permitId}/applications/generate`
- Generation-run idempotency tracking migration.

## Tests
1. Intake create.
- Valid request creates session (`201`).
- Idempotent replay returns same session (`200`).

2. Intake update/completion.
- Version mismatch returns `409`.
- Completion validates required fields and emits `intake.completed` v1.

3. Application generation.
- Completed intake + full required field mapping emits `permit.application_generated` v1.
- Missing required mapping fails with `422`.

4. Generation run migration.
- `permit_application_generation_runs` table exists with unique `(organization_id, idempotency_key)`.
- Rollback drops table.

## Execution commands
- `python3 -m unittest tests/stage2/test_stage2_slice7_intake_api.py`
- `python3 -m unittest tests/stage2/test_stage2_slice7_contracts.py`
