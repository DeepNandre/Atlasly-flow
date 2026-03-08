# Stage 0.5 Slice 7: Service Runtime + API Contracts

## Scope
- Implement Stage 0.5 service-layer runtime modules for endpoint behavior and operational controls.
- Add Stage 0.5 OpenAPI contracts and event payload schemas.
- Add runtime and contract tests for webhook, connector, dashboard, API key, task template, and audit export flows.

## Contract-change note
- No shared enums/events/API contracts were changed.
- Added Stage 0.5 contract files under `contracts/stage0_5/*` aligned with existing stage specs and event names.

## Delivered artifacts
- Service core: `scripts/stage0_5/enterprise_service.py`
- API wrapper layer: `scripts/stage0_5/runtime_api.py`
- Contracts:
  - `contracts/stage0_5/apis/webhooks.v1.openapi.yaml`
  - `contracts/stage0_5/apis/webhook-events.v1.openapi.yaml`
  - `contracts/stage0_5/apis/connectors-sync.v1.openapi.yaml`
  - `contracts/stage0_5/apis/dashboard-portfolio.v1.openapi.yaml`
  - `contracts/stage0_5/apis/org-api-keys.v1.openapi.yaml`
  - `contracts/stage0_5/events/integration.run_started.v1.schema.json`
  - `contracts/stage0_5/events/integration.run_completed.v1.schema.json`
  - `contracts/stage0_5/events/webhook.delivery_failed.v1.schema.json`
- Tests:
  - `tests/stage0_5/test_stage0_5_contracts.py`
  - `tests/stage0_5/test_stage0_5_runtime_api.py`
- Runner:
  - `scripts/stage0_5-test.sh`

## Operational behavior implemented
- `POST /webhooks` semantics with idempotency, URL validation, event allowlist, and active dedupe.
- `GET /webhook-events` filtering by subscription/status/time/attempt.
- Delivery runtime: retry scheduling, terminal classification, dead-letter insertion, replay request queueing.
- `POST /connectors/{name}/sync` semantics with idempotency and run-start event emission.
- Connector completion and error taxonomy handling with completion event emission.
- `GET /dashboard/portfolio` latest snapshot retrieval with freshness.
- `POST /orgs/{orgId}/api-keys` creation with scoped validation, hashed-at-rest storage model, one-time plaintext behavior, rotate/revoke controls.
- Task template lifecycle and owner/admin-gated audit export lifecycle flows.

## Hardening boundary
- In-memory runtime components are explicitly non-production.
- Production-like tiers (`mvp`, `public_mvp`, `prod`) must fail closed unless:
  - runtime backend is not `in_memory`, and
  - persistence readiness is explicitly provided and true.

## MVP persistence adapter path
- Local/dev: `InMemoryStage05Adapter` (not production-ready).
- MVP launch: `SqlFunctionStage05Adapter` with required Stage 0.5 SQL contracts discoverable.
- Required contracts list is centralized in:
  - `scripts/stage0_5/persistence_adapter.py::required_stage0_5_mvp_contracts()`

## Rollout plan
1. Apply Stage 0 and Stage 0.5 DB slices 1-6.
2. Deploy `scripts/stage0_5/*` runtime modules.
3. Run `scripts/stage0_5-test.sh` in CI.
4. Wire endpoint handlers to Stage 0.5 runtime API wrappers.

## Rollback plan
1. Disable Stage 0.5 endpoint handlers/worker invocations.
2. Roll back service deployment containing `scripts/stage0_5/*`.
3. Keep DB state unchanged unless DB rollback is required by an independent incident.

## Rollback risk notes
- Service rollback without DB rollback may leave records created by Stage 0.5 paths; data remains valid but operational automation halts.
- If DB rollback also occurs, replay and lifecycle state continuity for webhook deliveries and audit exports may be interrupted.
