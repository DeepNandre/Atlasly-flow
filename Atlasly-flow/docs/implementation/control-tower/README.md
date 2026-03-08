# Control Tower Integration Slices

## Scope
Implements Section 7 of the Atlasly section-by-section execution plan.

## UI slices shipped
- UI-P1: Overview KPI cards, permit status mix, and project grid
- UI-P2: Comment Ops reviewer summary + needs-review queue rendering
- UI-P3: Permit Ops connector health and transition-review queue views
- UI-P4: Finance Ops payout timeline and reconciliation summary views
- UI-P5: Non-blocking error-state banner for runtime/API failures
- UI-P6: Enterprise Ops workspace for webhook/connector/API-key/template/audit controls
- UI-P7: Incident-state banner + SLO snapshot panel with auth-aware error messaging

## Runtime API surface
- Session bootstrap: `POST /api/bootstrap` (returns bearer session token)
- `GET /api/sessions`
- `POST /api/demo/reset`
- `POST /api/feedback`
- `GET /api/telemetry`
- `POST /api/telemetry`
- `GET /api/portfolio`
- `GET /api/activity?limit={n}`
- `GET /api/permit-ops?limit={n}`
- `POST /api/permit-ops/resolve-transition`
- `POST /api/permit-ops/resolve-drift`
- `GET /api/finance-ops?limit={n}`
- `POST /api/stage3/payout`
- `POST /api/stage3/provider-event`
- `POST /api/stage3/reconcile`
- `POST /api/stage3/publish-outbox`
- `GET /api/enterprise/overview?limit={n}`
- `GET /api/enterprise/webhook-events?...`
- `GET /api/enterprise/dashboard`
- `GET /api/enterprise/alerts`
- `GET /api/enterprise/slo`
- `GET /api/enterprise/integrations-readiness`
- `GET /api/enterprise/launch-readiness`
- `GET /api/enterprise/audit-evidence`
- `POST /api/enterprise/webhooks`
- `POST /api/enterprise/webhook-delivery`
- `POST /api/enterprise/webhook-replay`
- `POST /api/enterprise/connector-sync`
- `POST /api/enterprise/connector-error`
- `POST /api/enterprise/connector-complete`
- `POST /api/enterprise/api-keys`
- `POST /api/enterprise/api-keys/mark-used`
- `POST /api/enterprise/api-keys/policy-scan`
- `POST /api/enterprise/api-keys/rotate`
- `POST /api/enterprise/api-keys/revoke`
- `POST /api/enterprise/task-templates`
- `POST /api/enterprise/task-templates/archive`
- `POST /api/enterprise/audit-exports/request`
- `POST /api/enterprise/audit-exports/run`
- `POST /api/enterprise/audit-exports/complete`
- `POST /api/enterprise/dashboard-snapshot`
- `POST /api/stage1a/upload`
- `POST /api/stage1a/process-upload`
- `GET /api/stage1a/quality-report`
- `GET /api/stage1b/routing-audit`
- `POST /api/stage1b/escalation-tick`
- `POST /api/stage2/resolve-ahj`
- `GET /api/stage2/connector-credentials`
- `POST /api/stage2/connector-credentials/rotate`
- `POST /api/stage2/poll-live`

## Auth boundary
- All `/api/*` routes except `/api/health`, `/api/bootstrap`, and `/api/demo/reset` require bearer session auth.
- Route RBAC is enforced for comment ops, permit ops, finance ops, and enterprise controls.

## Contract source
- `contracts/stage0_5/apis/control-tower.v1.openapi.yaml`

## Runbook impact
- Smoke test now validates control-tower endpoints and post-action queue states.
- Browser verification should include:
  1. Comment parse with `needs_review` cases visible
  2. Polling a low-confidence status, resolving transition review, and confirming queue update
  3. Creating payout + reconciliation, then running outbox publish and checking finance timeline
  4. Registering webhook, producing a dead-letter, replaying it, and confirming Enterprise Ops counters
