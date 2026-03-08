# Canary Rollout and Rollback Checklist

## Scope
Launch checklist for `REL-002` (canary rollout) and production freeze controls.

## Canary order
1. Stage 0/0.5 controls (auth/RBAC, webhooks, API-key governance, SLO reporting)
2. Stage 1A/1B comment extraction + routing flows
3. Stage 2 intake/autofill/sync connector paths
4. Stage 3 preflight + payout/reconciliation paths

## Go/No-Go gates
- `bash scripts/mvp-gates.sh` passes on release candidate commit.
- `bash scripts/webapp-smoke-test.sh` passes against release environment.
- No cross-tenant authz failures in last 24h.
- No unresolved P1 incidents.
- Stage 0.5 SLO snapshot:
  - webhook success rate `>= 0.99`
  - connector success rate `>= 0.985`
  - dead-letter backlog `< 25`

## Freeze checklist
- Lock migrations except emergency fixes.
- Lock shared contracts (`contracts/**`) unless versioned.
- Freeze feature flags for non-launch-critical experiments.
- Record final release SHA and rollback SHA.
- Capture dashboard screenshots: portfolio, permit ops, finance ops, enterprise SLO.

## Rollback checklist
1. Disable Stage 3 payout writes.
2. Disable Stage 2 live connector poll jobs.
3. Revert webapp/runtime deploy to rollback SHA.
4. If schema rollback required, execute stage rollback docs in reverse order.
5. Re-run smoke test and confirm control-tower read endpoints are healthy.

## Incident comms template
- Trigger condition:
  - SLO breach sustained for 15 minutes, or
  - P1 incident opened.
- Notify:
  - Engineering on-call
  - Product owner
  - Support lead
- Include:
  - incident code
  - impacted endpoints/workflows
  - mitigation ETA
