# Stage 2 Slice 4 Rollback Runbook

## Scope
- Revert Slice 4 operational control objects:
  - `status_reconciliation_runs`
  - `status_transition_reviews`

## Preconditions
- Pause reconciliation jobs and invalid-transition review processors.
- Confirm no active writes on Slice 4 tables.

## Rollback steps
1. Disable scheduler entries for status reconciliation.
2. Disable status-transition review queue ingestion.
3. Execute:
   - `db/migrations/rollback/000026_stage2_sync_ops_controls_rollback.sql`
4. Validate:
   - Slice 4 tables removed.
   - No partially applied migration remains.

## Data impact
- Destructive rollback for reconciliation and review queue history.

## Contract safety note
- Shared API paths and event names/versions are unchanged by this rollback.
