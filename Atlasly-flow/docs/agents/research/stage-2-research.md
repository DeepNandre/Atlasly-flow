# Stage 2 Research

Status: In Progress
Owner: Stage 2 Agent
Last Updated: 2026-03-02

## 1. Stage objective recap
- Ship incumbent-parity permit intake, form generation/autofill, and municipal status sync workflows with auditable provenance.
- Standardize intake and status data so AHJ variability is absorbed by mapping layers, not by core business logic.
- Deliver API-first connector coverage (minimum two API-native connectors + one fallback path) with operational controls.
- Achieve Stage 2 KPIs: at least 95% clean status normalization and at least 70% reduction in manual form-entry effort for targeted permit types.

## 2. Deep research findings

### Architecture
- Split Stage 2 into five bounded services:
  - `intake-service`: session orchestration and normalized application capture.
  - `requirements-service`: AHJ requirements ingestion, versioning, and lookup.
  - `form-service`: field library, template mapping, autofill payload generation, validation.
  - `connector-service`: API/fallback source adapters, polling/scheduling, raw observation capture.
  - `permit-status-service`: normalization engine, transition guards, current-status projection.
- Keep normalized canonical records (`permit_applications`, normalized status enum) separate from source records (`permit_status_events`, `status_source_provenance`) to preserve auditability and reprocessing.
- Model requirements and mappings as versioned artifacts:
  - AHJ requirements snapshots keyed by `ahj_id`, `permit_type`, `version`.
  - Field mappings keyed by `form_template_id`, `mapping_version`, `ahj_id`.
- Introduce a deterministic normalization pipeline:
  - Raw status observed -> parser output -> normalization rule match -> confidence score -> transition guard -> optional manual review queue.
- Use event-driven coupling between services (`intake.completed`, `permit.application_generated`, `permit.status_observed`, `permit.status_changed`) with idempotent consumers.

### Tooling
- Intake wizard:
  - Schema-driven step engine (JSON schema or equivalent) so new permit types/AHJs can be introduced through configuration.
  - Partial-save and resume support tied to `intake_sessions.current_step`.
- Requirements ingestion:
  - Bootstrap via Shovels feed for AHJ basics, then apply per-AHJ enrichment adapters.
  - Content hash dedupe to avoid duplicate requirements revisions.
- PDF autofill:
  - Canonical field library (`owner_name`, `project_address`, etc.) mapped to PDF AcroForm/XFA field IDs per template.
  - Validation stack with required fields, type/format checks, and cross-field constraints before file generation.
- Connectors:
  - API-native connector SDK with common interface (`authenticate`, `discover`, `poll`, `parse`, `checkpoint`).
  - Fallback runner framework with parser version pinning and synthetic monitoring.
- Observability:
  - Trace IDs propagated from poll runs to status events and final status transitions.
  - Dashboard slices by connector, AHJ, parser version, mapping version, and confidence bucket.

### Operations
- Polling strategy:
  - Adaptive cadence by status age (new submissions poll more often, stale permits less often).
  - Backoff and retry by error class (auth, rate-limit, transient, parser failure).
- Run management:
  - `portal_sync_runs` stores run lifecycle, checkpoints, source revision, and replay cursor.
  - Failed runs route into retry queue with bounded attempts and escalation path.
- Human-in-the-loop:
  - Low-confidence status mappings and invalid transition attempts are held for review, not auto-applied.
  - Manual override requires reason + actor and emits `permit.status_changed` with explicit override provenance.
- Data hygiene:
  - Nightly reconciliation jobs compare current permit status projection against latest observed source events.
  - Drift detection alerts when mapping confidence or clean-map ratio drops below thresholds.

### Risks
- AHJ status semantics mismatch normalized enum.
  - Mitigation: source-specific mapping dictionaries, confidence thresholds, and review queue for uncertain mappings.
- Form variance growth across municipalities and permit types.
  - Mitigation: canonical field dictionary and reusable mapping primitives with template inheritance.
- API credential expiration and permission drift.
  - Mitigation: connector credential health checks, proactive rotation reminders, connector-level auth failure alerts.
- Fallback parser breakage due to portal UI/API changes.
  - Mitigation: parser version pinning, contract tests, canary runs, fast rollback to previous parser.

## 3. Recommended implementation approach
1. Stand up Stage 2 data contracts and schema first.
   - Create all Stage 2 tables and indexes.
   - Add normalized status enum and transition policy guardrails.
2. Implement intake foundation.
   - Build `POST /intake-sessions` and `PATCH /intake-sessions/{sessionId}` with step-state persistence and validation.
   - Emit `intake.completed` when mandatory question set is satisfied.
3. Implement AHJ requirements ingestion.
   - Add ingestion pipeline for Shovels bootstrap + per-source enrichers.
   - Expose read path to intake/form services with version-aware lookups.
4. Build permit application model and generation flow.
   - Convert intake + project data into canonical `permit_applications`.
   - Add `POST /permits/{permitId}/applications/generate` and emit `permit.application_generated`.
5. Deliver PDF autofill engine.
   - Implement canonical field library and template mapping registry (`application_field_mappings`).
   - Add validation gates and generated output QA snapshots.
6. Deliver first API-native connector path.
   - Implement connector SDK baseline and first adapter (e.g., Accela pattern).
   - Emit `permit.status_observed` and apply normalized transitions with provenance.
7. Deliver second API-native connector and one fallback runner.
   - Add second adapter (e.g., OpenGov/Cloudpermit pattern).
   - Add fallback runner path with parser versioning and checkpointed sync runs.
8. Ship portfolio status views and reconciliation.
   - Build timeline endpoint and current-status materialization.
   - Add reconciliation/drift jobs and operations dashboards.

## 4. Required APIs/data/contracts and schema guidance

### API contract guidance
- `POST /intake-sessions`
  - Inputs: `project_id`, `permit_type`, optional seed answers.
  - Outputs: `session_id`, `current_step`, step schema, completion progress.
- `PATCH /intake-sessions/{sessionId}`
  - Supports partial answer patches with optimistic concurrency (`version`/`updated_at` precondition).
  - Returns validation issues per field and next-step instructions.
- `POST /permits/{permitId}/applications/generate`
  - Produces canonical application payload + form mapping status per target template.
- `POST /connectors/{ahj}/poll`
  - Triggers scoped sync run with run id; supports dry-run and force flags for operations.
- `GET /permits/{permitId}/status-timeline`
  - Returns normalized timeline with source provenance references.

### Event contract guidance
- `intake.completed`
  - `session_id`, `project_id`, `permit_type`, `ahj_id`, `completed_at`, `intake_version`.
- `permit.application_generated`
  - `permit_id`, `application_id`, `form_template_id`, `mapping_version`, `generated_at`.
- `permit.status_observed`
  - `permit_id`, `raw_status`, `normalized_status_candidate`, `source`, `confidence`, `observed_at`, `sync_run_id`, `parser_version`.
- `permit.status_changed`
  - `permit_id`, `old_status`, `new_status`, `source_event_id`, `changed_by`, `change_reason`.

### Schema/index guidance
- `intake_sessions`
  - Fields: `id`, `organization_id`, `project_id`, `permit_type`, `current_step`, `answers_json`, `status`, `version`, timestamps.
  - Index: `(project_id, current_step)`.
- `permit_applications`
  - Fields: `id`, `permit_id`, `organization_id`, `application_payload_json`, `intake_session_id`, `version`, timestamps.
- `application_field_mappings`
  - Fields: `id`, `ahj_id`, `permit_type`, `form_template_id`, `mapping_version`, `canonical_field`, `target_field_id`, `transform_rule`, `required`.
  - Index: `(form_template_id, mapping_version, canonical_field)`.
- `ahj_requirements`
  - Fields: `id`, `ahj_id`, `permit_type`, `requirements_json`, `source`, `source_revision`, `effective_at`, `expires_at`.
  - Index: `(ahj_id, permit_type, effective_at DESC)`.
- `connector_credentials`
  - Fields: `id`, `organization_id`, `connector`, `credential_ref`, `scopes`, `status`, `last_validated_at`.
  - Index: `(organization_id, connector)`.
- `portal_sync_runs`
  - Fields: `id`, `organization_id`, `connector`, `ahj_id`, `run_started_at`, `run_finished_at`, `status`, `checkpoint`, `error_summary`.
  - Index: `(connector, organization_id, run_started_at)`.
- `permit_status_events`
  - Fields: `id`, `permit_id`, `organization_id`, `raw_status`, `normalized_status`, `confidence`, `observed_at`, `source`, `sync_run_id`, `parser_version`.
  - Index: `(permit_id, observed_at)`.
- `status_source_provenance`
  - Fields: `id`, `status_event_id`, `source_type`, `source_ref`, `source_payload_hash`, `ingested_at`.

## 5. Build-vs-buy decisions and tradeoffs
- AHJ requirements intelligence:
  - Buy bootstrap signal via Shovels for speed-to-coverage.
  - Build normalization/versioning layer in-house for quality control and long-term moat.
- PDF processing/autofill:
  - Buy mature PDF parser/filler primitives where possible.
  - Build canonical field model, mappings, and validation logic (domain-specific differentiator).
- Connector framework:
  - Build connector SDK/orchestrator internally (core reliability path and reusable abstraction).
  - Buy/support vendor SDKs only for auth transport or protocol helpers.
- Fallback runners:
  - Build minimal, policy-compliant fallback runner framework with strict observability and rollback.
- Status normalization:
  - Build mapping/rules/confidence pipeline in-house because this is central to timeline correctness and Stage 3 data moat quality.

## 6. Validation and test plan
- Intake tests:
  - Step validation, resume behavior, role authorization, and completion event emission.
- Requirements ingestion tests:
  - Source ingest idempotency, version supersession rules, and lookup correctness by effective date.
- Autofill tests:
  - Mapping completeness checks for targeted templates, field transform unit tests, generated PDF verification snapshots.
- Connector tests:
  - Contract tests for each adapter, checkpoint replay tests, rate-limit/auth failure handling, parser regression fixtures.
- Status normalization tests:
  - Raw-to-normalized mapping coverage, invalid transition rejection, confidence gating, and manual override audit checks.
- End-to-end parity tests:
  - Intake -> application generation -> connector observation -> normalized timeline for representative AHJs/permit types.
- KPI validation:
  - Clean-map ratio >= 95% and measured manual entry-time reduction >= 70% on target permit cohorts.

## 7. Execution checklist
1. Confirm Stage 1B and Stage 0.5 dependency gates are green in production-like environment.
2. Ship Stage 2 schema migration pack and enum/index updates.
3. Implement intake session APIs + validation engine + completion event.
4. Implement AHJ requirements ingest pipeline and retrieval API.
5. Implement canonical permit application model + generation endpoint.
6. Implement mapping registry and PDF autofill validation/generation pipeline.
7. Ship connector SDK baseline and first API-native adapter.
8. Add status normalization engine, transition guards, and provenance persistence.
9. Ship second API-native adapter and fallback runner path.
10. Implement status timeline and multi-project portfolio projections.
11. Add reconciliation jobs, drift alerts, parser canary checks, and runbooks.
12. Execute full Stage 2 test matrix and KPI acceptance checks.
13. Roll out in phases by connector/AHJ cohort with rollback gates.

## 8. Open risks and unknowns with mitigation plan
- Unknown: exact API capability/coverage differences across target AHJs.
  - Mitigation: connector capability matrix before implementation and explicit fallback criteria per AHJ.
- Unknown: initial targeted permit-type set for 70% data-entry reduction KPI.
  - Mitigation: lock MVP permit cohorts early and instrument baseline/manual timings before rollout.
- Risk: mapping debt accumulates faster than team can maintain.
  - Mitigation: enforce template lifecycle ownership, mapping linting, and stale-mapping alerts.
- Risk: provenance payload retention increases storage costs significantly.
  - Mitigation: tiered retention (hot vs cold), payload hashing in hot path, raw payload archival policy.
- Risk: status flapping from noisy sources impacts user trust.
  - Mitigation: debounce rules, transition confidence thresholds, and operator-reviewed exception queue.

## 9. Resource list
- Internal specs:
  - `docs/agents/shared-context.md`
  - `docs/agents/stage-2-agent-prompt.md`
  - `docs/stages/stage-2-parity-intake-autofill-sync.md`
  - `docs/master-prd.md`
  - `docs/stages/README.md`
- Official/high-signal implementation references to consult during build:
  - Accela Civic Platform API docs.
  - OpenGov Permitting & Licensing API docs.
  - Cloudpermit integration/API documentation.
  - PostgreSQL docs for indexing, JSONB patterns, and transactional integrity.
  - PDF form standards and library docs for AcroForm/XFA handling.

## Task 2

### MVP scope lock (permit types + connectors)
- MVP permit types (Stage 2):
  - `commercial_ti` (commercial tenant improvement)
  - `rooftop_solar` (C&I rooftop PV)
  - `electrical_service_upgrade` (panel/service upgrade)
- API-native connectors:
  - `accela_api` (Wave 1)
  - `opengov_api` (Wave 2)
- Fallback connector:
  - `cloudpermit_portal_runner` (Wave 3 fallback path for non-API/blocked API conditions)

### 1) Canonical intake and permit application schema (final fields + validation)

#### Intake schema (`intake_sessions.answers_json`)
- `project`
  - `project_name`: string, required, 3-120 chars.
  - `project_address_line1`: string, required.
  - `project_address_line2`: string, optional.
  - `city`: string, required.
  - `state`: enum (US states), required.
  - `postal_code`: string, required, regex `^\d{5}(-\d{4})?$`.
  - `parcel_apn`: string, optional, 1-40 chars.
  - `occupancy_type`: enum (`business`, `mercantile`, `residential_mixed`, `industrial`, `other`), required.
  - `construction_type`: enum (`ia`,`ib`,`iia`,`iib`,`iiia`,`iiib`,`iva`,`ivb`,`va`,`vb`,`unknown`), required.
- `permit_request`
  - `permit_type`: enum (`commercial_ti`, `rooftop_solar`, `electrical_service_upgrade`), required.
  - `scope_summary`: string, required, 20-2000 chars.
  - `valuation_usd`: number, required, min `0`, max `250000000`.
  - `estimated_start_date`: date, required, must be >= intake date.
  - `estimated_duration_days`: integer, required, min `1`, max `1095`.
- `parties`
  - `owner_legal_name`: string, required.
  - `owner_entity_type`: enum (`individual`,`llc`,`corp`,`partnership`,`other`), required.
  - `owner_mailing_address`: object, required.
  - `applicant_name`: string, required.
  - `applicant_email`: email, required.
  - `applicant_phone`: E.164-ish string, required.
  - `contractor_company_name`: string, required.
  - `contractor_license_number`: string, required for `rooftop_solar` and `electrical_service_upgrade`.
  - `contractor_license_state`: enum (US states), conditionally required with license number.
- `site_details`
  - `building_area_sqft`: number, required for `commercial_ti`, min `1`.
  - `stories_affected`: integer, optional, min `1`, max `200`.
  - `historic_district_flag`: boolean, required.
  - `sprinklered_flag`: boolean, required for `commercial_ti`.
- `trade_details`
  - `electrical_panel_amps_existing`: integer, required for `electrical_service_upgrade`.
  - `electrical_panel_amps_proposed`: integer, required for `electrical_service_upgrade`, must be >= existing.
  - `solar_kw_dc`: number, required for `rooftop_solar`, min `0.1`, max `5000`.
  - `solar_inverter_count`: integer, required for `rooftop_solar`, min `1`.
  - `battery_storage_kwh`: number, optional, min `0`.
- `attachments_manifest`
  - `required_docs`: array of enums (`site_plan`,`floor_plan`,`single_line_diagram`,`structural_calcs`,`spec_sheets`,`owner_authorization`,`contractor_license_proof`).
  - Validation: all AHJ-required docs for selected `permit_type` must be present before completion.

#### Permit application schema (`permit_applications.application_payload_json`)
- `application_id`: UUID, immutable.
- `organization_id`, `project_id`, `permit_id`, `intake_session_id`: UUID refs, required.
- `ahj_id`: string, required.
- `permit_type`: mirrored enum, required.
- `canonical_fields`: flattened key-value map from intake + derived fields.
- `computed_fields`
  - `jurisdiction_code`: derived from AHJ mapper.
  - `valuation_bucket`: derived enum (`lt_50k`,`50k_250k`,`250k_1m`,`gt_1m`).
  - `risk_flags`: array (`historic`,`high_load_upgrade`,`incomplete_docs`,`license_mismatch`).
- `validation_summary`
  - `status`: enum (`pass`,`warn`,`fail`).
  - `errors`: array `{field, rule_id, message}`.
  - `warnings`: array `{field, rule_id, message}`.
- `generation_context`
  - `requirements_version_id`, `mapping_bundle_version`, `generator_version`, `generated_at`.

#### Cross-object validation rules
- Intake cannot emit `intake.completed` unless:
  - all required-by-permit-type fields are present,
  - all required AHJ docs are attached in manifest,
  - applicant/owner identity fields pass format checks,
  - no `fail`-level rule remains in `validation_summary`.
- Application generation hard-fails on:
  - missing mapping for required canonical field,
  - stale requirements version (`effective_at` older than allowed policy window),
  - connector/AHJ mismatch for targeted submission channel.

### 2) AHJ requirements ingestion/versioning design with source provenance
- Ingestion sources:
  - `shovels_bootstrap` for initial AHJ + permit requirement baseline.
  - `connector_discovery` for API-exposed requirement metadata.
  - `ops_curated` manual ops updates for emergency corrections.
- Version model:
  - Table `ahj_requirements` gains `version_number` (int), `is_active` (bool), `supersedes_id` (nullable), `content_hash` (sha256).
  - Unique: `(ahj_id, permit_type, version_number)`.
  - Active pointer: one active version per `(ahj_id, permit_type)`.
- Provenance model:
  - Each requirement version links to `status_source_provenance`-style record:
    - `source_type` (`api`,`portal`,`vendor`,`manual`)
    - `source_ref` (endpoint URL, portal page key, or ticket id)
    - `source_payload_hash`
    - `ingested_by` (`system`/actor id)
    - `ingested_at`
- Ingestion workflow:
  1. Pull source payload.
  2. Normalize into canonical requirement shape.
  3. Compute hash and dedupe.
  4. Run semantic diff against active version.
  5. If changed, write new version and mark previous inactive.
  6. Emit `ahj.requirements_versioned`.
- Rollback policy:
  - Allow one-click promote of previous version; emit `ahj.requirements_reverted`.

### 3) Form mapping/autofill spec (canonical dictionary + template lifecycle)

#### Canonical field dictionary (MVP keys)
- Identity and addresses:
  - `owner_legal_name`, `owner_mailing_street`, `owner_mailing_city`, `owner_mailing_state`, `owner_mailing_zip`
  - `applicant_name`, `applicant_email`, `applicant_phone`
  - `contractor_company_name`, `contractor_license_number`, `contractor_license_state`
- Project core:
  - `project_name`, `project_site_street`, `project_site_city`, `project_site_state`, `project_site_zip`, `parcel_apn`
  - `permit_type`, `scope_summary`, `valuation_usd`
- Technical/trade:
  - `building_area_sqft`, `stories_affected`, `sprinklered_flag`
  - `solar_kw_dc`, `solar_inverter_count`, `battery_storage_kwh`
  - `electrical_panel_amps_existing`, `electrical_panel_amps_proposed`
- AHJ/system:
  - `ahj_name`, `jurisdiction_code`, `application_date`, `application_reference`

#### Mapping model
- `application_field_mappings` includes:
  - `mapping_bundle_id`, `mapping_version`, `form_template_id`, `canonical_field`, `target_field_id`
  - `target_field_type` (`text`,`checkbox`,`radio`,`date`,`number`,`signature_placeholder`)
  - `transform_rule` (dsl/json expression)
  - `required`, `default_value`, `validation_regex`, `effective_at`, `retired_at`
- Mapping completeness gate:
  - For each `(form_template_id, permit_type)` required canonical fields must be 100% mapped.

#### Template mapping lifecycle
1. `draft`: created from form field extraction + canonical suggestions.
2. `qa`: validation test pack run against fixture applications.
3. `approved`: ops signoff and production promotion.
4. `active`: used by generation service.
5. `retired`: replaced by newer mapping version.
- Lifecycle controls:
  - Only `admin`/`pm` with mapping permission can promote.
  - Every promotion stores changelog and diff summary.
  - Automatic rollback to last `active` on generation error-rate threshold breach.

### 4) Connector capability matrix and rollout plan

| Connector | Type | MVP AHJ cohort | Auth | Create/submit support | Status pull support | Webhook support | Confidence target |
|---|---|---|---|---|---|---|---|
| `accela_api` | API-native | Top Accela jurisdictions in CA/TX/FL pilot list | OAuth2/API key (AHJ dependent) | Phase 2 (status first, submit second) | Yes (primary) | Limited/varies | >=0.97 |
| `opengov_api` | API-native | OpenGov jurisdictions in CA/AZ/CO pilot list | OAuth2/service account | Phase 2 (status first, submit second) | Yes (primary) | Varies by tenant | >=0.96 |
| `cloudpermit_portal_runner` | Fallback runner | Cloudpermit + non-API municipalities | Vaulted creds + MFA assist | No create in MVP | Yes (scrape/automation) | No | >=0.90 |

- Rollout waves:
  - Wave 1 (Week 4): `accela_api` status polling GA for MVP permit types.
  - Wave 2 (Week 5): `opengov_api` status polling GA + parity metrics.
  - Wave 3 (Week 5-6): `cloudpermit_portal_runner` limited rollout with strict ops monitoring.
- Promotion criteria per connector:
  - clean normalization ratio >= 95% for connector cohort,
  - < 2% failed poll runs over trailing 7 days,
  - provenance completeness 100% for status events.

### 5) Status normalization rulebook and invalid-transition handling

#### Raw-to-normalized rulebook (connector-agnostic baseline)
- `submitted`: raw contains (`submitted`,`application received`,`intake complete`,`pending intake review`).
- `in_review`: raw contains (`under review`,`plan review`,`department review`,`routing`).
- `corrections_required`: raw contains (`revisions required`,`resubmit`,`denied with corrections`,`hold for corrections`).
- `approved`: raw contains (`approved`,`approved pending issuance`,`ready to issue`).
- `issued`: raw contains (`issued`,`permit issued`,`finalized/issued`).
- `expired`: raw contains (`expired`,`void`,`closed expired`).

#### Priority and confidence
- Matching order:
  1. connector-specific exact mapping table,
  2. AHJ-specific regex map,
  3. global lexical fallback.
- Confidence scoring:
  - exact table match: `0.99`
  - regex map match: `0.95`
  - lexical fallback: `0.75`
  - conflicting signals in same payload: minus `0.20`.
- Auto-apply threshold: `>=0.90`; else queue for manual review.

#### Invalid-transition handling
- Allowed transitions:
  - `submitted -> in_review|corrections_required|approved|issued`
  - `in_review -> corrections_required|approved|issued`
  - `corrections_required -> submitted|in_review|approved`
  - `approved -> issued|expired`
  - `issued -> expired` (time-bound jurisdictional cases only)
  - `expired ->` terminal (no auto-transition)
- Invalid transition flow:
  1. Persist observed event as `rejected_transition`.
  2. Do not mutate `permits.status`.
  3. Emit `permit.status_transition_rejected`.
  4. Route to ops review queue with source payload and prior state context.

### 6) Reconciliation/drift detection design for status timelines
- Reconciliation job cadence:
  - Hourly for active permits (`submitted`,`in_review`,`corrections_required`).
  - Daily for `approved`/`issued`.
- Reconciliation algorithm:
  1. Load latest connector observation per permit.
  2. Re-run normalization with current ruleset.
  3. Compare with current projected `permits.status`.
  4. If mismatch:
     - classify as `mapping_drift` (rules changed) or `source_drift` (connector payload changed),
     - create reconciliation record with diff and severity.
  5. Auto-heal only if confidence >= `0.95` and transition valid.
  6. Otherwise raise manual task.
- Drift KPIs and alerts:
  - `status_drift_rate` threshold: alert at `>3%` rolling 24h.
  - `unknown_raw_status_rate` threshold: alert at `>2%` per connector/day.
  - `timeline_gap_rate` (missing provenance events) threshold: alert at `>0.5%`.
- Audit guarantees:
  - every reconciliation decision stores `ruleset_version`, `actor` (`system`/user), and `decision_reason`.

### 7) Implementation backlog with explicit connector-by-connector sequencing

#### Foundation (pre-connector)
1. Finalize MVP permit-type enum and intake validation schemas.
2. Apply DB migrations for Stage 2 tables + constraints + indexes.
3. Build requirements versioning/provenance write path.
4. Build canonical field dictionary and mapping lifecycle states.
5. Build normalization engine core + transition guard framework.

#### Connector sequence
6. `accela_api` adapter
   - Implement auth client + polling endpoint wrapper.
   - Build raw-status parser and connector-specific mapping table.
   - Run fixture contract suite and canary in 2 AHJs.
   - Exit gate: >=95% clean mapping and <=2% run failures.
7. `opengov_api` adapter
   - Implement auth client + polling wrapper.
   - Build mapping table and AHJ-specific overrides.
   - Run parallel canary in 2 AHJs with reconciliation enabled.
   - Exit gate: same as Accela + no unresolved high-severity drift for 72h.
8. `cloudpermit_portal_runner` fallback
   - Implement secure runner with credential vault integration.
   - Add parser versioning and DOM contract tests.
   - Restrict to status polling (no submission) for MVP.
   - Exit gate: provenance completeness 100%, manual review queue SLA <24h.

#### Post-connector hardening
9. Ship cross-connector portfolio timeline views.
10. Enable hourly reconciliation + drift alerting in production.
11. Run KPI certification on MVP permit cohorts (`commercial_ti`, `rooftop_solar`, `electrical_service_upgrade`).
12. Prepare Wave-2 expansion backlog (additional AHJs and permit types after Stage 2 exit).
