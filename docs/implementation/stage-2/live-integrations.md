# Stage 2 Live Integrations (Sprint 3 Start)

## Scope
- Added live connector adapter support for `accela_api` and configurable `opengov_api`.
- Added Stage 2 connector credential vault primitives (credential reference rotation + env-backed secret resolution).
- Added Shovels-backed AHJ intelligence lookup endpoint and intake-flow hook.

## Endpoints
- `POST /api/stage2/resolve-ahj`
- `GET /api/stage2/connector-credentials`
- `POST /api/stage2/connector-credentials/rotate`
- `POST /api/stage2/poll-live`
- `GET /api/enterprise/integrations-readiness`

## Runtime configuration
- `ATLASLY_SHOVELS_API_KEY`
- `ATLASLY_SHOVELS_BASE_URL` (default: `https://api.shovels.ai`)
- `ATLASLY_ACCELA_BASE_URL` (default: `https://apis.accela.com`)
- `ATLASLY_ACCELA_APP_ID` (optional)
- `ATLASLY_OPENGOV_BASE_URL` (required for live OpenGov polling)
- `ATLASLY_OPENGOV_STATUS_PATH` (default: `/permits/status`)

## Credential vault convention
- Connector credentials store only `credential_ref`.
- Secret material is loaded from env var:
  - `ATLASLY_CONNECTOR_SECRET_<SANITIZED_CREDENTIAL_REF>`
- Example:
  - `credential_ref = accela_prod_token`
  - env var key = `ATLASLY_CONNECTOR_SECRET_ACCELA_PROD_TOKEN`

## Validation harness
- Use `bash scripts/run-live-validations.sh` to run:
  1. Integration readiness summary
  2. Stage 2 live poll check (when `ATLASLY_LIVE_CREDENTIAL_REF` and secret env are set)
  3. Stage 3 Stripe sandbox payout check (when `ATLASLY_STRIPE_SECRET_KEY` is set)
- Set `ATLASLY_LIVE_VALIDATION_STRICT=1` to fail fast when required credentials are missing.

## Source references
- Accela API docs and base URL guidance:
  - [Accela APIs Documentation](https://developer.accela.com/docs/get-started.html)
- Shovels API reference:
  - [Shovels API Docs](https://docs.shovels.ai/)
- OpenGov developer docs:
  - [OpenGov Developer Portal](https://developer.opengov.com/)
