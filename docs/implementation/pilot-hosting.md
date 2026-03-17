# Atlasly Pilot Hosting

## Purpose
- Run Atlasly in a hosted pilot-safe mode on Railway or any Docker host with persistent storage.

## Required env
- `ATLASLY_DEPLOYMENT_TIER=mvp`
- `ATLASLY_STAGE05_RUNTIME_BACKEND=sqlite`
- `ATLASLY_STAGE05_PERSISTENCE_READY=true`
- `ATLASLY_DATA_DIR=/data`
- `ATLASLY_SHOVELS_API_KEY=...`
- `ATLASLY_ACCELA_APP_ID=...`
- `ATLASLY_CONNECTOR_SECRET_<REF>=<oauth access token>`

## Runtime behavior
- Demo routes are disabled outside demo tier.
- `/api/bootstrap` seeds a single pilot workspace if no persisted workspace exists.
- `/api/readiness` exposes deploy-time readiness checks for Railway triage.
- `/api/runtime-diagnostics` exposes runtime state, session health, and launch blockers.
- `/api/demo/start` seeds a hosted-safe guided demo story.
- Runtime state, Stage 2, and Stage 3 data persist under `ATLASLY_DATA_DIR`.

## Accela live path
1. Save connector credential ref with `/api/stage2/connector-credentials/rotate`.
2. Validate the connector with `/api/stage2/connector-validate`.
3. Create an internal-to-external permit binding with `/api/stage2/permit-bindings`.
4. Run `/api/stage2/poll-live`.
5. Inspect `operator_messages` in the response for invalid token, missing app id, unmapped record, or no observations.
6. In the browser, use the Integrations page:
   - `Update Credential Ref`
   - `Validate Connector`
   - `External Permit Bindings`
   - `Live Connector Poll`

## Validation
- Browser smoke: `bash scripts/frontend-browser-smoke.sh`
- API smoke: `bash scripts/webapp-smoke-test.sh`
- Pilot smoke: `bash scripts/pilot-smoke-test.sh`
- Live validations: `bash scripts/run-live-validations.sh`

## Railway checklist
- Add a persistent disk and set `ATLASLY_DATA_DIR=/data`.
- Redeploy after any credential/env change.
- For live validation, set:
  - `ATLASLY_LIVE_CONNECTOR=accela_api`
  - `ATLASLY_LIVE_AHJ_ID=<target ahj>`
  - `ATLASLY_LIVE_CREDENTIAL_REF=<ref>`
  - `ATLASLY_LIVE_EXTERNAL_PERMIT_ID=<real external permit id>`

## Rollback
- Revert the Railway deployment to the previous image.
- Keep `ATLASLY_DATA_DIR` mounted so the persisted pilot state remains intact.
