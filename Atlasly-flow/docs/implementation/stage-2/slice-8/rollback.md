# Stage 2 Slice 8 Rollback Runbook

## Scope
- Revert Slice 8 migration:
  - `connector_poll_attempts`
- Disable persistence-backed connector retry diagnostics path.

## Preconditions
- Pause connector polling workers.
- Ensure in-flight sync runs are drained or safely cancelled.

## Rollback steps
1. Disable retry-attempt logging flag for connector runtime.
2. Execute rollback SQL:
   - `db/migrations/rollback/000030_stage2_connector_poll_attempts_rollback.sql`
3. Validate table removal and migration health.

## Data impact
- Poll attempt history is dropped.
- `portal_sync_runs` and status event history remain intact.

## Contract safety note
- No shared API route or event contract name/version is changed.
