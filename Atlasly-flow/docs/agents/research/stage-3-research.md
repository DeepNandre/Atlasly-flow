# Stage 3 Research

Status: In Progress
Owner: Stage 3 agent
Last updated: 2026-03-03

## 1. Stage objective recap
- Build proprietary AHJ intelligence that predicts correction risk before submission, with evidence-backed recommendations and explainability.
- Introduce milestone-based payout orchestration that only triggers on verified permit lifecycle events from Stage 2 normalized status streams.
- Preserve enterprise trust through strict auditability, model governance, RBAC + step-up auth on financial actions, and reconciliation-first operations.
- Deliver measurable outcomes: reduce correction-cycle frequency by >=20% (assisted vs control) and maintain 100% daily settlement reconciliation match.

## 2. Deep research findings
### Architecture
- Split Stage 3 into four bounded services with event contracts:
  - `intelligence-service`: feature computation, scoring, recommendations, model metadata.
  - `milestone-service`: verification rules, milestone state machine, evidence capture.
  - `payout-service`: payout instruction creation, provider adapters, idempotent dispatch.
  - `finance-ledger-service`: append-only financial events, reconciliation, exception queue.
- Use an offline/online feature-store pattern for AHJ behavior features:
  - Offline snapshots for training/backtesting.
  - Online point-in-time reads for low-latency scoring and drift monitoring.
- Keep recommendations and payouts decoupled by event choreography (not synchronous RPC) so payout processing remains stable during model incidents.
- Treat `milestone.verified` as the sole payout eligibility trigger; never pay from raw permit-status events directly.

### Tooling
- Model stack:
  - Baseline: interpretable gradient-boosted model + calibrated confidence output.
  - Explainability: top risk factors stored per prediction, mapped to AHJ evidence slices.
  - Governance: model registry with semantic versioning + approval gates.
- Data quality stack:
  - Feature freshness checks, leakage checks, schema-contract tests for events.
  - Shadow scoring in pre-production before rollout to production decisions.
- Fintech stack:
  - Provider-agnostic payout adapter interface.
  - Idempotency keys at instruction creation and provider dispatch boundaries.
  - Double-entry internal ledger independent of provider status webhooks.

### Operations
- Daily control loops:
  - Model health: drift, precision/recall by AHJ segment, false-positive review.
  - Finance health: provider settlement import, internal ledger matching, exception triage.
- Access controls:
  - Financial action endpoints limited to `owner` and `admin`.
  - Step-up authentication required for payout initiation and reversals.
- Incident management:
  - Playbooks for duplicate instruction attempts, failed payouts, delayed settlement files, and webhook outages.
  - Freeze switch to disable new payout dispatch while preserving ledger/event ingestion.

### Risks
- Sparse AHJ history can produce unstable model behavior for long-tail jurisdictions.
  - Mitigation: confidence-banded outputs, fallback heuristics, mandatory human review for low-support segments.
- False confidence in recommendations can create legal/operational exposure.
  - Mitigation: evidence citations, confidence labels, explicit non-legal-advice framing.
- Payment-provider mismatch and timing drift can create ledger breaks.
  - Mitigation: immutable event ledger, strict daily reconciliation gate, capped pilot transaction volume.

## 3. Recommended implementation approach (step-by-step)
1. Lock Stage 2 dependency contract: verify normalized permit events are stable, complete, and replay-safe.
2. Implement Stage 3 schema objects and indexes (`ahj_behavior_features`, `preflight_risk_scores`, `recommendation_runs`, `milestones`, `payout_instructions`, `financial_events`, `reconciliation_runs`).
3. Build `intelligence-service` baseline:
   - Feature pipelines, training dataset builder, baseline model, scoring API, event emission.
4. Add explainability + audit package:
   - Persist `top_risk_factors`, model version, source evidence references, generation timestamps.
5. Build preflight API surface:
   - `GET /projects/{projectId}/preflight-risk`
   - `POST /projects/{projectId}/preflight-recommendations`
6. Build milestone domain + verification rules:
   - Deterministic state machine (`pending -> verified -> payable -> paid/failed/reversed`).
7. Build payout orchestration and provider adapter:
   - `POST /milestones/{milestoneId}/financial-actions`
   - Idempotent instruction creation + dispatch + callback processing.
8. Build ledger + reconciliation:
   - Daily run pipeline and `GET /financial/reconciliation-runs/{runId}`.
9. Run capped pilot:
   - Confidence-gated model outputs + transaction limits + manual approval for exceptional payouts.
10. Tune and gate GA with explicit exit criteria and rollback plans.

## 4. Required APIs/data/contracts and schema guidance
- REST endpoints (stage-defined):
  - `GET /projects/{projectId}/preflight-risk`
  - `POST /projects/{projectId}/preflight-recommendations`
  - `POST /milestones/{milestoneId}/financial-actions`
  - `GET /financial/reconciliation-runs/{runId}`
- Required events:
  - `permit.preflight_scored`
  - `permit.recommendations_generated`
  - `milestone.verified`
  - `payout.instruction_created`
- Contract guidance:
  - Include `idempotency_key`, `event_id`, `trace_id`, `occurred_at`, `source_service`, `schema_version`.
  - Enforce backward-compatible event versioning; additive-only during pilot.
  - Store point-in-time feature snapshot hashes for every score to support reproducibility.
- Schema guidance:
  - `preflight_risk_scores`: `score`, `band`, `model_version`, `calibration_version`, `feature_snapshot_ref`.
  - `recommendation_runs`: `recommendation_json`, `evidence_refs`, `confidence`, `generated_by_model_version`.
  - `financial_events`: append-only debit/credit entries with `external_ref`, `event_type`, `amount`, `currency`, `balance_delta`.
  - `reconciliation_runs`: provider file/checksum refs, matched/mismatched counts, disposition status.

## 5. Build-vs-buy decisions and tradeoffs
- Model infrastructure:
  - Build core feature + scoring pipeline (proprietary moat).
  - Buy/managed where useful for registry/monitoring to reduce ops burden.
- Explainability:
  - Build domain evidence mapping (AHJ-specific rationale is differentiator).
  - Buy generic observability/monitoring components.
- Payout rails:
  - Buy via established payout provider(s); do not build money movement rails.
  - Build payout policy engine, milestone gating logic, and internal ledger controls.
- Reconciliation:
  - Build deterministic reconciliation logic and exception handling.
  - Buy provider ingestion connectors if available to reduce integration time.

## 6. Validation and test plan
- Data/model tests:
  - Point-in-time correctness tests for features.
  - Offline backtests segmented by AHJ, permit type, and data density.
  - Shadow deployment before serving live scores.
- API/event tests:
  - Contract tests for all Stage 3 endpoints/events.
  - Replay/idempotency tests for duplicate events and retries.
- Finance tests:
  - Ledger invariants (sum debits == sum credits).
  - Reconciliation tests with synthetic mismatch scenarios.
  - Webhook reorder/duplication/failure simulation.
- End-to-end acceptance:
  - Assisted vs control cohort experiment for correction-cycle KPI.
  - Daily reconciliation must hit 100% match before lifting transaction caps.

## 7. Execution checklist (ordered, dependency-aware)
1. Confirm Stage 2 event reliability and define freeze window for contract changes.
2. Apply Stage 3 schema migrations and index rollout.
3. Implement intelligence feature pipeline and baseline model training.
4. Ship preflight risk/recommendation APIs with audit fields.
5. Add model governance controls (registry, approval, rollback).
6. Implement milestone verification state machine and evidence records.
7. Implement payout instruction orchestration with idempotent provider adapter.
8. Implement append-only ledger and daily reconciliation jobs.
9. Write incident runbooks and activate freeze switch controls.
10. Launch capped pilot; monitor KPIs and reliability; decide GA at Week 6 gate.

## 8. Open risks and unknowns with mitigation plan
- Unknown: minimum historical volume needed per AHJ for reliable prediction.
  - Plan: define support thresholds; route low-support cases to human-only recommendations.
- Unknown: legal constraints by state on milestone-triggered payouts and invoice automation.
  - Plan: legal review packet per launch state, configurable policy rules by jurisdiction.
- Unknown: provider settlement timing variance impact on daily close windows.
  - Plan: configurable reconciliation cutoffs + late-arrival handling states.
- Unknown: operational burden of exceptions during pilot.
  - Plan: strict caps, manual approval queue, and weekly control review cadence.

## 9. Resource list (official docs first, then high-signal references)
- Internal product specs:
  - `docs/agents/shared-context.md`
  - `docs/agents/stage-3-agent-prompt.md`
  - `docs/stages/stage-3-moat-predictive-fintech.md`
  - `docs/stages/stage-2-parity-intake-autofill-sync.md`
  - `docs/master-prd.md`
- Official references to include in next research pass:
  - Payment provider payout + reconciliation docs (selected provider in implementation).
  - NIST AI RMF guidance for model governance controls.
  - SOC 2 / ISO 27001 control mappings for financial workflow operations.
  - OWASP ASVS/MASVS-relevant auth controls for step-up authentication patterns.

## Task 2

### 1) Feature-store and model lifecycle design (training, registry, deployment, rollback)
- Feature store architecture:
  - Offline store: immutable daily feature snapshots keyed by `(permit_id, as_of_at)` for reproducible training/backtests.
  - Online store: low-latency keyed reads on `(ahj_id, permit_type, project_profile_hash)` for scoring.
  - Point-in-time join enforcement to prevent leakage from post-submission outcomes.
- Training lifecycle:
  - Trigger: weekly retrain + on-demand retrain after drift or major schema/event changes.
  - Data window: trailing 12-18 months with cohort weighting by AHJ density and permit type.
  - Labels: correction-cycle occurrence, review turnaround delay bins, outcome confidence.
  - Outputs: model artifact, calibration artifact, feature schema hash, training report.
- Registry lifecycle:
  - States: `draft -> validated -> approved -> deployed -> retired`.
  - Required metadata: `model_version`, training dataset ID, feature schema hash, metrics by segment, approver.
  - Promotion gate: no severe metric regressions on protected AHJ/permit segments.
- Deployment pattern:
  - `shadow` (100% traffic, no user impact) -> `canary` (5-10%) -> `ramped` (25/50/100%).
  - Online inference includes `model_version` and `calibration_version` on every score record.
- Rollback plan:
  - One-click revert to last `approved` model version.
  - Automatic rollback trigger on breach: calibration drift threshold, severe precision drop, or elevated false-positive queue.
  - Rollback preserves full audit lineage; no deletion of prior artifacts.

### 2) Preflight scoring contract (inputs, outputs, explainability payload, confidence policy)
- Endpoint: `GET /projects/{projectId}/preflight-risk`
- Inputs:
  - Path: `projectId`
  - Required context: `permit_type`, `ahj_id`, project attributes (scope, valuation band, occupancy/use category, discipline mix), latest submission package completeness score.
  - Optional: upstream design-check signals (if available), prior correction history for same org + AHJ.
- Output payload:
  - `risk_score` (0-1 float), `risk_band` (`low|medium|high|critical`), `confidence_score` (0-1), `model_version`, `scored_at`.
  - `top_risk_factors[]`: `{factor_code, factor_label, contribution, evidence_ref_ids[]}`.
  - `recommended_actions[]`: `{action_id, action_text, expected_impact, priority, owner_role}`.
- Explainability payload requirements:
  - At least 3 and at most 7 risk factors.
  - Each factor must map to an evidence record from historical AHJ behavior features or project completeness checks.
  - Explanations must be human-readable and exportable for audits.
- Confidence policy:
  - `confidence_score >= 0.75`: auto-publish recommendations.
  - `0.45 <= confidence_score < 0.75`: publish with reviewer confirmation required.
  - `< 0.45`: suppress auto recommendations; route to manual analyst workflow.
  - Low-support AHJs always capped at `reviewer confirmation required` until minimum data threshold is reached.

### 3) Milestone verification state machine and evidence requirements
- State machine:
  - `draft -> pending_verification -> verified -> payout_eligible -> payout_initiated -> paid`
  - Failure branches: `verification_failed`, `payout_failed`, `reversed`.
  - Terminal states: `paid`, `reversed`, `verification_failed` (unless reopened by admin override workflow).
- Transition rules:
  - `pending_verification -> verified` only from trusted status-event source + rule checks.
  - `verified -> payout_eligible` only if policy checks pass (role, amount caps, beneficiary status, no hold flags).
  - `payout_eligible -> payout_initiated` only via idempotent financial action command.
- Evidence requirements (must be stored before `verified`):
  - Normalized permit event IDs and raw provider/source reference.
  - Timestamp lineage (`occurred_at`, `received_at`, `verified_at`) and verifying rule version.
  - Actor context (`system` or human approver ID), plus rationale for overrides.
  - Optional attachments hash (documents/screenshots) for audit exports.

### 4) Payout orchestration flow with idempotency and failure handling
- Provider-safe orchestration (no legal escrow semantics):
  1. `POST /milestones/{milestoneId}/financial-actions` receives command with `idempotency_key`.
  2. Validate milestone in `payout_eligible`, beneficiary readiness, org limits, and step-up auth token.
  3. Create `payout_instruction` record in `created` state (idempotent on `(milestone_id, idempotency_key)`).
  4. Emit `payout.instruction_created`; async worker dispatches to provider adapter.
  5. Provider response updates instruction to `submitted|failed_transient|failed_terminal`.
  6. Webhooks/polling reconcile to `settled|failed|reversed`.
- Idempotency rules:
  - API layer dedupes repeated requests for 24h+ using client idempotency key.
  - Worker dedupes outbound provider calls with provider idempotency token persisted in instruction record.
  - Webhook processor dedupes by provider event ID + signature timestamp.
- Failure handling:
  - `failed_transient`: exponential backoff retry with capped attempts.
  - `failed_terminal`: move to exception queue, require operator action.
  - Duplicate detection: auto-mark duplicate as `ignored_duplicate`, emit audit event.
  - Reversal handling: create compensating financial events only; never mutate historical records.

### 5) Ledger + reconciliation specification (daily close, mismatch handling, controls)
- Ledger design:
  - Append-only `financial_events` with double-entry postings (`debit_account`, `credit_account`, `amount`, `currency`, `external_ref`).
  - Event types: `instruction_created`, `instruction_submitted`, `provider_settled`, `provider_failed`, `reversal_posted`, `adjustment_posted`.
  - Immutable provenance: `trace_id`, `source_service`, `schema_version`, `recorded_at`.
- Daily close process:
  - Cutoff: configured org-local close window (default 00:00 local).
  - Steps: ingest provider settlement/report files -> normalize -> match by external refs and amount/currency -> persist `reconciliation_runs`.
  - Close succeeds only if run status is `matched` and mismatch count is zero.
- Mismatch handling:
  - Classes: `timing_gap`, `amount_mismatch`, `missing_internal`, `missing_provider`, `duplicate_provider_event`.
  - Generate exception tickets with SLA and owner assignment.
  - Late-arriving provider records handled by next run with carry-forward trace.
- Controls:
  - No payout cap increase if previous day reconciliation not fully matched.
  - Mandatory dual-approval for manual adjustments above threshold.
  - Monthly audit export bundle: instructions, ledger postings, reconciliation outcomes, exception dispositions.

### 6) Governance package (step-up auth, access policies, audit exports, incident playbooks)
- Step-up authentication:
  - Required for payout initiation, retry override, reversal, cap changes, and manual adjustments.
  - Token TTL <= 15 minutes; cryptographically bound to action scope and actor.
- Access policies:
  - Financial endpoints: `owner` and `admin` only.
  - Separation of duties: model approvers cannot self-approve production payout policy changes.
  - Service-to-service access via scoped machine identities and rotated credentials.
- Audit exports:
  - Export includes model decision trace, recommendation evidence, milestone verification chain, payout instruction lifecycle, ledger + reconciliation trail.
  - Formats: JSON + CSV manifests with checksum files for integrity verification.
- Incident playbooks:
  - `P1 duplicate payout risk`: freeze dispatch, isolate instruction set, dedupe/reversal workflow.
  - `P1 reconciliation break`: block new high-value payouts, run expedited reclose.
  - `P2 model anomaly`: shift to last approved model, enforce manual recommendation review.
  - Each playbook includes detection signals, owner, response SLA, customer comms template, postmortem checklist.

### 7) Pilot experiment design for KPI validation and GA gate criteria
- Pilot scope:
  - 3-5 design partners across mixed AHJ density profiles.
  - Start with capped payout volume and capped transaction amounts per org/day.
- Experiment design:
  - Predictive KPI cohorting:
    - Treatment: preflight-scored + recommendations-enabled submissions.
    - Control: standard workflow without Stage 3 recommendations.
  - Financial KPI cohorting:
    - All payout instructions through orchestration flow with mandatory reconciliation gate.
- KPI success criteria:
  - >=20% correction-cycle reduction in treatment vs control (statistically stable over pilot window).
  - 100% daily reconciliation match rate for production-settled payouts.
  - 0 unresolved `P1` payout incidents at GA decision point.
- GA gate criteria:
  - Model: no critical segment regression, stable drift profile, confidence policy adherence.
  - Operations: incident playbooks validated in simulation and at least one live drill.
  - Finance: reconciliation controls pass for consecutive close window (for example, 30 days).
  - Compliance/governance: complete audit export for sampled payouts and milestone decisions.

## Task 3

### 1) `GET /projects/{projectId}/preflight-risk` full input contract (derived vs query params + exact examples)

#### Endpoint intent
- Returns risk for one project in the context of one permit type and one AHJ.
- Endpoint is read-only and deterministic for a fixed `(project_id, permit_type, ahj_id, as_of)` input set.

#### Inputs
- Path parameter:
  - `projectId` (required, UUID v4).
- Query parameters:
  - `permit_type` (required, enum).
  - `ahj_id` (required, string, canonical AHJ identifier from Stage 2 AHJ mapping).
  - `as_of` (optional, RFC3339 timestamp; defaults to server `now()`).
  - `include_recommendations` (optional, boolean; default `true`).
  - `include_explainability` (optional, boolean; default `true`).

#### Derived server-side (must NOT be client query params)
- `organization_id`: from auth context / tenant scope.
- `requester_role`: from RBAC token claims.
- `project_profile`: derived from persisted project + intake/application data.
- `requirements_version_id`: active version from `ahj_requirements` for `(ahj_id, permit_type, as_of)`.
- `feature_snapshot_ref`: generated by intelligence service from point-in-time feature store.
- `model_version` + `calibration_version`: selected by deployment policy at request time.

#### Request examples
- Minimal required request:
```http
GET /projects/7a6dc13a-34a6-4fce-9f01-8d97f36d3d35/preflight-risk?permit_type=commercial_ti&ahj_id=ca.san_jose.building HTTP/1.1
Authorization: Bearer <token>
X-Trace-Id: trc_01HRW4Q8KPV6W3M1P0H4N5V2N7
```

- Point-in-time request without recommendations:
```http
GET /projects/7a6dc13a-34a6-4fce-9f01-8d97f36d3d35/preflight-risk?permit_type=rooftop_solar&ahj_id=ca.san_diego.dsd&as_of=2026-03-03T10:30:00Z&include_recommendations=false&include_explainability=true HTTP/1.1
Authorization: Bearer <token>
X-Trace-Id: trc_01HRW4Q8KPV6W3M1P0H4N5V2N8
```

### 2) Query param requirements and validation rules

#### `permit_type`
- Required: yes.
- Type: string enum.
- Allowed values (MVP alignment): `commercial_ti`, `rooftop_solar`, `electrical_service_upgrade`.
- Validation failures:
  - Missing -> `400 invalid_request` (`permit_type is required`).
  - Unknown enum -> `422 validation_error` (`unsupported permit_type`).

#### `ahj_id`
- Required: yes.
- Type: string.
- Format: lowercase dotted identifier, regex `^[a-z0-9]+(\.[a-z0-9_]+)+$`.
- Must exist in AHJ registry and be active for org region policy.
- Validation failures:
  - Missing -> `400 invalid_request` (`ahj_id is required`).
  - Bad format -> `422 validation_error`.
  - Not found/inactive -> `404 not_found` or `422 validation_error` (policy blocked).

#### `as_of`
- Required: no.
- Type: RFC3339 timestamp.
- Defaults to current server time.
- Bounds:
  - Must be >= project creation timestamp.
  - Must be <= server now + 5 minutes clock-skew allowance.
- Validation failures:
  - Bad timestamp -> `422 validation_error`.
  - Out of bounds -> `422 validation_error`.

#### `include_recommendations`, `include_explainability`
- Required: no.
- Type: boolean.
- Defaults: both `true`.
- Validation failures:
  - Non-boolean values -> `422 validation_error`.

### 3) Event alignment: risk/recommendation and milestone/payout to shared envelope/version policy

#### Shared envelope policy (locked)
- All Stage 3 domain events MUST include:
  - `event_id` (UUID)
  - `event_type` (string)
  - `event_version` (integer, starts at `1`)
  - `organization_id` (UUID)
  - `aggregate_type` (string)
  - `aggregate_id` (UUID/string)
  - `occurred_at` (RFC3339 timestamp)
  - `produced_by` (service identity string)
  - `idempotency_key` (string, unique within `(organization_id, idempotency_key)`)
  - `trace_id` (string)
  - `payload` (JSON object)
- Version policy:
  - `event_version` increments only for breaking payload changes.
  - Additive optional fields allowed within same version.
  - Event registry enforces `(event_type, event_version)` schema uniqueness.

#### Stage 3 event contracts (v1)
- `permit.preflight_scored` (`event_version=1`)
  - `aggregate_type=permit`, `aggregate_id=permit_id`
  - Payload:
    - `project_id`, `permit_id`, `permit_type`, `ahj_id`
    - `risk_score`, `risk_band`, `confidence_score`
    - `model_version`, `calibration_version`, `feature_snapshot_ref`
    - `scored_at`
- `permit.recommendations_generated` (`event_version=1`)
  - `aggregate_type=permit`, `aggregate_id=permit_id`
  - Payload:
    - `project_id`, `permit_id`, `permit_type`, `ahj_id`
    - `recommendations` (array of `{recommendation_id, action_text, priority, owner_role, expected_impact}`)
    - `top_risk_factors` (array of `{factor_code, contribution, evidence_ref_ids}`)
    - `generated_at`, `source_score_event_id`
- `milestone.verified` (`event_version=1`)
  - `aggregate_type=milestone`, `aggregate_id=milestone_id`
  - Payload:
    - `milestone_id`, `permit_id`, `project_id`
    - `verification_source`, `verified_at`, `verification_rule_version`
    - `evidence_refs`, `verified_by`
- `payout.instruction_created` (`event_version=1`)
  - `aggregate_type=payout_instruction`, `aggregate_id=instruction_id`
  - Payload:
    - `instruction_id`, `milestone_id`, `permit_id`, `project_id`
    - `amount`, `currency`, `beneficiary_id`
    - `provider`, `instruction_status`, `created_at`
- `payout.instruction_state_changed` (`event_version=1`) (explicitly added for lifecycle traceability)
  - `aggregate_type=payout_instruction`, `aggregate_id=instruction_id`
  - Payload:
    - `instruction_id`, `previous_status`, `new_status`
    - `provider_ref`, `reason_code`, `changed_at`

### 4) End-to-end contract test cases for preflight and payout flows

#### Preflight flow contract tests
1. Happy path preflight score generation.
   - Given valid `projectId`, `permit_type`, `ahj_id`
   - When `GET /projects/{projectId}/preflight-risk`
   - Then response includes `risk_score`, `risk_band`, `confidence_score`, `model_version`
   - And outbox contains `permit.preflight_scored v1` with full shared envelope fields.
2. Recommendations included path.
   - Given `include_recommendations=true`
   - Then response includes `recommended_actions`
   - And `permit.recommendations_generated v1` is emitted referencing source score event.
3. Query validation failures.
   - Missing `permit_type` -> `400`
   - Unsupported `permit_type` -> `422`
   - Invalid `ahj_id` format -> `422`
   - Invalid `as_of` format -> `422`.
4. Determinism test.
   - Same `(projectId, permit_type, ahj_id, as_of)` repeated call
   - Returns identical `risk_score` + `model_version`
   - Emits no duplicate events when idempotency key replays.
5. Authorization/tenant isolation.
   - Caller from different org cannot read project preflight (`404`/`403` policy).
   - Assert no event emission on unauthorized request.

#### Payout flow contract tests
1. Verified milestone -> instruction created.
   - Given milestone state `payout_eligible`
   - When `POST /milestones/{milestoneId}/financial-actions` with idempotency key
   - Then `201` with instruction record and `payout.instruction_created v1` emitted.
2. Idempotent replay on financial action.
   - Same `idempotency_key` retried
   - Returns same instruction ID
   - No duplicate `payout.instruction_created` rows/events.
3. Invalid milestone state handling.
   - Milestone not in `payout_eligible`
   - Returns `409 conflict`
   - Emits no payout creation event.
4. Provider async status transition contract.
   - Simulate provider webhook/poll update `submitted -> settled`
   - Assert `payout.instruction_state_changed v1` emitted with shared envelope and provider refs.
5. Reconciliation linkage.
   - Settled instruction appears in next reconciliation run
   - `GET /financial/reconciliation-runs/{runId}` includes matched entry by `instruction_id` + provider ref.
6. Envelope schema compliance.
   - Validate all Stage 3 event payloads against `(event_type, event_version=1)` schemas
   - Fail test if any required shared envelope field missing.
