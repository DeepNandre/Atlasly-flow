# Atlasly Execution Plan (Q2 2026)

Date: March 3, 2026

## Objective
Ship a testable MVP that outperforms manual expediting on speed, visibility, and operational reliability.

## Build sequence (strict)
1. Harden Stage 0 + 0.5 primitives (tenant boundaries, audit, eventing, dashboards)
2. Operationalize Stage 1A + 1B (comment-to-task engine)
3. Expand Stage 2 connector reliability and AHJ coverage
4. Ship Stage 3 predictive + fintech orchestration in sandbox
5. Add vertical launch overlays (solar/EV, MEP)

## Sprint plan (6 x 2-week sprints)

### Sprint 1 - Control tower and workflow UX
Scope:
- Portfolio dashboard UI with project/permit/task rollups
- Unified activity feed from stage events
- Operator-friendly workflow navigation (Overview, Comment Ops, Permit Ops, Finance Ops)

Exit:
- PM can run end-to-end demo from browser without scripts

Status:
- In progress/completed in this repo (webapp upgraded and validated via smoke test)

### Sprint 2 - Comment Ops quality gates
Scope:
- Reviewer queue UX for needs-review extractions
- Routing-rule management UX and dry-run explainability
- SLA/escalation visual indicators

Exit:
- Reviewer can approve/route comments entirely from UI with visible confidence/ownership

### Sprint 3 - Intake and form quality
Scope:
- Intake completeness meter
- Mapping diagnostics (required-field failures by form)
- AHJ requirement snapshot surfacing in UI

Exit:
- Application generation failures show actionable remediation within one screen

### Sprint 4 - City Sync reliability
Scope:
- Connector health dashboard (success rates, retries, DLQ)
- Transition-review queue for invalid/low-confidence status events
- Reconciliation report UX

Exit:
- Operations can detect and resolve sync drift without DB access

### Sprint 5 - Predictive preflight and recommendation ops
Scope:
- Preflight risk panel with top factors + evidence references
- Recommendation acceptance workflow and tracking
- Model version and snapshot metadata display

Exit:
- PM can act on preflight recommendations before resubmission

### Sprint 6 - Fintech sandbox launch
Scope:
- Payout approval controls (role/step-up)
- Provider webhook and settlement monitor
- Reconciliation mismatch resolution workflow

Exit:
- End-to-end payout simulation with auditable ledger trail passes smoke tests

## Technical guardrails
- No shared contract changes without explicit changelog entry and migration note
- Every slice must include rollback notes and targeted tests
- Idempotency keys mandatory for side-effecting endpoints
- Event payload schemas locked by contract tests before merge

## Engineering backlog by priority

### P0 (do immediately)
- Portfolio + activity API aggregation endpoint hardening
- UI for project/permit/task control tower
- Stage 1A reviewer queue and Stage 1B routing explainability panel

### P1
- Connector observability and reconciliation dashboard
- AHJ requirement snapshots surfaced in intake flow
- Stage 3 outbox monitoring in UI

### P2
- Vertical templates (solar/EV, MEP)
- Service-partner handoff workflows
- Advanced analytics for cycle-time variance

## KPI targets for first external pilots
- Comment triage cycle reduced from weeks to <1 business day
- 80%+ extraction tickets auto-routed for target trade vertical
- 95%+ status update freshness within 24h polling window
- 25% reduction in permit cycle-time variance for pilot cohorts

## Risks and mitigations
- Risk: AHJ portal variance breaks connectors
  - Mitigation: adapter versioning, runbook fallback, transition review queues
- Risk: low-confidence extraction creates rework
  - Mitigation: strict review gates, correction feedback loop, benchmark harness
- Risk: fintech workflows increase compliance overhead
  - Mitigation: sandbox-first rollout, gated roles, full audit trail
