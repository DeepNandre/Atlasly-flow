# Stage 0 Slice 7 Rollback Notes

Date: 2026-03-03  
Scope: `000009_stage0_future_moat_tables` migration.

## What Slice 7 Adds

- Future instrumentation tables required by Stage 0 spec:
  - `permit_reviews`
  - `ahj_comments`
  - `code_citations`
  - `review_outcomes`
- Tenant-safe composite FK chain across permit review/comment/citation/outcome entities.
- Baseline RLS policies on these moat tables.

## Rollback Order

1. `db/migrations/000009_stage0_future_moat_tables.down.sql`
2. If full rollback is needed, continue with prior slice downs (`0008`..`0001`) in reverse order.

## Rollback Caveats

- Data loss: rolling back `0009` removes permit review and AHJ feedback history.
- Analytics impact: downstream models relying on these tables will fail after rollback.
- Security dependency: `0009` assumes helper functions from `0008`; keep order intact.

## Pre-Rollback Checklist

1. Backup/snapshot DB.
2. Pause any workloads writing review/comment/citation outcomes.
3. Confirm no downstream schema depends on these tables.
4. Apply `0009` down.
5. Verify object removal and restore dependent workloads only after checks.

