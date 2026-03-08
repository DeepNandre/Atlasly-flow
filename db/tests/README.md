# DB Tests

These tests are SQL-based contract checks for migration slices.

For Slice 1:

- `001_slice1_contracts.sql` validates canonical shared enum values and fixed tenancy uniqueness behavior for `memberships`.

Run via:

```bash
scripts/db/test_slice1.sh
```

For Stage 0.5 Slice 2:

- `002_stage0_5_webhook_control_plane.sql` validates webhook registration constraints,
  allowed event filtering, duplicate active subscription prevention, and webhook-event listing behavior.

Run via:

```bash
scripts/db/test_slice2_stage0_5.sh
```

For Stage 0.5 Slice 3:

- `003_stage0_5_webhook_delivery_runtime.sql` validates retry scheduling, dead-letter transitions, and replay request queueing.

Run via:

```bash
scripts/db/test_slice3_stage0_5.sh
```

For Stage 0.5 Slice 4:

- `004_stage0_5_connector_runtime.sql` validates connector run lifecycle transitions,
  terminal state protection, and connector error taxonomy enforcement.

Run via:

```bash
scripts/db/test_slice4_stage0_5.sh
```

For Stage 0.5 Slice 5:

- `005_stage0_5_dashboard_api_credentials.sql` validates dashboard snapshot upsert/latest-read behavior and API credential lifecycle controls (scope, expiry, rotate, revoke).

Run via:

```bash
scripts/db/test_slice5_stage0_5.sh
```

For Stage 0.5 Slice 6:

- `006_stage0_5_admin_security_exports.sql` validates task template lifecycle controls and owner/admin-gated security audit export flows.

Run via:

```bash
scripts/db/test_slice6_stage0_5.sh
```

For Stage 1B Slice 1:

- `002_stage1b_contracts.sql` validates:
  - one-task-per-approved-extraction uniqueness under retries/races,
  - Stage 1B event idempotency behavior via `domain_events`,
  - reassignment feedback integrity constraints.

Run via:

```bash
scripts/db/test_stage1b_slice1.sh
```

For Slice 2:

- `002_slice2_core_domain_contracts.sql` validates tenant-safe core domain FKs and canonical `permit_status` transition rules.

Run via:

```bash
scripts/db/test_slice2.sh
```

For Slice 3:

- `003_slice3_documents_contracts.sql` validates document version sequencing, storage uniqueness, OCR queue index contract, and tenant-safe document ownership.

Run via:

```bash
scripts/db/test_slice3.sh
```

For Slice 4:

- `004_slice4_events_contracts.sql` validates audit append-only behavior, domain event idempotency scope, and consumer dedup primitives.

Run via:

```bash
scripts/db/test_slice4.sh
```

For Slice 5:

- `005_slice5_notifications_contracts.sql` validates notification dedupe behavior, retry scheduling constraints, and queue index presence.

Run via:

```bash
scripts/db/test_slice5.sh
```

For Slice 6:

- `006_slice6_rls_contracts.sql` validates Stage 0 tenant-isolation RLS behavior using a non-superuser app role and scoped session settings.

Run via:

```bash
scripts/db/test_slice6.sh
```

For Slice 7:

- `007_slice7_moat_contracts.sql` validates future-moat tables, tenant-safe FK chains, and baseline RLS policy presence.

Run via:

```bash
scripts/db/test_slice7.sh
```

Full Stage 0 DB baseline check:

```bash
scripts/db/test_stage0.sh
```

For Stage 3 Slice 6:

- `006_stage3_persistence_contracts.sql` validates:
  - Stage 3 outbox idempotency uniqueness behavior,
  - payout instruction state constraint enforcement,
  - reconciliation run status constraint and replay-safe uniqueness key.

Run via:

```bash
scripts/db/test_stage3_slice6.sh
```
