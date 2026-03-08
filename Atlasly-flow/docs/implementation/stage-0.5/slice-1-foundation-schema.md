# Stage 0.5 Slice 1: Foundation Schema

## Scope
- Add Stage 0.5 foundational database schema and required indexes.
- Add migration contract checks to enforce stage-spec schema coverage.
- Document rollback procedure for safe PR deployment.

## Contract-change note
- No shared enum/event/API contract changes in this slice.
- This slice only introduces data structures required by `docs/stages/stage-0.5-enterprise-readiness.md`.

## Files
- `db/migrations/000010_stage0_5_enterprise_readiness.up.sql`
- `db/migrations/000010_stage0_5_enterprise_readiness.down.sql`
- `db/tests/test_stage_0_5_migration_contracts.sh`

## Rollout plan
1. Apply `000010_stage0_5_enterprise_readiness.up.sql` in staging.
2. Run migration contract checks script.
3. Validate table/index creation in DB metadata.
4. Promote to production in low-traffic window.

## Rollback plan
1. Disable Stage 0.5 write paths (feature flag or deployment rollback).
2. Confirm no active connector/webhook workers are writing.
3. Execute `000010_stage0_5_enterprise_readiness.down.sql`.
4. Validate table removal and restore prior app deployment.

## Rollback risk notes
- This rollback is destructive for Stage 0.5 table data.
- Before rollback in production, snapshot affected tables for forensic recovery.
- If partial rollback occurs, re-run full down migration idempotently and verify table absence.
