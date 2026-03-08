# Stage 1A Build - Slice 1

## Scope
- Create initial Stage 1A database contracts for extraction persistence.
- Lock extraction payload contract in JSON Schema.
- Add migration rollback script.
- Add SQL contract check script for required Stage 1A tables/columns/indexes.

## Contract safety
- Shared API/event names unchanged.
- No shared enum/event/API contract changed in this slice.
- Stage 1A local status/check constraints added only in Stage 1A tables.

## Migration
- Apply: `db/migrations/000016_stage1a_comment_extraction.sql`
- Rollback: `db/migrations/rollback/000016_stage1a_comment_extraction.rollback.sql`

## Test
- Run: `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/stage1a/20260303_slice1_contract_checks.sql`
- Expected: final `PASS` row and no exceptions.

## Rollback notes
1. Pause Stage 1A parser workers before rollback.
2. Snapshot rows from `comment_letters`, `comment_extractions`, `extraction_reviews`, `extraction_feedback`.
3. Run rollback SQL in a transaction.
4. Verify all four Stage 1A tables are absent.
5. Re-enable workers only after DB schema is re-applied or feature flag is off.

## Known gap after Slice 1
- No service/API implementation yet for `POST /comment-letters` and review workflow.
- No event publisher implementation yet for Stage 1A events.
