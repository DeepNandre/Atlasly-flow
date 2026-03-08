# Stage 2 Slice 7 Rollback Runbook

## Scope
- Revert Slice 7 generation-run idempotency table:
  - `permit_application_generation_runs`
- Disable runtime stubs:
  - `scripts/stage2/intake_api.py`

## Preconditions
- Pause intake update and application generation write paths.
- Ensure fallback/manual generation path is available.

## Rollback steps
1. Disable Slice 7 runtime flag for intake/application generation.
2. Execute rollback SQL:
   - `db/migrations/rollback/000029_stage2_application_generation_runs_rollback.sql`
3. Validate table removal and migration consistency.
4. Re-enable write path only after fallback is verified.

## Data impact
- Generation-run idempotency history is dropped.
- Core intake sessions and permit applications tables remain intact.

## Contract safety note
- Shared API paths and event names/versions remain unchanged.
