# Database

This directory contains Stage 0 foundation database assets:

- `migrations/`: ordered SQL migrations with explicit `.up.sql` and `.down.sql`.
- `tests/`: SQL contract tests that run against a temporary local PostgreSQL instance.
- `../scripts/db/test_slice1.sh`: migration + contract-test runner for Slice 1.

## Slice 1 Scope

Slice 1 introduces:

- Extension bootstrap (`pgcrypto`, `citext`).
- Canonical shared enums for Stage 0 contracts.
- Identity/tenancy tables (`users`, `organizations`, `workspaces`, `user_identities`, `memberships`).
- Fixed `memberships` uniqueness for nullable `workspace_id` using partial unique indexes.

## Stage 0.5 Slice 2 Scope

Slice 2 introduces:

- Webhook control-plane constraints for secure target URLs and allowed event-type subscriptions.
- SQL registration/read functions to back `POST /webhooks` and `GET /webhook-events` service paths.
- Additional webhook query index and active subscription dedupe index.
- Rollback-safe migration pair and slice-level contract tests.

## Stage 0.5 Slice 3 Scope

Slice 3 introduces:

- Delivery-runtime primitives for retries, terminal transitions, and dead-letter persistence.
- Replay job queue table and request function for dead-letter recovery flows.
- Retryability and delay helper functions aligned to Stage 0.5 delivery policy.
- Rollback-safe migration pair and stage-level contract tests.

## Stage 0.5 Slice 4 Scope

Slice 4 introduces:

- Connector run lifecycle constraints and transition primitives.
- Connector error taxonomy enforcement and retryability defaults.
- Runtime SQL functions to start/complete connector runs and persist run-linked errors.
- Rollback-safe migration pair and stage-level contract tests.

## Stage 0.5 Slice 5 Scope

Slice 5 introduces:

- Dashboard KPI snapshot shape checks and upsert/read helpers.
- API credential scope allowlist, expiry controls, and lifecycle helpers (create/revoke/rotate).
- Active API key prefix uniqueness per org.
- Rollback-safe migration pair and stage-level contract tests.

## Stage 0.5 Slice 6 Scope

Slice 6 introduces:

- Task template lifecycle controls (versioning, archive metadata, active-name uniqueness).
- Security audit export lifecycle controls and status transitions.
- Owner/admin request gating function for audit exports using org-level memberships.
- Rollback-safe migration pair and stage-level contract tests.
