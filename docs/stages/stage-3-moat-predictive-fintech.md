# Stage 3: Moat (Predictive + Fintech)

## Title
Stage 3: Proprietary AHJ Intelligence and Milestone-Based Payout Orchestration

## Goal
Create durable competitive advantages through predictive AHJ guidance, upstream design checks, and milestone-driven financial workflows.

## Scope (In)
- Predictive AHJ feedback loop using historical review outcomes.
- Pre-submit risk scoring and recommendation generation.
- Initial upstream design integration path for code-compliance checks.
- Milestone-based payout orchestration tied to verified permit status events.

## Out of Scope
- Fully autonomous permit submission across all municipalities.
- Guaranteed legal code compliance certification without licensed reviewer pathways.
- Banking-as-a-service products beyond payout orchestration.

## Dependencies
- Stage 2 normalized permit status events stable and trusted.
- Stage 0-2 historical review and extraction feedback data retained at quality.
- Payments provider account architecture and compliance onboarding.

## Data model changes

### Schema changes
- New tables: `ahj_behavior_features`, `preflight_risk_scores`, `recommendation_runs`, `milestones`, `payout_instructions`, `financial_events`, `reconciliation_runs`.
- New fields on `permits`: `risk_score`, `risk_band`, `last_recommendation_at`.
- Indexes:
  - `(ahj_id, permit_type, updated_at)` on `ahj_behavior_features`.
  - `(organization_id, milestone_state, due_at)` on `milestones`.
  - `(organization_id, event_type, occurred_at)` on `financial_events`.

## APIs / interfaces

### REST endpoints
- `GET /projects/{projectId}/preflight-risk`: return permit-specific risk insights.
- `POST /projects/{projectId}/preflight-recommendations`: generate remediation actions.
- `POST /milestones/{milestoneId}/financial-actions`: enqueue payout instruction.
- `GET /financial/reconciliation-runs/{runId}`: retrieve reconciliation outcomes.
- `GET /api/finance-ops?limit={n}`: payout timeline, reconciliation history, and outbox publish-state summary.
- `POST /api/stage3/publish-outbox`: dispatch pending outbox events for downstream accounting sync.
- Provider webhook signatures supported via env-driven enforcement (`ATLASLY_STAGE3_ENFORCE_SIGNATURES`).

### Event contracts
- Producer: intelligence service -> `permit.preflight_scored` with `permit_id`, `risk_score`, `top_risk_factors`, `model_version`.
- Producer: intelligence service -> `permit.recommendations_generated` with `permit_id`, `recommendation_ids`, `generated_at`.
- Producer: milestone service -> `milestone.verified` with `milestone_id`, `permit_id`, `verification_source`, `verified_at`.
- Producer: payout service -> `payout.instruction_created` with `instruction_id`, `milestone_id`, `amount`, `currency`, `beneficiary_id`.

### Security constraints
- Financial endpoints restricted to `owner` and `admin` roles with step-up authentication.
- Ledger writes append-only with reconciliation provenance.
- AI recommendation outputs must be traceable to source features and model version.
- Provider webhook signature controls:
  - `ATLASLY_STAGE3_PROVIDER_WEBHOOK_SECRET`
  - `ATLASLY_STAGE3_ENFORCE_SIGNATURES`

## Operational requirements
- Model monitoring for drift and false-positive risk alerts.
- Financial workflow idempotency, replay safety, and double-entry reconciliation.
- Incident runbooks for payout failure, reversal, and duplicate instruction handling.

## Acceptance criteria
- KPI: at least 20% reduction in correction-cycle frequency for assisted submissions vs control cohort.
- KPI: 100% reconciliation match rate between internal ledger events and payment provider settlement records per daily run.
- Exit criteria: recommendations cite explicit AHJ pattern evidence and are audit-exportable.
- Exit criteria: payout instructions only execute for verified milestones with full traceability.

## Risks and mitigations
- Risk: biased or weak predictive guidance from sparse AHJ history.
  - Mitigation: confidence-banded recommendations and human reviewer gating.
- Risk: financial automation errors.
  - Mitigation: staged release with low transaction caps and mandatory reconciliation gate.
- Risk: legal/compliance ambiguity around payment flows.
  - Mitigation: counsel-reviewed terms and strict provider-supported payout patterns.

## Milestones (Week-by-week)
- Week 1: feature store schema and baseline risk model pipeline.
- Week 2: preflight scoring/recommendation APIs and auditability hooks.
- Week 3: milestone verification and payout instruction domain model.
- Week 4: provider integration and sandbox reconciliation.
- Week 5: pilot rollout with transaction caps and controls.
- Week 6: model/payout reliability tuning and GA decision gate.
