# Stage 0 Slice 4 Rollback Notes

Date: 2026-03-03  
Scope: `000006_stage0_audit_and_domain_events` migration.

## What Slice 4 Adds

- Event/audit primitives:
  - `audit_events`
  - `domain_events`
  - `event_consumer_dedup`
- Core idempotency constraint:
  - `domain_events` unique key `(organization_id, idempotency_key)`
- Audit immutability guard:
  - `prevent_audit_event_mutation()` trigger function
  - update/delete blocking triggers on `audit_events`
- Timeline/publisher indexes:
  - project/org audit timeline indexes
  - pending/failed outbox scan index

## Rollback Order

1. `db/migrations/000006_stage0_audit_and_domain_events.down.sql`
2. If full rollback to pre-Slice 4 is needed, continue with:
  - `db/migrations/000005_stage0_documents_and_versions.down.sql`
  - `db/migrations/000004_stage0_core_domain.down.sql`
  - `db/migrations/000003_stage0_identity_and_tenancy.down.sql`
  - `db/migrations/000002_stage0_create_types.down.sql`
  - `db/migrations/000001_stage0_enable_extensions.down.sql`

## Rollback Caveats

- Data loss: rolling back `0006` drops all audit and domain events.
- Operational impact: replay/reconciliation logic depending on `domain_events` will be unavailable after rollback.
- Dependency order: `event_consumer_dedup` must be dropped before `domain_events`; handled by `0006` down.

## Pre-Rollback Checklist

1. Backup/snapshot database.
2. Drain or pause event publisher/consumer workers.
3. Confirm no downstream migration depends on `audit_events`/`domain_events`.
4. Apply `0006` down in maintenance mode.
5. Validate remaining Stage 0 schema and re-enable writes.

