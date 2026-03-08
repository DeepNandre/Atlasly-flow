# Stage 1A: Comment Extraction

## Title
Stage 1A: Municipal Comment Letter Extraction MVP

## Goal
Convert unstructured municipal review PDFs into structured, reviewable extraction records in minutes.

## Scope (In)
- Upload and parse municipal comment letters (scanned and digital PDFs).
- Extract comment-level structured objects with confidence metadata.
- Discipline classification and code reference extraction.
- Human review queue for low-confidence extractions.

## Out of Scope
- Automatic task creation and routing.
- AHJ portal status polling.
- Predictive reviewer behavior recommendations.

## Dependencies
- Stage 0 document ingestion, OCR status, audit, and event primitives.
- Prompt/config management for extraction models.
- Gold-labeled benchmark dataset for quality evaluation.

## Data model changes

### Schema changes
- New tables: `comment_letters`, `comment_extractions`, `extraction_reviews`, `extraction_feedback`.
- `comment_extractions` required fields: `comment_id`, `letter_id`, `raw_text`, `discipline`, `severity`, `requested_action`, `code_reference`, `page_number`, `confidence`, `status`.
- Indexes:
  - `(letter_id, status)` on `comment_extractions`.
  - `(project_id, created_at)` on `comment_letters`.

## APIs / interfaces

### REST endpoints
- `POST /comment-letters`: upload letter and start extraction pipeline.
- `GET /comment-letters/{letterId}`: retrieval of parse status and summary.
- `GET /comment-letters/{letterId}/extractions`: list extraction candidates.
- `POST /comment-letters/{letterId}/approve`: approve corrected extraction set.
- `POST /api/stage1a/upload`: queue file upload for OCR parsing.
- `POST /api/stage1a/process-upload`: process queued upload job (or next queued job).
- `GET /api/stage1a/quality-report?target=staging|prod`: release-gate and drift report from benchmark metrics.

### Event contracts
- Producer: parser worker -> `comment_letter.parsing_started` with `letter_id`, `document_id`, `started_at`.
- Producer: parser worker -> `comment_letter.extraction_completed` with `letter_id`, `extraction_count`, `avg_confidence`, `completed_at`.
- Producer: review service -> `comment_letter.approved` with `letter_id`, `approved_by`, `approved_at`.

### Security constraints
- Access restricted to project members with at least `reviewer` role.
- Extracted content inherits document access policies.
- Model prompts and responses stored with redaction controls for sensitive data.

## Operational requirements
- Async extraction pipeline with retry/backoff and per-document idempotency keys.
- Observability on parse time, failure rates, and confidence distributions.
- Manual override tooling for extraction correction.

## Acceptance criteria
- KPI: discipline classification precision >= 0.90 on benchmark set.
- KPI: comment capture recall >= 0.85 on benchmark set.
- KPI: median end-to-end extraction turnaround <= 10 minutes for <= 50-page letters.
- Exit criteria: approved extraction records are immutable snapshots and auditable.

## Risks and mitigations
- Risk: OCR errors on low-quality scans.
  - Mitigation: multi-pass OCR fallback and page-level confidence flagging.
- Risk: hallucinated code references.
  - Mitigation: require source quote spans and validation rules for citation format.
- Risk: quality drift across municipalities.
  - Mitigation: stratified benchmark set by AHJ and monthly regression suite.

## Milestones (Week-by-week)
- Week 1: extraction schema, benchmark definitions, baseline parser pipeline.
- Week 2: discipline/code-reference extraction and confidence scoring.
- Week 3: review queue UI/API, approval workflow, audit hooks.
- Week 4: benchmarking, quality tuning, production readiness gate.
