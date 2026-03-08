# Demo Hosting Guide

## Local containerized run
1. Build and start:
   - `bash scripts/run-demo-container.sh`
2. Open:
   - `http://127.0.0.1:8080`

## Required environment for hosted demo
- `ATLASLY_DEPLOYMENT_TIER=demo`
- `ATLASLY_STAGE05_RUNTIME_BACKEND=sqlite`
- `ATLASLY_STAGE05_PERSISTENCE_READY=true`

Optional integrations:
- `ATLASLY_SHOVELS_API_KEY` for live AHJ mapping
- `ATLASLY_STRIPE_SECRET_KEY` for Stage 3 Stripe sandbox submission path
- `ATLASLY_STRIPE_BASE_URL` if using non-default Stripe endpoint

## Smoke validation before sharing link
- `bash scripts/webapp-smoke-test.sh`
- `bash scripts/mvp-gates.sh`

## Demo operator checklist
- Bootstrap workspace
- Run demo scenario once
- Verify role switching (owner/admin/pm/reviewer/subcontractor)
- Verify feedback submit path and telemetry visibility
- Verify reset returns a clean workspace
