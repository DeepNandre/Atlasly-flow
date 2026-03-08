# Stage 0.5 Slice 2: Webhook Control Plane Baseline

## Scope
- Add webhook control-plane validation and registration functions in PostgreSQL.
- Add event-type allowlist and secure URL enforcement for subscriptions.
- Add query function to back `GET /webhook-events` retrieval path.
- Add contract tests and rollback-tested migration runner.

## Contract-change note
- No changes to shared enums/events/API contracts in this slice.
- This slice enforces existing event names already defined in Stage 0 and Stage 0.5 specs.

## Delivered artifacts
- Migration up: `db/migrations/000011_stage0_5_webhook_control_plane.up.sql`
- Migration down: `db/migrations/000011_stage0_5_webhook_control_plane.down.sql`
- SQL tests: `db/tests/002_stage0_5_webhook_control_plane.sql`
- Runner: `scripts/db/test_slice2_stage0_5.sh`

## Operational behavior implemented
- Subscription registration requires:
  - HTTPS target URL.
  - non-empty event types.
  - allowed event names only.
- Active dedupe policy:
  - one active subscription per org + target URL.
- Events read path:
  - filtered and paginated delivery listing function.

## Rollout plan
1. Apply Stage 0 base migrations, then Stage 0.5 Slice 1 migration.
2. Apply `000011_stage0_5_webhook_control_plane.up.sql`.
3. Run `scripts/db/test_slice2_stage0_5.sh` in CI/staging.
4. Enable webhook control-plane API code paths behind feature flag.

## Rollback plan
1. Disable webhook registration/listing write paths via feature flag.
2. Apply `000011_stage0_5_webhook_control_plane.down.sql`.
3. Keep Stage 0.5 Slice 1 tables intact unless full Stage 0.5 rollback is needed.
4. Verify subscription CRUD path returns to pre-slice behavior.

## Rollback risk notes
- Rolling back this slice removes helper functions and new validation constraints.
- Existing subscriptions that relied on new constraints remain in table; data cleanup may be required if partial writes occurred during rollback window.
