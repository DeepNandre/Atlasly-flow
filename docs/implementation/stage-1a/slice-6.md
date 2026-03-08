# Stage 1A Build - Slice 6

## Scope
- Add pipeline entrypoint DB functions for create/finalize extraction flow.
- Add end-to-end script bundle for apply/test/rollback/drift-check.
- Keep shared contracts locked while improving operational executability.

## Contract safety
- Shared event names unchanged:
  - `comment_letter.parsing_started`
  - `comment_letter.extraction_completed`
  - `comment_letter.approved`
- Shared endpoint paths unchanged.
- No shared enum/event/API contract rename.

## Artifacts
- Migration:
  - `db/migrations/000021_stage1a_pipeline_entrypoints.sql`
- Rollback:
  - `db/migrations/rollback/000021_stage1a_pipeline_entrypoints.rollback.sql`
- Tests:
  - `tests/stage1a/20260303_slice6_pipeline_entrypoint_checks.sql`
- Scripts:
  - `scripts/stage1a-apply.sh`
  - `scripts/stage1a-test.sh`
  - `scripts/stage1a-rollback.sh`
  - `scripts/stage1a-drift-check.sh`

## New functions
- `stage1a_create_comment_letter(...)`
  - Idempotent create path for `POST /comment-letters`.
  - Emits `comment_letter.parsing_started` once.
- `stage1a_finalize_extraction(...)`
  - Canonical finalization path for extraction output.
  - Moves status to `review_queueing` when called from `normalizing_validating`.
  - Emits `comment_letter.extraction_completed` once (idempotent retries).

## Script usage
From repo root:
- `scripts/stage1a-drift-check.sh`
- `DATABASE_URL=... scripts/stage1a-apply.sh`
- `DATABASE_URL=... scripts/stage1a-test.sh`
- `DATABASE_URL=... scripts/stage1a-rollback.sh`

## Rollback notes
1. Stop parser/review workers.
2. Run `scripts/stage1a-rollback.sh`.
3. Validate Stage 1A functions are removed from `pg_proc`.
4. Re-enable workers after compatible migration state is restored.

## Known gap after Slice 6
- Service HTTP handlers are still not implemented in this repository.
- CI automation for running shell scripts is not wired yet.
