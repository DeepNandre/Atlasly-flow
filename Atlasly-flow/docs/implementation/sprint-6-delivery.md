# Sprint 6 Delivery (Control Tower Release Hardening)

## Scope delivered
- Added incident banner UX for degraded operational conditions.
- Added auth-aware error UX messages for `401/403/409` API failures.
- Added enterprise SLO snapshot backend (`GET /api/enterprise/slo`) and frontend rendering.
- Added enterprise API key governance actions:
  - `POST /api/enterprise/api-keys/mark-used`
  - `POST /api/enterprise/api-keys/policy-scan`
- Added audit evidence pack endpoint:
  - `GET /api/enterprise/audit-evidence`
- Added integration readiness endpoint and UI panel:
  - `GET /api/enterprise/integrations-readiness`
- Added launch readiness checklist endpoint and UI panel:
  - `GET /api/enterprise/launch-readiness`
- Added provider selection support on Stage 3 payout route:
  - `POST /api/stage3/payout` now accepts `provider` (including `stripe_sandbox`)
- Expanded enterprise SLO payload to include:
  - Stage 2 transition review queue depth
  - Stage 3 payout reconciliation mismatch rate
- Added live validation harness:
  - `bash scripts/run-live-validations.sh`
- Expanded smoke coverage for Stage 1A quality, Stage 1B routing audit/ticks, enterprise SLO, policy scan, and evidence generation.

## UI updates
- Comment Ops: upload+OCR parse controls, quality report panel, routing audit and escalation tick actions.
- Enterprise Ops: SLO summary panel and policy/evidence controls.
- Enterprise Ops: integration readiness panel for live connector/provider launch blockers.
- Enterprise Ops: launch readiness checklist panel with explicit pass/fail gates.
- Global: incident banner shown when SLO incidents are present.

## Validation
- `node --check webapp/app.js`
- `python3 -m unittest discover -s tests/webapp -p 'test_*.py'`
- `bash scripts/webapp-smoke-test.sh`

## Remaining items
- `PAY-001` final validation is still open: execute one successful staging Stripe sandbox run with real credentials.
- `INT-001` live validation is still open: execute one successful live connector poll (Accela or OpenGov) with real credentials.
