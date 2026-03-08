# Stage 1A Build - Slice 4

## Scope
- Add API contract artifact for Stage 1A comment-letter endpoints.
- Implement DB-level approval workflow for `POST /comment-letters/{letterId}/approve`.
- Enforce immutable snapshot creation and idempotent retry behavior.

## Contract safety
- Locked endpoint names preserved:
  - `POST /comment-letters`
  - `GET /comment-letters/{letterId}`
  - `GET /comment-letters/{letterId}/extractions`
  - `POST /comment-letters/{letterId}/approve`
- Locked Stage 1A event names preserved.
- No shared enum/event/API contract renamed.

## Artifacts
- API contract:
  - `contracts/stage1a/api/comment-letters.openapi.yaml`
- Migration:
  - `db/migrations/000019_stage1a_approval_workflow.sql`
- Rollback:
  - `db/migrations/rollback/000019_stage1a_approval_workflow.rollback.sql`
- Tests:
  - `tests/stage1a/20260303_slice4_approve_checks.sql`

## Approve workflow behavior
- Reject approval if any extraction row remains in `needs_review`.
- Promote eligible extraction rows to `approved_snapshot`.
- Persist immutable snapshot row in `comment_letter_approval_snapshots` (unique per letter).
- Emit `comment_letter.approved` through `stage1a_emit_event` exactly once.
- Transition letter status to `completed`.
- Idempotent retries return the existing snapshot id.

## Test
- Run in order:
  - `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/stage1a/20260303_slice1_contract_checks.sql`
  - `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/stage1a/20260303_slice2_state_event_checks.sql`
  - `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/stage1a/20260303_slice3_emit_function_checks.sql`
  - `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/stage1a/20260303_slice4_approve_checks.sql`

## Rollback notes
1. Stop Stage 1A review/approve workers.
2. Ensure no in-flight calls are executing `stage1a_approve_comment_letter`.
3. Apply Slice 4 rollback SQL.
4. Verify `comment_letter_approval_snapshots` and function are removed.
5. Re-enable workers only after compatible schema is re-applied.

## Known gap after Slice 4
- Service-level HTTP handlers are still not present in this repo (docs/contracts/migrations only).
- No generated SDK/server stubs from OpenAPI yet.
