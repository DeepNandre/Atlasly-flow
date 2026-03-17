# Atlasly-flow

## Documentation
- Product requirements: [Master PRD](docs/master-prd.md)
- Stage-by-stage execution docs: [Stages Index](docs/stages/README.md)
- Sub-agent research prompts: [Prompt Pack](docs/agents/README.md)
- Strategy and competitive analysis: [Strategy Docs](docs/strategy/README.md)
- Control tower implementation notes: [Control Tower Slices](docs/implementation/control-tower/README.md)
- Productionization execution plan: [6-Week Sprint Plan](docs/implementation/productionization-sprint-plan.md)
- Sprint 1 delivery log: [Sprint 1 Delivery](docs/implementation/sprint-1-delivery.md)
- Migration orchestration notes: [Migration Tooling](docs/implementation/migration-tooling.md)
- Stage 2 live integration notes: [Stage 2 Live Integrations](docs/implementation/stage-2/live-integrations.md)
- Sprint 3 progress: [Sprint 3 Delivery (Phase 1)](docs/implementation/sprint-3-delivery-phase-1.md)
- Sprint 4 delivery log: [Sprint 4 Delivery](docs/implementation/sprint-4-delivery.md)
- Sprint 6 delivery log: [Sprint 6 Delivery](docs/implementation/sprint-6-delivery.md)
- Release rollout checklist: [Canary Plan](docs/implementation/release-canary-plan.md)
- Demo hosting guide: [Demo Hosting](docs/implementation/demo-hosting.md)
- Pilot hosting guide: [Pilot Hosting](docs/implementation/pilot-hosting.md)
- Stage 3 webhook security notes: [Stage 3 Security Hardening](docs/implementation/stage-3/security-hardening.md)

## Webapp Demo
- Run: `bash scripts/run-webapp.sh`
- Container run: `bash scripts/run-demo-container.sh`
- Open: `http://127.0.0.1:8080`
- Smoke test: `bash scripts/webapp-smoke-test.sh`
- Pilot smoke test: `bash scripts/pilot-smoke-test.sh`
- Frontend browser smoke: `bash scripts/frontend-browser-smoke.sh`
- Live credential validation: `bash scripts/run-live-validations.sh`
- Full hard-gate suite: `bash scripts/mvp-gates.sh`

## Hosted Pilot Notes
- Set `ATLASLY_DEPLOYMENT_TIER=mvp` or `pilot` in Railway.
- Set `ATLASLY_DATA_DIR=/data` when using a mounted volume for persistent hosted state.
- `ATLASLY_STAGE05_RUNTIME_BACKEND=sqlite` and `ATLASLY_STAGE05_PERSISTENCE_READY=true` are required for pilot-safe mode.
- Demo-only routes (`/api/demo/reset`, `/api/demo/run-scenario`) are disabled automatically outside demo tier.
- Hosted diagnostics now live at:
  - `GET /api/readiness`
  - `GET /api/runtime-diagnostics`
  - `POST /api/demo/start`
  - `POST /api/stage2/connector-validate`
- Live Accela polling requires:
  - `ATLASLY_ACCELA_APP_ID`
  - `ATLASLY_CONNECTOR_SECRET_<REF>` containing an OAuth access token, not the app secret
  - an Atlasly internal permit binding created for the target external permit id
- The browser Integrations page now exposes:
  - credential ref updates
  - external permit binding creation
  - connector validation
  - live connector poll operator output

## Frontend
- Source app: `/Users/deepnandre/Desktop/Atlasly-flow/frontend`
- Built assets served by the runtime: `/Users/deepnandre/Desktop/Atlasly-flow/webapp`
- Frontend commands:
  - `cd frontend && npm run lint`
  - `cd frontend && npm run test`
  - `cd frontend && npm run build`
