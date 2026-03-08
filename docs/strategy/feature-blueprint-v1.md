# Atlasly Feature Blueprint v1 (Implementation Detail)

Date: March 3, 2026
Canonical source for mission/vision remains: `docs/master-prd.md`

## 1. Product scope definition

### Primary users
- General Contractor PM
- Permit Coordinator / Reviewer
- Trade Partner (subcontractor)
- Org Admin / Owner
- Finance Ops

### Jobs-to-be-done
1. Know exactly what to submit for a project and jurisdiction.
2. Submit a complete package with minimal manual copy/paste.
3. Track every permit state and reviewer feedback without portal hopping.
4. Convert comment letters into routed, accountable tasks in minutes.
5. Predict and reduce rejection risk before resubmission.
6. Tie permit milestones to controlled financial actions.

## 2. Baseline entities and state models

### Core entities
- Organization, Workspace, User, Membership (RBAC)
- Project
- Permit
- Document + DocumentVersion
- CommentLetter + Extraction + Review + ApprovalSnapshot
- Task + RoutingRule + EscalationPolicy
- IntakeSession + PermitApplication
- PermitStatusEvent + PermitStatusProjection + TransitionReview
- PreflightScore + FeatureSnapshot
- PayoutInstruction + ProviderWebhookEvent + ReconciliationRun

### Canonical permit status states
`draft -> submitted -> in_review -> corrections_required -> approved -> issued`
Terminal: `expired`

### Task status states
`todo -> in_progress -> blocked -> done`
Operational overlays: `escalated`, `manual_queue`

## 3. Feature blueprint by module

## Module A: Portfolio and control tower (must-have baseline)
Goal:
- One pane for all projects, permits, task load, and sync health.

Required UI/UX:
- Portfolio KPI cards (issued rate, in-review count, blocker aging, open task count)
- Project table with permit status rollups
- Activity feed across Stage 0/1/2/3 events

Required backend behavior:
- Aggregate data by organization and workspace
- Show both latest normalized status and source raw status
- Filter by project code, AHJ, permit type, risk band

Acceptance criteria:
- Page loads in <2s for 200 projects in demo benchmark
- No cross-tenant leakage in aggregated endpoints

## Module B: AHJ intelligence + intake orchestration (Stage 2 parity core)
Goal:
- Deterministically map project facts to AHJ requirements and intake completion.

Key features:
- Dynamic intake questionnaire by permit type and jurisdiction
- Required field engine with validation hints
- AHJ requirement snapshots with versioning
- Form mapping audit trail (which source field mapped to which target field)

APIs:
- `POST /api/intake/sessions`
- `PATCH /api/intake/sessions/{id}` with optimistic concurrency
- `POST /api/permit-applications/generate`

Events:
- `intake.completed`
- `permit.application_generated`

Acceptance criteria:
- 95%+ required fields auto-populate for supported permit templates
- Idempotent generation by key per org

## Module C: Comment Ops (Stage 1A + 1B wedge)
Goal:
- Convert municipal comments into routed execution in <10 minutes.

Key features:
- OCR/multimodal parsing from PDFs
- Extraction confidence scoring with needs-review queue
- Reviewer approval snapshot and immutable event log
- Deterministic task generation from approved extraction IDs
- Rule-based auto-routing + manual fallback queue
- SLA timers and escalation events

APIs:
- `POST /api/comment-letters`
- `GET /api/comment-letters/{id}/extractions`
- `POST /api/comment-letters/{id}/approve`
- `POST /api/tasks/from-extractions`

Events:
- `comment_letter.extracted`
- `comment_letter.approved`
- `tasks.bulk_created_from_extractions`
- `task.auto_assigned`
- `task.manual_queueed`

Acceptance criteria:
- Extraction precision >= 0.9 on benchmark set
- Task generation idempotency conflict-safe under retry storms
- 80%+ of extraction tickets auto-routed in target trade vertical

## Module D: City Sync and reconciliation (Stage 2 reliability core)
Goal:
- Replace portal refresh behavior with trusted normalized status events.

Key features:
- Connector run lifecycle (scheduled/manual/forced)
- Retry with backoff + dead-letter tracking
- Raw status to normalized status mapping ruleset
- Invalid transition handling to manual review queue
- Drift detection and reconciliation reports

APIs:
- `POST /api/sync/runs`
- `GET /api/permits/{permit_id}/timeline`
- `GET /api/sync/reconciliation-runs/{id}`

Events:
- `permit.status_observed`
- `permit.status_changed`
- `permit.status_review_required`

Acceptance criteria:
- No duplicate status events for same event hash per org
- <1% polling runs end with unknown error after retries

## Module E: Enterprise readiness and governance (Stage 0.5)
Goal:
- Make the platform sellable to mid-market/enterprise teams.

Key features:
- API key lifecycle management
- Webhook control plane and signing
- Audit exports and immutable operational log
- Dashboard snapshots for cycle-time and blocker aging
- Row-level security across all tenant data

Acceptance criteria:
- Every mutable action writes auditable actor + request trace
- API credentials rotate without downtime

## Module F: Predictive moat and preflight intelligence (Stage 3)
Goal:
- Proactively reduce rejection probability and cycle-time variance.

Key features:
- AHJ behavior model keyed by permit type + reviewer signals
- Preflight risk scoring API with explainability factors
- Recommendation generation linked to evidence refs
- Model registry + snapshot references for reproducibility

APIs:
- `GET /api/projects/{id}/preflight-risk`

Events:
- `permit.preflight_scored`

Acceptance criteria:
- Risk score reproducible from stored feature snapshot and model version
- Top factors exposed for user explanation panel

## Module G: Milestone-based payouts and financial controls (Stage 3)
Goal:
- Tie permit outcomes to controlled disbursement workflows.

Key features:
- Payout instruction creation with role + step-up checks
- Provider webhook ingestion and state transitions
- Settlement reconciliation and mismatch taxonomy
- Outbox pattern for downstream accounting integrations

APIs:
- `POST /api/milestones/{id}/financial-actions`
- `POST /api/provider/webhooks`
- `POST /api/reconciliation-runs`

Events:
- `financial.payout_instruction_created`
- `financial.payout_state_changed`
- `financial.reconciliation_completed`

Acceptance criteria:
- Idempotent payout creation by organization key
- Reconciliation run includes matched/mismatched counts and details

## 4. Non-functional requirements

### Security
- Strict tenant boundary on every read/write path
- RBAC enforced server-side, never UI-trusted
- Signed webhook events with replay protection

### Reliability
- Outbox-based event publication where external side effects exist
- Retry policies with bounded backoff and DLQ visibility
- Deterministic idempotency semantics across APIs

### Observability
- Trace IDs propagated across API and event envelopes
- Run-level metrics: success rate, replay ratio, queue depth, SLA breaches

### Performance targets (MVP)
- P95 API latency under 500ms for metadata endpoints
- P95 timeline endpoint under 1s for 1,000 event history

## 5. Vertical-specific launch overlays (post-core)

### Solar / EV charging
- SolarAPP+ eligibility checks
- Utility/interconnection milestone tracking

### Commercial MEP
- Discipline-specific routing templates and reviewer cheat-sheets

## 6. Exit criteria for MVP readiness
The MVP is considered ready when all are true:
1. Stage 1A+1B pipeline handles real comment letters with reviewer approval and deterministic routing.
2. Stage 2 intake + status sync produces trusted permit timelines for supported AHJs.
3. Portfolio UI exposes project-level status, blockers, and activity in a testable browser workflow.
4. Stage 3 preflight + payout orchestration runs end-to-end in sandbox mode.
5. Security/audit/event contracts are enforced in tests and validated in smoke checks.
