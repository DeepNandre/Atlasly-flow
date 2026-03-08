# Stage 2: Parity (Intake, Autofill, Sync)

## Title
Stage 2: Incumbent Parity for Intake, Form Autofill, and City Sync

## Goal
Deliver end-to-end permit orchestration features that match baseline market expectations for research, application generation, and status tracking.

## Scope (In)
- Project intake wizard with normalized permit application schema.
- AHJ mapping and requirements lookup integration (Shovels bootstrap).
- Smart form autofill from project/application data to municipal PDFs.
- City Sync status ingestion from API connectors first, with fallback runners where needed.
- Unified multi-project portfolio status views.

## Out of Scope
- Reviewer-specific predictive recommendations.
- CAD/BIM plugin workflows.
- Financial transfer/payout orchestration.

## Dependencies
- Stage 1B routing feedback loop live and stable.
- Stage 0.5 integration framework and observability complete.
- Credential and policy setup for each connector source.

## Data model changes

### Schema changes
- New tables: `intake_sessions`, `permit_applications`, `application_field_mappings`, `ahj_requirements`, `connector_credentials`, `permit_status_events`, `portal_sync_runs`, `status_source_provenance`.
- Standardized status enum in `permits.status`: `submitted`, `in_review`, `corrections_required`, `approved`, `issued`, `expired`.
- Indexes:
  - `(project_id, current_step)` on `intake_sessions`.
  - `(permit_id, observed_at)` on `permit_status_events`.
  - `(connector, organization_id, run_started_at)` on `portal_sync_runs`.

## APIs / interfaces

### REST endpoints
- `POST /intake-sessions`: initialize guided intake.
- `PATCH /intake-sessions/{sessionId}`: update intake answers.
- `POST /permits/{permitId}/applications/generate`: produce fill-ready application payload.
- `POST /connectors/{ahj}/poll`: trigger status sync run.
- `GET /permits/{permitId}/status-timeline`: read normalized status history.
- `GET /api/permit-ops?limit={n}`: connector health, transition review queue, and drift alerts for operator workflows.
- `POST /api/permit-ops/resolve-transition`: resolve or dismiss transition review queue items.
- `POST /api/permit-ops/resolve-drift`: resolve or dismiss drift alert queue items.
- `POST /api/stage2/resolve-ahj`: resolve AHJ metadata from address via Shovels integration.
- `GET /api/stage2/connector-credentials`: list configured connector credential refs for org.
- `POST /api/stage2/connector-credentials/rotate`: rotate connector credential reference.
- `POST /api/stage2/poll-live`: run live connector poll path using credential vault + env secret.

### Event contracts
- Producer: intake service -> `intake.completed` with `session_id`, `project_id`, `permit_type`, `ahj_id`.
- Producer: form service -> `permit.application_generated` with `permit_id`, `form_template_id`, `generated_at`.
- Producer: connector runner -> `permit.status_observed` with `permit_id`, `raw_status`, `normalized_status`, `source`, `confidence`, `observed_at`.
- Producer: permit service -> `permit.status_changed` with `permit_id`, `old_status`, `new_status`, `source_event_id`.

### Security constraints
- Connector credentials encrypted and scoped per organization.
- Status updates require provenance and traceability to source event.
- Intake and application endpoints honor role constraints (`owner`, `admin`, `pm`).

## Operational requirements
- Connector scheduler with retries, rate-limit handling, and drift detection.
- Source-specific parsers versioned and testable.
- Human override path for disputed status transitions.

## Acceptance criteria
- KPI: >= 95% of connector-observed statuses map cleanly to normalized enum.
- KPI: >= 70% reduction in manual data entry time for targeted permit types.
- Exit criteria: at least two API-native connector paths and one fallback path operate in production.
- Exit criteria: status timeline remains auditable with source provenance for every transition.

## Risks and mitigations
- Risk: portal DOM/API changes break sync.
  - Mitigation: contract tests, parser version pinning, and rapid rollback path.
- Risk: incorrect status normalization.
  - Mitigation: confidence thresholds with manual review for low-confidence mappings.
- Risk: municipal form variance explosion.
  - Mitigation: canonical field library + per-AHJ mapping templates.

## Milestones (Week-by-week)
- Week 1: intake schema and wizard APIs.
- Week 2: AHJ requirements ingestion and permit application model.
- Week 3: PDF autofill mapping engine and validation.
- Week 4: first API-native connector and status normalization.
- Week 5: second connector + fallback runner.
- Week 6: portfolio views, QA hardening, production rollout.
