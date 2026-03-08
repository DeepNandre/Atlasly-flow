# Stage 0.5 Slice 3: Webhook Delivery Runtime (Retry, DLQ, Replay Queue)

## Scope
- Add DB runtime primitives for webhook failure handling and delivery reliability.
- Implement retry scheduling semantics and terminal dead-letter transitions.
- Add replay job queueing primitives for dead-letter recovery workflow.
- Add contract tests and rollback-verified runner.

## Contract-change note
- No shared enums/events/API contracts were changed in this slice.
- This slice implements runtime controls behind existing Stage 0.5 interfaces.

## Delivered artifacts
- Migration up: `db/migrations/000012_stage0_5_webhook_delivery_runtime.up.sql`
- Migration down: `db/migrations/000012_stage0_5_webhook_delivery_runtime.down.sql`
- SQL tests: `db/tests/003_stage0_5_webhook_delivery_runtime.sql`
- Runner: `scripts/db/test_slice3_stage0_5.sh`

## Operational behavior implemented
- Retry scheduling function with bounded attempt windows.
- Failure classification helper for retryable/non-retryable outcomes.
- Delivery transition function:
  - retryable failure -> `retrying` with computed `next_retry_at`.
  - terminal/non-retryable failure -> `dead_lettered` plus DLQ row.
- Replay queue request function for dead-letter entries.

## Rollout plan
1. Apply Slice 1 and Slice 2 migrations.
2. Apply `000012_stage0_5_webhook_delivery_runtime.up.sql`.
3. Run `scripts/db/test_slice3_stage0_5.sh` in CI/staging.
4. Enable worker path that calls `enqueue_webhook_retry(...)` under feature flag.

## Rollback plan
1. Disable webhook delivery workers and replay request path.
2. Apply `000012_stage0_5_webhook_delivery_runtime.down.sql`.
3. Keep prior Stage 0.5 schema intact unless full rollback is required.
4. Validate no runtime SQL function calls remain in service code.

## Rollback risk notes
- Rollback drops DLQ/replay runtime tables and retry metadata columns.
- Any in-flight retry schedules and replay requests are lost; export `webhook_dead_letters` and `webhook_replay_jobs` before rollback if forensic continuity is required.
