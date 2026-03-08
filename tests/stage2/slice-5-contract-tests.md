# Stage 2 Slice 5 Contract and Runtime Tests

Date: 2026-03-03  
Owner: Agent-5

## Scope
- Runtime connector poll and status normalization scaffold.
- Transition validity matrix enforcement and review-queue behavior.
- Drift classification logic and persistence schema for alerts/rules.

## Contract/runtime tests
1. Poll idempotency behavior.
- Same `(org, connector, ahj, idempotency_key)` returns existing run and no duplicate run rows in memory store.

2. Poll role guard.
- Non `owner|admin|pm` caller is rejected (`403`).

3. Normalization confidence tiers.
- Exact rule match returns `0.99`.
- Regex rule match returns `0.95`.
- Lexical fallback returns `0.75`.

4. Invalid transition queueing.
- Rejected transition creates a `status_transition_reviews` record with `resolution_state=open`.

5. Drift classification.
- Ruleset change -> `mapping_drift`.
- Same ruleset with payload hash change -> `source_drift`.
- Neither change -> `timeline_gap`.

6. Migration contract.
- `status_normalization_rules` and `status_drift_alerts` tables exist with enum/check constraints.

## Execution commands
- `python3 -m unittest tests/stage2/test_stage2_slice5_contracts.py`
- `python3 -m unittest tests/stage2/test_stage2_slice5_runtime.py`
