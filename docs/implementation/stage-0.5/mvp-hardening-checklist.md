# Stage 0.5 MVP Hardening Checklist

## 0) Runtime Boundary (Explicit)
- `scripts/stage0_5/*` in-memory store is **NOT PRODUCTION READY**.
- Public MVP and production-like tiers (`mvp`, `public_mvp`, `prod`) must reject `runtime_backend=in_memory`.
- API/runtime gate must require explicit persistence readiness signal for production-like tiers.

## 1) Persistence Path Required For MVP Launch
- Required adapter path:
  - `InMemoryStage05Adapter` for local/dev only.
  - `SqlFunctionStage05Adapter` for MVP launch with Stage 0.5 SQL contracts present.
- MVP launch requires `SqlFunctionStage05Adapter.capability_report().production_ready == true`.
- Required Stage 0.5 persistence contracts are defined in:
  - `scripts/stage0_5/persistence_adapter.py::required_stage0_5_mvp_contracts()`

## 2) Failure-Mode Coverage (Webhook)
- Must pass edge-case tests for:
  - non-retryable `4xx` -> terminal + DLQ.
  - retry schedule boundary (`attempt=6` scheduled; `attempt=7` terminal).
  - delivery dedupe on repeated `(subscription,event,attempt)`.
  - replay authorization and missing dead-letter behavior.

## 3) MVP Release Gates (Measurable)
- Webhook success 24h >= `99.0%`.
- Connector success 24h >= `98.5%`.
- Dashboard refresh p95 <= `300s`.
- Dashboard max staleness <= `300s`.
- API key rotation coverage >= `95%`.
- Audit export success 24h >= `99.0%`.
- P1 incidents last 24h == `0`.

## 4) Rollback Trigger Rules
- Webhook success 60m < `97.0%`.
- Webhook DLQ growth 30m > `200`.
- Connector max staleness > `120m`.
- Dashboard max staleness > `900s`.
- P1 incidents last 24h >= `2`.

## 5) Public MVP Go/No-Go Checklist
- [ ] Runtime boundary checks active for production-like tiers.
- [ ] Persistence adapter report marked production-ready.
- [ ] Stage 0.5 DB migrations + rollback drills validated in staging.
- [ ] Stage 0.5 hardening/runtime test suite green.
- [ ] Release gates pass for 7 consecutive days pre-launch.
- [ ] On-call runbooks and rollback authority assigned for launch window.
