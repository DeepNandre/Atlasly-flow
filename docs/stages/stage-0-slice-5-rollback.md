# Stage 0 Slice 5 Rollback Notes

Date: 2026-03-03  
Scope: `000007_stage0_notifications` migration.

## What Slice 5 Adds

- Notification delivery queue table:
  - `notification_jobs`
- Idempotency/dedupe constraint:
  - unique `(organization_id, dedupe_key, channel)`
- Retry queue index:
  - partial index on `(status, next_attempt_at)` for `pending` and `retry`

## Rollback Order

1. `db/migrations/000007_stage0_notifications.down.sql`
2. If full rollback to pre-Slice 5 is needed, continue with:
  - `db/migrations/000006_stage0_audit_and_domain_events.down.sql`
  - `db/migrations/000005_stage0_documents_and_versions.down.sql`
  - `db/migrations/000004_stage0_core_domain.down.sql`
  - `db/migrations/000003_stage0_identity_and_tenancy.down.sql`
  - `db/migrations/000002_stage0_create_types.down.sql`
  - `db/migrations/000001_stage0_enable_extensions.down.sql`

## Rollback Caveats

- Data loss: rolling back `0007` drops all pending/sent notification jobs.
- Operational impact: workers polling notification retries will have no backing table.
- Dependency order: remove notification workers before rollback to avoid runtime errors.

## Pre-Rollback Checklist

1. Backup/snapshot database.
2. Pause notification workers and disable enqueue paths.
3. Confirm no downstream migration depends on `notification_jobs`.
4. Apply `0007` down in maintenance mode.
5. Re-enable writes only after smoke checks pass.

