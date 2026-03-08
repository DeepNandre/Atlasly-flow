# Stage 2 Slice 6 Rollback Runbook

## Scope
- Revert Slice 6 status projection cache:
  - `permit_status_projections`
- Disable Stage 2 API runtime stubs:
  - `scripts/stage2/sync_api.py`

## Preconditions
- Pause timeline read traffic routed to Slice 6 runtime path.
- Ensure fallback timeline path (raw event query) is available.

## Rollback steps
1. Disable Slice 6 API runtime flag.
2. Execute rollback SQL:
   - `db/migrations/rollback/000028_stage2_status_projection_cache_rollback.sql`
3. Validate projection table removal.
4. Re-enable API reads on fallback path only.

## Data impact
- Projection cache rows are dropped; canonical event/provenance tables are untouched.

## Contract safety note
- Shared API routes and event names/versions are unchanged by this rollback.
