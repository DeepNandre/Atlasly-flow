# Stage 1A Build - Slice 2

## Scope
- Add DB-enforced Stage 1A extraction state transition rules.
- Add exactly-once Stage 1A event emission dedupe contract.
- Add event payload JSON schemas for Stage 1A events.
- Add SQL contract checks for transition validity and emission uniqueness.

## Contract safety
- Shared event names preserved exactly:
  - `comment_letter.parsing_started`
  - `comment_letter.extraction_completed`
  - `comment_letter.approved`
- Shared event envelope contract unchanged (`event_type` + `event_version`).
- No REST API contract changes in this slice.

## Migration
- Apply: `db/migrations/000017_stage1a_state_and_event_guards.sql`
- Rollback: `db/migrations/rollback/000017_stage1a_state_and_event_guards.rollback.sql`

## Test
- Run after Slice 1 migration:
  - `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/stage1a/20260303_slice1_contract_checks.sql`
  - `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/stage1a/20260303_slice2_state_event_checks.sql`
- Expected: final `PASS` row from each file and no uncaught exceptions.

## Rollback notes
1. Stop Stage 1A extraction workers.
2. Ensure no in-flight transactions are writing `comment_letters`.
3. Run rollback SQL for Slice 2.
4. Validate trigger/functions/event-emission table are removed.
5. Resume workers only when migration is re-applied or feature is disabled.

## Known gap after Slice 2
- Event publish to Stage 0 `domain_events` outbox is not implemented yet.
- Service-layer transaction orchestration for "emit `extraction_completed` exactly once at normalization completion" still pending.
