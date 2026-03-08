# Stage 2 Slice 1 Rollback Runbook

## Scope
- Revert Stage 2 intake foundation objects introduced by migration:
  - `intake_sessions`
  - `permit_applications`

## Preconditions
- Confirm no dependent application code is still writing to these tables.
- Snapshot data if rollback is in production-like environments.

## Rollback steps
1. Disable intake write traffic (`POST /intake-sessions`, `PATCH /intake-sessions/{sessionId}`) at gateway/feature flag.
2. Verify no active transactions against the target tables.
3. Execute:
   - `db/migrations/rollback/000023_stage2_intake_foundations_rollback.sql`
4. Validate rollback:
   - `intake_sessions` and `permit_applications` do not exist.
   - No migration lock remains.
5. Re-enable traffic only if fallback code path is active.

## Data impact
- Destructive rollback: all records in both tables are dropped.
- Required mitigation: export rows prior to rollback if retention is needed.

## Contract safety note
- This rollback does not modify shared event names/versions or shared API paths.
