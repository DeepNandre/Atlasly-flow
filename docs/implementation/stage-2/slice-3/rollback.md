# Stage 2 Slice 3 Rollback Runbook

## Scope
- Revert Slice 3 status-sync foundation objects:
  - `portal_sync_runs`
  - `permit_status_events`
  - `status_source_provenance`

## Preconditions
- Pause connector polling and status timeline reads relying on Slice 3 storage.
- Snapshot table contents if forensic audit retention is required.

## Rollback steps
1. Disable connector poll trigger paths (`POST /connectors/{ahj}/poll`) and timeline read feature flag.
2. Confirm no active writes against Slice 3 tables.
3. Execute:
   - `db/migrations/rollback/000025_stage2_status_sync_foundations_rollback.sql`
4. Validate:
   - Tables removed cleanly.
   - No migration lock or partial state remains.

## Data impact
- Destructive rollback; all sync runs, observed status events, and provenance rows are dropped.

## Contract safety note
- No shared event names/versions or API route names are altered by this rollback.
