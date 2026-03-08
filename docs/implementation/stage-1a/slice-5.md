# Stage 1A Build - Slice 5

## Scope
- Add DB read-model functions for Stage 1A GET endpoints.
- Add immutable snapshot retrieval function for approved extraction sets.
- Add SQL checks for summary metrics and extraction ordering/shape.

## Contract safety
- Endpoint names unchanged and aligned to Stage 1A contract:
  - `GET /comment-letters/{letterId}`
  - `GET /comment-letters/{letterId}/extractions`
- Event names/contracts unchanged.
- No shared enums/events/APIs renamed.

## Artifacts
- Migration:
  - `db/migrations/000020_stage1a_read_models.sql`
- Rollback:
  - `db/migrations/rollback/000020_stage1a_read_models.rollback.sql`
- Tests:
  - `tests/stage1a/20260303_slice5_read_models_checks.sql`

## Read model functions
- `stage1a_get_comment_letter_status(letter_id)`
  - Returns `status`, `extraction_count`, `avg_confidence`, `requires_review_count`.
- `stage1a_list_comment_extractions(letter_id)`
  - Returns deterministic ordered extraction list (by `page_number`, `comment_id`).
- `stage1a_get_approval_snapshot(letter_id)`
  - Returns immutable approved snapshot payload and metadata.

## Test
- Run in order:
  - `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/stage1a/20260303_slice1_contract_checks.sql`
  - `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/stage1a/20260303_slice2_state_event_checks.sql`
  - `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/stage1a/20260303_slice3_emit_function_checks.sql`
  - `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/stage1a/20260303_slice4_approve_checks.sql`
  - `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/stage1a/20260303_slice5_read_models_checks.sql`

## Rollback notes
1. Pause read paths that call Stage 1A read-model functions.
2. Apply Slice 5 rollback SQL.
3. Validate read-model functions are removed from `pg_proc`.
4. Resume read traffic on compatible deployment.

## Known gap after Slice 5
- HTTP handlers still not implemented in this repo.
- No CI runner integration for SQL checks yet.
