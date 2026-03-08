# Stage 0.5 Slice 5: Dashboard KPI Snapshot + API Credential Lifecycle

## Scope
- Enforce API credential scope/expiry/hash controls.
- Add API key lifecycle SQL functions (create, revoke, rotate).
- Add KPI snapshot shape checks and snapshot upsert/latest-query functions.
- Add contract tests and rollback-tested runner.

## Contract-change note
- No shared enums/events/API contracts were changed in this slice.
- This slice adds enforcement and runtime helpers for existing Stage 0.5 interfaces.

## Delivered artifacts
- Migration up: `db/migrations/000014_stage0_5_dashboard_api_credentials.up.sql`
- Migration down: `db/migrations/000014_stage0_5_dashboard_api_credentials.down.sql`
- SQL tests: `db/tests/005_stage0_5_dashboard_api_credentials.sql`
- Runner: `scripts/db/test_slice5_stage0_5.sh`

## Operational behavior implemented
- API credentials:
  - allowed scope allowlist enforcement
  - max expiry window (365 days) for create path
  - hash length check and active key prefix uniqueness per org
  - rotate flow revokes old key and creates a new credential row
- Dashboard snapshots:
  - metrics shape contract checks
  - idempotent upsert by `(organization_id, snapshot_at)`
  - latest snapshot retrieval helper

## Rollout plan
1. Apply Stage 0 and Stage 0.5 Slice 1-4 migrations.
2. Apply `000014_stage0_5_dashboard_api_credentials.up.sql`.
3. Run `scripts/db/test_slice5_stage0_5.sh` in CI/staging.
4. Enable dashboard and API key service paths behind feature flags.

## Rollback plan
1. Disable API key rotation/revocation paths and dashboard snapshot writer.
2. Apply `000014_stage0_5_dashboard_api_credentials.down.sql`.
3. Keep prior Stage 0.5 schema in place unless full rollback required.

## Rollback risk notes
- Rollback removes API key lifecycle helper functions and dashboard upsert/read helpers.
- Existing credential and snapshot rows persist, but lifecycle validation and shape checks are no longer enforced.
