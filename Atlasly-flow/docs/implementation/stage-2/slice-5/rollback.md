# Stage 2 Slice 5 Rollback Runbook

## Scope
- Revert Slice 5 runtime control data tables and disable runtime scaffolding:
  - `status_normalization_rules`
  - `status_drift_alerts`
  - `scripts/stage2/status_sync.py` runtime usage

## Preconditions
- Pause reconciliation and normalization jobs that read Slice 5 tables.
- Archive active rule records if needed for restoration.

## Rollback steps
1. Disable Stage 2 normalization/reconciliation worker entrypoints via feature flag.
2. Execute rollback SQL:
   - `db/migrations/rollback/000027_stage2_normalization_and_drift_rules_rollback.sql`
3. Confirm tables are removed.
4. Keep connector polling in fallback-safe mode until rules are restored.

## Data impact
- Destructive rollback of custom normalization rules and drift alert history.

## Contract safety note
- Shared API routes and event names/versions remain unchanged.
