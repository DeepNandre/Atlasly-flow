# Stage 1A Build - Slice 3

## Scope
- Add deterministic event emission helper for Stage 1A.
- Enforce canonical emission point for `comment_letter.extraction_completed`.
- Add idempotency-key builder to prevent duplicate emission drift.
- Add optional outbox bridge into Stage 0 `domain_events` when present.

## Contract safety
- Shared event names unchanged:
  - `comment_letter.parsing_started`
  - `comment_letter.extraction_completed`
  - `comment_letter.approved`
- Shared envelope model unchanged (`event_type` + `event_version`).
- Emission-point rule aligned with Stage 1A research Task 3:
  - `comment_letter.extraction_completed` only when `comment_letters.extraction_status = 'review_queueing'`.

## Migration
- Apply: `db/migrations/000018_stage1a_event_emit_function.sql`
- Rollback: `db/migrations/rollback/000018_stage1a_event_emit_function.rollback.sql`

## Test
- Run in order:
  - `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/stage1a/20260303_slice1_contract_checks.sql`
  - `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/stage1a/20260303_slice2_state_event_checks.sql`
  - `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/stage1a/20260303_slice3_emit_function_checks.sql`
- Expected: all files finish with `PASS` row and no uncaught exceptions.

## Rollback notes
1. Pause Stage 1A workers that call `stage1a_emit_event`.
2. Confirm no in-flight transaction is inside helper function.
3. Execute Slice 3 rollback SQL.
4. Validate both helper functions are absent from `pg_proc`.
5. Resume workers only after redeploying compatible code path.

## Known gap after Slice 3
- No HTTP API/service implementation yet invokes `stage1a_emit_event` transactionally.
- No benchmark runner wired yet to assert KPI gates in CI.
