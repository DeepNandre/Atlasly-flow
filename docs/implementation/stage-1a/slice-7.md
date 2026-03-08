# Stage 1A Build - Slice 7

## Scope
- Add Stage 1A runtime service layer for endpoint semantics and extraction workflow state handling.
- Add Stage 1A evaluation harness for KPI/gate checks.
- Add Stage 1A DB test harness script aligned with existing repo test runner conventions.

## Contract safety
- Endpoint paths unchanged:
  - `POST /comment-letters`
  - `GET /comment-letters/{letterId}`
  - `GET /comment-letters/{letterId}/extractions`
  - `POST /comment-letters/{letterId}/approve`
- Event names unchanged:
  - `comment_letter.parsing_started`
  - `comment_letter.extraction_completed`
  - `comment_letter.approved`
- `event_version` remains integer in envelope, no internal `event_type` suffixing.

## Runtime artifacts
- `scripts/stage1a/comment_extraction_service.py`
- `scripts/stage1a/comment_letter_api.py`
- `scripts/stage1a/evaluation.py`

## Tests
- `tests/stage1a/test_stage1a_slice7_api_workflow.py`
- `tests/stage1a/test_stage1a_slice8_evaluation.py`
- `scripts/db/test_stage1a.sh` (full SQL migration+contract+rollback harness)

## Notes
- Runtime service currently uses in-memory store objects (same pattern as Stage 1B/2 runtime modules).
- DB-backed service adapter can be added later without changing endpoint/event contracts.
