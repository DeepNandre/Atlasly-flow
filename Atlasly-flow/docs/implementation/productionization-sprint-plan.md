# Atlasly Productionization Sprint Plan (6 Weeks)

## Goal
Ship from demo-ready MVP to production-ready MVP with real integrations, hardened security, and operational reliability.

## Owners
- Agent-1 (Stage 0): tenancy/auth/RBAC/data integrity
- Agent-0.5: enterprise runtime hardening/ops controls
- Agent-1A: extraction pipeline reliability and quality gates
- Agent-1B: routing/assignment/escalation robustness
- Agent-2: intake/autofill/city-sync real connectors
- Agent-3: fintech payout orchestration hardening
- Agent Leader: frontend control tower, cross-stage contracts, release gating

## Hard gates
1. No launch with Stage 0.5 in-memory backend in production-like tiers.
2. No Stage 3 payouts enabled until Stage 2 status normalization is stable in staging.
3. No public launch until cross-tenant/RBAC/security suite passes and runbooks are signed off.

## Sprint 1 (Week 1): Production foundation + security boundary
- Status: Implemented
- `PLAT-001` (Agent-1): Replace demo bootstrap auth path with real session auth middleware + RBAC enforcement on all control tower routes.
- `PLAT-002` (Agent-1): Add tenant-boundary negative tests for all stage endpoints.
- `OPS-001` (Agent-0.5): Enforce Stage 0.5 runtime hardening gate (`in_memory` rejected in mvp/public tiers).
- `REL-001` (Leader): Add CI pipeline for lint, tests, migrations, smoke gates.
- Exit criteria: auth+RBAC fully enforced; CI green on every PR.

## Sprint 2 (Week 2): Persistence + migration safety
- Status: Implemented
- `OPS-002` (Agent-0.5): Implement production persistence adapter for Stage 0.5 and wire runtime API to it.
- `DB-001` (Agent-1): Add migration orchestration scripts (up/down, dry-run, checksum verification).
- `DB-002` (Leader): Add backup/restore rehearsal scripts for SQLite demo + Postgres target.
- `QA-001` (Leader): Add migration rollback integration test job.
- Exit criteria: all Stage 0.5 runtime tests pass on persistent backend; rollback drill documented and passing.

## Sprint 3 (Week 3): Real external integrations (Stage 2)
- Status: In progress (Phase 1 + live validation harness shipped; awaiting credentialed staging run)
- `INT-001` (Agent-2): Integrate one real AHJ connector path (Accela/OpenGov) behind existing contract.
- `INT-002` (Agent-2): Integrate Shovels for AHJ mapping in intake flow.
- `INT-003` (Agent-2): Add connector credential vault integration + rotation.
- `OPS-003` (Agent-0.5): DLQ + replay observability dashboards and alert thresholds.
- Exit criteria: live staging connector sync works daily with normalized status timeline and reconciliation queue.

## Sprint 4 (Week 4): Document/AI pipeline hardening (Stage 1A/1B)
- Status: Implemented
- `DOC-001` (Agent-1A): Replace text-only path with real file upload + OCR + extraction queue worker.
- `DOC-002` (Agent-1A): Add extraction quality gate report (precision/recall baseline + drift check).
- `ROUTE-001` (Agent-1B): Add routing decision explainability audit endpoint and reassignment feedback loop analytics.
- `ROUTE-002` (Agent-1B): Add escalation scheduler durability (retry-safe scheduler ticks).
- Exit criteria: end-to-end comment letter -> approved extraction -> tasks routed in staging with KPI report.

## Sprint 5 (Week 5): Fintech and compliance hardening (Stage 3 + 0.5)
- Status: In progress (webhook security + API key governance + audit evidence + provider selection shipped; awaiting credentialed staging run)
- `PAY-001` (Agent-3): Wire real payment provider sandbox path behind payout state machine (Stripe sandbox adapter implemented; awaiting staging credential run).
- `PAY-002` (Agent-3): Add webhook signature verification, replay protection, and stale-event handling hard tests.
- `SEC-001` (Agent-0.5): Complete API key lifecycle governance (last-used tracking + forced rotation policy job).
- `SEC-002` (Agent-1): Audit export evidence pack automation + permission checks.
- Exit criteria: payout lifecycle works in sandbox end-to-end with reconciliation and signed webhook verification.

## Sprint 6 (Week 6): Launch prep + control tower release
- Status: Implemented (pending only external credentialed validation sign-off)
- `UI-001` (Leader): Finalize control tower UX for degraded states, auth errors, and incident banners.
- `OBS-001` (Leader + Agent-0.5): SLO dashboards (webhook success, connector success, review queue depth, payout mismatches).
- `REL-002` (Leader): Canary rollout plan + rollback checklist + release freeze checklist (`docs/implementation/release-canary-plan.md`).
- `DOC-003` (All owners): Update all stage docs from Drafted -> Implemented/Productionized with exact runbooks.
- Exit criteria: canary-ready production MVP with signed go/no-go checklist.

## Definition of done per ticket
- Code + tests + migration/rollback notes
- Contract updates (if required) with no undocumented drift
- Runbook update
- Monitoring/alert impact noted
- Owner demo recorded in control tower with reproducible steps

## MVP launch KPIs (must meet for 7 consecutive days)
- Webhook success rate >= 99.0%
- Connector success rate >= 98.5%
- Dashboard freshness p95 <= 300s
- Cross-tenant authz violations: 0
- P1 incidents: 0
- Payout reconciliation mismatch rate <= 1.0%
