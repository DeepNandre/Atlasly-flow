# Stage 1A Research

Status: In Progress (kickoff planning complete)
Owner: Stage 1A agent
Last updated: 2026-03-02

## 1. Stage objective recap
- Convert scanned/digital municipal comment PDFs into structured comment extraction records quickly and reliably.
- Produce comment-level fields (`discipline`, `severity`, `requested_action`, `code_reference`, `confidence`, `status`) with page attribution.
- Route low-confidence outputs into human review before approval.
- Meet Stage 1A quality/latency gates: precision >= 0.90, recall >= 0.85, median <= 10 minutes for <= 50 pages.

## 2. Deep research findings (initial, from canonical docs)
### Architecture
- Stage 1A is gated on Stage 0 primitives: ingestion, OCR status, audit, and event infrastructure.
- Pipeline must be async, idempotent per document, and observable with parse latency/failure/confidence metrics.
- Event flow required:
  - `comment_letter.parsing_started`
  - `comment_letter.extraction_completed`
  - `comment_letter.approved`

### Tooling
- Need multimodal parsing path that handles both text PDFs and low-quality scans.
- Must support citation-grounded extraction (source quote spans + page number) to reduce hallucinated code references.
- Prompt/config management is a hard dependency for extraction model control and safe iteration.

### Operations
- Manual override and correction tooling is mandatory (review queue + approve corrected set).
- Prompt/response storage requires redaction controls and access inheritance from source documents.
- Benchmarks must be stratified by AHJ segment and discipline to detect municipality drift.

### Risks
- OCR quality variance can suppress recall; mitigate with multipass OCR and page-level confidence flags.
- Hallucinated code references can create legal/operational risk; require citation validation rules.
- Cross-municipality drift requires recurring regression runs and threshold tuning.

## 3. Recommended implementation approach (step-by-step)
1. Finalize Stage 1A extraction contract and confidence semantics before model tuning.
2. Implement ingestion-to-extraction async workflow with idempotency and retries.
3. Build hybrid parser path:
   - text-native extraction for digital PDFs
   - OCR-first extraction for scanned pages
4. Add structured extraction normalizer (discipline/severity/action/code reference/page quote span).
5. Implement confidence scorer (field-level + record-level) and status transitions (`auto_accepted` vs `needs_review`).
6. Ship review queue endpoints/UI actions and immutable approval snapshotting.
7. Add benchmark harness and quality gates in CI/regression jobs.
8. Run staged rollout by AHJ cohort; monitor precision/recall/latency before general release.

## 4. Required APIs/data/contracts and schema guidance
- Required tables:
  - `comment_letters`
  - `comment_extractions`
  - `extraction_reviews`
  - `extraction_feedback`
- Required indexes:
  - `(letter_id, status)` on `comment_extractions`
  - `(project_id, created_at)` on `comment_letters`
- Required endpoints:
  - `POST /comment-letters`
  - `GET /comment-letters/{letterId}`
  - `GET /comment-letters/{letterId}/extractions`
  - `POST /comment-letters/{letterId}/approve`
- Required events:
  - `comment_letter.parsing_started`
  - `comment_letter.extraction_completed`
  - `comment_letter.approved`
- Schema guidance:
  - Include provenance fields for every extracted item (`document_id`, `page_number`, `quote_span`).
  - Persist both field-level confidence and aggregate confidence.
  - Keep approval output immutable and versioned for audit trails.

## 5. Build-vs-buy decisions and tradeoffs
- OCR engine:
  - Buy/API OCR yields faster start, but higher per-page cost and vendor lock-in.
  - Self-host OCR lowers unit cost at scale, but increases ops burden.
- Extraction model:
  - Hosted multimodal LLM improves iteration speed and quality baseline.
  - Self-hosted models improve data residency/control but increase MLOps complexity.
- Recommended default for Stage 1A MVP:
  - Managed OCR + managed multimodal LLM + strict post-processing validator layer.

## 6. Validation and test plan
- Dataset:
  - Build gold-labeled benchmark set stratified by discipline, AHJ type, and scan quality.
- Metrics:
  - Discipline precision, comment recall, citation validity rate, median/p95 latency, review-queue rate.
- Tests:
  - Contract tests for endpoints/events/schema.
  - Regression suite on fixed benchmark monthly and pre-release.
  - Adversarial tests for noisy scans and malformed code references.
- Gates:
  - Block release if precision/recall/latency KPIs regress below thresholds.

## 7. Execution checklist (ordered, dependency-aware)
1. Confirm Stage 0 dependencies are complete and callable.
2. Write DB migration spec for Stage 1A tables/indexes.
3. Define extraction JSON schema and confidence taxonomy.
4. Implement parser worker orchestration + event publishing.
5. Implement extraction normalization + citation validation rules.
6. Implement review queue + approval workflow + immutable snapshotting.
7. Implement benchmark harness + KPI dashboards + alert thresholds.
8. Run AHJ-stratified pilot and capture feedback for Stage 1B handoff.

## 8. Open risks and unknowns with mitigation plan
- Unknown: target AHJ mix and document quality distribution.
  - Mitigation: gather sample set before threshold freeze; segment metrics by cohort.
- Unknown: acceptable human-review volume at launch.
  - Mitigation: tune confidence thresholds to cap queue load while preserving recall.
- Unknown: long-tail code citation formats across jurisdictions.
  - Mitigation: rule-based validators + reviewer feedback loop into extraction prompts.
- Unknown: exact Stage 0 interface contracts available in implementation repo.
  - Mitigation: produce integration contract checklist before build kickoff.

## 9. Resource list
### Canonical project docs
- `docs/master-prd.md`
- `docs/stages/README.md`
- `docs/stages/stage-1a-comment-extraction.md`
- `docs/agents/shared-context.md`
- `docs/agents/stage-1a-agent-prompt.md`

### Next research sources to collect (official-first)
- OCR vendor/model official docs and limits.
- Selected multimodal model API docs and structured output constraints.
- Benchmarking/evaluation references for information extraction quality in scanned documents.

## Task 2

### 1) Final extraction JSON schema (field-by-field definitions and constraints)
```json
{
  "letter_id": "uuid",
  "document_id": "uuid",
  "project_id": "uuid",
  "extraction_version": "string",
  "extractions": [
    {
      "comment_id": "string",
      "raw_text": "string",
      "discipline": "string",
      "severity": "string",
      "requested_action": "string",
      "code_reference": {
        "value": "string",
        "jurisdiction": "string",
        "code_family": "string",
        "valid_format": "boolean"
      },
      "page_number": "integer",
      "citation": {
        "quote": "string",
        "char_start": "integer",
        "char_end": "integer"
      },
      "confidence": {
        "raw_text": "number",
        "discipline": "number",
        "severity": "number",
        "requested_action": "number",
        "code_reference": "number",
        "citation": "number",
        "record": "number"
      },
      "status": "string",
      "normalization_flags": ["string"]
    }
  ],
  "summary": {
    "extraction_count": "integer",
    "avg_record_confidence": "number",
    "requires_review_count": "integer"
  }
}
```

Constraints:
- `letter_id`, `document_id`, `project_id`: required UUIDv4.
- `extraction_version`: required semver string (`v1.0.0` style).
- `comment_id`: required, deterministic per item; format `cmt_{page}_{sha1(raw_text_norm)[0:12]}`.
- `raw_text`: required, trimmed, 20-4000 chars.
- `discipline`: required enum: `structural|electrical|plumbing|mechanical|fire|zoning|civil|architectural|energy|accessibility|other`.
- `severity`: required enum: `critical|major|minor|info`.
- `requested_action`: required, imperative rewrite of requested fix, 10-1000 chars.
- `code_reference.value`: optional string; if empty set `""`, never `null`.
- `code_reference.jurisdiction`: optional normalized AHJ short code (`CITY_ST`, `COUNTY_ST`).
- `code_reference.code_family`: optional enum: `IBC|IRC|IECC|IFC|NEC|IPC|IMC|NFPA|LOCAL|UNKNOWN`.
- `code_reference.valid_format`: required boolean.
- `page_number`: required integer >= 1 and <= letter page count.
- `citation.quote`: required non-empty string (8-600 chars) that must exist on `page_number`.
- `citation.char_start`/`char_end`: required inclusive bounds with `0 <= start < end`.
- `confidence.*`: all required floats in `[0.0,1.0]`, rounded to 3 decimals.
- `status`: required enum: `auto_accepted|needs_review|reviewed_corrected|approved_snapshot`.
- `normalization_flags`: optional enum array:
  - `code_ref_unverified`
  - `discipline_low_signal`
  - `ocr_low_quality_page`
  - `citation_span_fuzzy_match`
  - `possible_duplicate`

### 2) Confidence scoring design (field-level + record-level formulas and thresholds)
Hard choice:
- Model path: single primary multimodal extraction model with structured JSON output, plus deterministic validator/rules layer. No model ensemble in Stage 1A.
- OCR path: hybrid.
  - Primary: native PDF text extraction when text layer quality score >= 0.85.
  - Fallback: managed OCR on low-text/scan pages; second OCR pass only for pages with OCR confidence < 0.80.
- Review thresholds:
  - `record_confidence >= 0.92` and no hard guardrail violations => `auto_accepted`.
  - `0.70 <= record_confidence < 0.92` or any soft violation => `needs_review`.
  - `< 0.70` or any hard violation => `needs_review` (priority high).

Field-level confidence formulas:
- `c_raw_text = text_match_score` where match score is exact/fuzzy overlap of extracted text with source span.
- `c_discipline = model_prob_discipline * keyword_alignment_factor`.
- `c_severity = model_prob_severity * severity_rule_alignment`.
- `c_requested_action = action_verb_score * completeness_score`.
- `c_code_reference = model_prob_code_ref * format_validity_factor * source_presence_factor`.
- `c_citation = exact_span_match ? 1.0 : fuzzy_span_score`.

Record-level formula:
- `c_record = 0.22*c_raw_text + 0.18*c_discipline + 0.12*c_severity + 0.20*c_requested_action + 0.18*c_code_reference + 0.10*c_citation`
- Penalties:
  - `-0.20` if missing citation quote.
  - `-0.15` if code reference present but invalid format.
  - `-0.10` if OCR page quality flag on source page.
- Clamp final `c_record` into `[0,1]`.

### 3) End-to-end pipeline state machine (ingest -> OCR -> extract -> normalize -> review -> approve)
States and transitions:
1. `ingest_received`
   - On `POST /comment-letters`, create `comment_letters` row with idempotency key.
   - Emit `comment_letter.parsing_started`.
2. `ocr_precheck`
   - Page-by-page detect text-layer quality.
   - Route pages to `text_extract` or `ocr_required`.
3. `ocr_processing`
   - Run OCR for routed pages.
   - Retry with exponential backoff (max 3 attempts/page).
   - If page permanently fails, mark page degraded and continue.
4. `extracting_comments`
   - Run multimodal extraction over merged page text+image context.
   - Produce candidate JSON objects with per-field confidences.
5. `normalizing_validating`
   - Apply enums, dedupe, code reference normalization, citation span verification.
   - Compute record confidence and `status`.
6. `review_queueing`
   - Insert `needs_review` items into `extraction_reviews`.
   - Keep `auto_accepted` items ready but not final-approved.
7. `human_review` (optional path)
   - Reviewer edits extraction; write correction and rationale to `extraction_feedback`.
   - Set status `reviewed_corrected`.
8. `approval_snapshot`
   - On `POST /comment-letters/{letterId}/approve`, freeze full extraction set as immutable snapshot.
   - Emit `comment_letter.approved` only.
9. `completed`
   - Snapshot available via `GET /comment-letters/{letterId}` and `/extractions`.

Terminal failure state:
- `failed_extraction` only if no usable extraction objects produced and all retries exhausted; record audit trail and error class.

### 4) Citation-grounding and hallucination guardrail rules
Hard guardrails (block auto-accept):
- Every extraction must include `citation.quote` mapped to a valid `page_number`.
- `citation.quote` must be exact substring match on page text; allow fuzzy fallback only for OCR-degraded pages with `citation_span_fuzzy_match`.
- If `code_reference.value` is present, it must satisfy regex family pattern; else set `valid_format=false` and require review.
- No extracted field may include content absent from source page region (detected by lexical overlap floor 0.55).

Soft guardrails (force review):
- Discipline predicted as `other` with `c_discipline < 0.85`.
- Requested action shorter than 12 tokens.
- Multiple comments with >0.95 similarity and same page (possible duplicate).

Redaction/audit controls:
- Store prompt/response artifacts with sensitive token redaction.
- Persist provenance triplet (`page_number`, `char_start`, `char_end`) for every approved field.
- Log all reviewer edits with before/after values and actor identity.

### 5) Benchmark dataset spec and evaluation harness (precision/recall/latency)
Dataset spec:
- Minimum 1,200 labeled comments across 240 letters at launch.
- Stratification:
  - 40% scanned low quality, 35% mixed quality, 25% digital-native.
  - AHJ segments: large metro (40%), mid-market (35%), small/rural (25%).
  - Discipline minimum support: >=100 comments each for top 6 disciplines.
- Label set:
  - Gold spans for `raw_text` and citation.
  - Gold class for `discipline`, `severity`.
  - Gold normalized `requested_action`.
  - Gold `code_reference` validity.

Evaluation harness:
- Run batch extraction against frozen benchmark set.
- Compute:
  - Discipline precision (primary KPI).
  - Comment capture recall (primary KPI).
  - Code reference hallucination rate (`invalid_or_uncited_code_refs / all_code_refs`).
  - Median and p95 end-to-end latency per letter.
  - Review-queue rate and reviewer correction rate.
- Matching rules:
  - Comment-level match via span IoU >= 0.6 plus page equality.
  - Field scoring uses exact for enums, token-F1 for text fields.
- Reporting:
  - Per-AHJ and per-discipline slices mandatory.
  - Weekly dashboard + monthly regression snapshot.

### 6) Release gate policy tied to Stage 1A KPIs
Promotion policy:
- Dev -> Staging gate:
  - Discipline precision >= 0.88.
  - Recall >= 0.82.
  - Median latency <= 12 min (<=50 pages).
  - Hallucinated code reference rate <= 8%.
- Staging -> Prod gate (hard Stage 1A exit):
  - Discipline precision >= 0.90.
  - Recall >= 0.85.
  - Median latency <= 10 min and p95 <= 18 min.
  - Hallucinated code reference rate <= 5%.
  - Approval snapshot immutability and audit trail checks pass 100%.
- Auto-rollback triggers in production:
  - 3-day moving precision < 0.89.
  - 3-day moving recall < 0.84.
  - Median latency > 10 min for two consecutive days.

### 7) Implementation backlog with exact dependencies on Stage 0 services
Backlog (dependency-ordered):
1. Stage 0 contract lock
   - Dependency: Stage 0 document ingestion API (document ID issuance, file storage URI).
   - Dependency: Stage 0 event bus/topic conventions and delivery guarantees.
   - Dependency: Stage 0 audit log write API (append-only actor/action/events).
   - Output: Stage 1A integration contract doc.
2. DB migrations for Stage 1A entities
   - Dependency: Stage 0 tenant/project identity model and RBAC roles.
   - Output: `comment_letters`, `comment_extractions`, `extraction_reviews`, `extraction_feedback` + indexes.
3. Parser worker scaffold + idempotent job runner
   - Dependency: Stage 0 job orchestration/retry primitives and idempotency key store.
   - Output: ingestion->state-machine runner.
4. OCR/text extraction adapter
   - Dependency: Stage 0 OCR status primitives (page quality metadata contract).
   - Output: page-level text corpus with quality/confidence fields.
5. Multimodal extraction + structured output contract
   - Dependency: prompt/config management service from Stage 0.
   - Output: deterministic JSON output with per-field model probabilities.
6. Normalization/validation/confidence module
   - Dependency: none beyond prior steps.
   - Output: schema-valid records, guardrail flags, final status assignment.
7. Review queue API + workflow
   - Dependency: Stage 0 RBAC/authz and audit logging.
   - Output: low-confidence queue, correction actions, reviewer attribution.
8. Approval snapshot + immutable storage path
   - Dependency: Stage 0 audit/event primitives and storage versioning conventions.
   - Output: immutable approved extraction set + `comment_letter.approved` event.
9. Benchmark harness + KPI monitoring
   - Dependency: observability stack from Stage 0 (metrics/logging/alerts).
   - Output: automated regression runs, gates, rollback alarms.

## Task 3

### 1) Reconfirmed extraction states/events vs shared event naming policy
Single source policy (adopted for Stage 1A to remove drift):
- Internal domain event naming: lowercase dot-namespace verb form, no version suffix in `event_type`.
  - Examples: `document.uploaded`, `document.ocr_completed`, `comment_letter.parsing_started`.
- Internal versioning: `event_version` integer in the shared envelope.
- External webhook projection (Stage 0.5+): compose `event_type` + `.v` + `event_version` for header/payload compatibility (example: `comment_letter.extraction_completed.v1`).

Stage 1A extraction state machine (canonical):
- `ingest_received`
- `ocr_precheck`
- `ocr_processing`
- `extracting_comments`
- `normalizing_validating`
- `review_queueing`
- `human_review` (conditional)
- `approval_snapshot`
- `completed`
- `failed_extraction` (terminal failure)

Stage 1A domain events aligned to policy:
- `comment_letter.parsing_started` (`event_version=1`)
- `comment_letter.extraction_completed` (`event_version=1`)
- `comment_letter.approved` (`event_version=1`)

Drift controls:
- Registry lock file must list only canonical internal names above.
- CI contract check fails if code/docs introduce:
  - snake_case or mixed-case event names
  - version suffix inside internal `event_type`
  - unregistered Stage 1A event names

### 2) Exact emission point for `comment_letter.extraction_completed` (happy-path vs review-path)
Decision: emit exactly once, from a single transition: `normalizing_validating -> review_queueing`.

Rationale:
- Extraction is "completed" when machine extraction + normalization + confidence scoring finish, independent of whether human review is required.
- Prevents double emit risk between auto-accept and human-review branches.
- Keeps downstream latency and throughput analytics stable (same semantic checkpoint for all letters).

Canonical emission rule:
- Emit `comment_letter.extraction_completed` immediately after all extraction candidates are persisted and statuses (`auto_accepted`/`needs_review`) are assigned.
- Include:
  - `letter_id`
  - `document_id`
  - `extraction_count`
  - `avg_confidence`
  - `requires_review_count`
  - `completed_at`
- Idempotency key format:
  - `{letter_id}:comment_letter.extraction_completed:v1`

Branch behavior:
- Happy path (`requires_review_count=0`):
  - `extraction_completed` emitted once at normalization finish.
  - Later approval emits only `comment_letter.approved`.
- Review path (`requires_review_count>0`):
  - `extraction_completed` still emitted at same point (once).
  - Human corrections do not re-emit `extraction_completed`.
  - Final approve emits `comment_letter.approved` only.

### 3) Stage 0 dependency contract checklist with pass/fail criteria
Use this checklist before enabling Stage 1A production traffic. Any `FAIL` blocks release.

1. Document ingest contract
- Dependency: `POST /projects/{projectId}/documents` and persisted `document_id`/`version`.
- Pass criteria:
  - Returns stable `document_id` and storage reference.
  - Supports idempotent retries via `Idempotency-Key`.
  - Upload metadata retrievable within 2 seconds p95 after commit.
- Fail criteria:
  - Duplicate records on retry.
  - Missing or mutable `document_id` identity.

2. OCR completion event contract
- Dependency: `document.ocr_completed` event with shared envelope fields.
- Pass criteria:
  - Event includes `event_id`, `event_type`, `event_version`, `organization_id`, `aggregate_id`, `occurred_at`, `idempotency_key`, `payload`.
  - Payload includes `document_id`, `ocr_status`, `page_count`, `completed_at`.
  - Signature verification succeeds for 100% sampled events.
- Fail criteria:
  - Missing required envelope fields.
  - Unsigned or unverifiable events.

3. Event bus idempotency + dedupe
- Dependency: Stage 0 outbox and consumer dedupe primitives.
- Pass criteria:
  - Replay of same idempotency key does not create duplicate Stage 1A rows/events.
  - At-least-once delivery tolerated with no duplicate side effects in extraction pipeline.
- Fail criteria:
  - Duplicate `comment_letter.parsing_started` or `extraction_completed` for one letter run.

4. Audit append-only contract
- Dependency: Stage 0 audit event write path.
- Pass criteria:
  - Every Stage 1A state transition writes immutable audit entry with actor/service identity.
  - Reviewer edits include before/after payloads.
- Fail criteria:
  - Any missing transition audit event.
  - Mutable/deletable audit rows for non-admin actors.

5. RBAC and tenant isolation
- Dependency: Stage 0 org scoping + roles (`reviewer` minimum for extraction review actions).
- Pass criteria:
  - Cross-tenant access tests: 100% deny.
  - Non-reviewer cannot approve extraction snapshot.
  - Project-scoped reviewer can read/write only in authorized org/project.
- Fail criteria:
  - Any cross-tenant read/write success.
  - Approve endpoint callable by unauthorized role.

6. Domain event envelope compatibility for Stage 1A events
- Dependency: shared envelope + publisher worker.
- Pass criteria:
  - Stage 1A events published with canonical `event_type` and integer `event_version=1`.
  - Webhook projection (if enabled) emits `<event_type>.v1` consistently.
- Fail criteria:
  - Mixed naming conventions in same environment.
  - Internal event emitted with embedded `.v1` suffix.

7. Observability baseline for gate metrics
- Dependency: Stage 0 metrics/logging/trace primitives.
- Pass criteria:
  - Metrics available: extraction latency (median/p95), failure rate, confidence distribution, review queue rate.
  - Logs include `trace_id`, `organization_id`, `letter_id`, `document_id`.
  - Alert rules active for KPI gate breaches.
- Fail criteria:
  - Any KPI required by Stage 1A release gate is not queryable.
