# Stage 0.5: Enterprise Readiness

## Title
Stage 0.5: Enterprise Readiness and Operational Controls

## Goal
Add the operational, observability, integration, and compliance capabilities required for mid-market and enterprise customer onboarding.

## Scope (In)
- Portfolio-level dashboards with permit lifecycle KPIs.
- Integrations framework: outbound webhooks, connector runner, retries, dead-letter handling.
- Admin/support controls: org settings, API credentials, template management.
- Security/compliance controls for SOC2-readiness.

## Out of Scope
- AI extraction logic.
- Full production Procore bi-directional synchronization.
- Fintech transfer execution.

## Dependencies
- Stage 0 completed and stable in production-like environment.
- Centralized logging and metrics backend.
- Secrets manager and key rotation mechanism.

## Data model changes

### Schema changes
- New tables: `webhook_subscriptions`, `webhook_deliveries`, `connector_runs`, `connector_errors`, `dashboard_snapshots`, `api_credentials`, `task_templates`, `security_audit_exports`.
- Indexes:
  - `(organization_id, created_at)` on `connector_runs` and `webhook_deliveries`.
  - `(organization_id, is_active)` on `webhook_subscriptions`.

## APIs / interfaces

### REST endpoints
- `POST /webhooks`: register webhook subscription.
- `GET /webhook-events`: retrieve delivery outcomes.
- `POST /connectors/{name}/sync`: trigger connector sync run.
- `GET /dashboard/portfolio`: aggregate permit and task KPIs.
- `POST /orgs/{orgId}/api-keys`: create scoped API credential.
- `GET /api/portfolio`: control-tower project, permit, and task rollups.
- `GET /api/activity?limit={n}`: cross-stage operations event stream.
- `GET /api/enterprise/overview?limit={n}`: enterprise operations rollup for webhooks/connectors/credentials/templates/exports.
- `GET /api/enterprise/webhook-events`: delivery attempt audit stream for replay controls.
- `GET /api/enterprise/dashboard`: latest Stage 0.5 KPI snapshot.
- `GET /api/enterprise/alerts`: alert thresholds and backlog signals for DLQ/replay queue monitoring.
- `GET /api/enterprise/slo`: rolling 24h SLO snapshot for webhook/connector/API-key governance.
- `GET /api/enterprise/audit-evidence`: build evidence-pack manifest for completed exports.
- `POST /api/enterprise/api-keys/mark-used`: record key last-used metadata.
- `POST /api/enterprise/api-keys/policy-scan`: evaluate/optionally enforce key rotation policy.
- `POST /api/enterprise/*`: operator actions for webhooks, connector lifecycle, API key lifecycle, task templates, audit exports, and dashboard snapshot upserts.

### Event contracts
- Producer: integration service -> `integration.run_started` with `connector`, `organization_id`, `run_id`, `started_at`.
- Producer: integration service -> `integration.run_completed` with `run_id`, `status`, `duration_ms`, `records_synced`.
- Producer: webhook dispatcher -> `webhook.delivery_failed` with `subscription_id`, `event_id`, `attempt`, `error_code`.

### Security constraints
- API keys must be scope-limited and hashed at rest.
- Admin-only access to connector credentials and org settings.
- Audit exports restricted to `owner` and `admin` roles.
- Log redaction for PII and secrets before persistence.

## Operational requirements
- Connector run observability: success rate, latency, error taxonomy.
- Alerting on repeated webhook failures and connector drift.
- Backup and restore runbooks validated quarterly.

## Acceptance criteria
- KPI: webhook delivery success >= 99% over rolling 24h (excluding endpoint 4xx).
- KPI: dashboard refresh completes within 5 minutes for 1,000 active permits.
- Exit criteria: at least one external system can subscribe and receive permit/task event stream.
- Exit criteria: compliance/audit export path is usable by support and security teams.

## Risks and mitigations
- Risk: connector flakiness creates data mistrust.
  - Mitigation: run health scores, replay tooling, and explicit source provenance.
- Risk: insecure API key handling.
  - Mitigation: one-time key display, hashed storage, and forced rotation policy.
- Risk: operational blind spots.
  - Mitigation: SLO dashboards with per-connector error budgets.

## Milestones (Week-by-week)
- Week 1: connector SDK and webhook contract design.
- Week 2: connector runtime + delivery retries + dead-letter queue.
- Week 3: portfolio KPI aggregations and dashboard APIs.
- Week 4: admin/support controls and API credential lifecycle.
- Week 5: compliance controls, runbooks, reliability validation.
