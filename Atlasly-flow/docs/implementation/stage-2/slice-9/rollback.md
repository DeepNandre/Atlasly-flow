# Stage 2 Slice 9 Rollback Runbook

## Scope
- Revert Slice 9 migration:
  - `stage2_event_outbox`
- Disable SQLite-backed Stage 2 repository rollout path.

## Preconditions
- Pause outbox publisher workers for Stage 2 event stream.
- Ensure no pending Stage 2 outbox publishes are in-flight.

## Rollback steps
1. Disable Stage 2 outbox publisher and persisted runtime path.
2. Execute rollback SQL:
   - `db/migrations/rollback/000031_stage2_event_outbox_rollback.sql`
3. Validate table removal and migration consistency.

## Data impact
- Stage 2 outbox records are dropped.
- Intake/sync canonical records remain available in primary tables.

## Contract safety note
- Shared API route and event contract names/versions remain unchanged.
