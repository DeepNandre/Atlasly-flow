# Stage 2 Slice 4 Contract Tests

Date: 2026-03-03  
Owner: Agent-5

## Scope
- Connector poll trigger API contract.
- Status changed event contract alignment to shared envelope.
- Reconciliation run persistence for drift checks.
- Invalid-transition review queue constraints.

## Contract tests
1. Migration integrity.
- Required tables:
  - `status_reconciliation_runs`
  - `status_transition_reviews`.
- Required indexes:
  - `idx_status_recon_runs_org_started`
  - `uq_status_transition_reviews_event_once`.

2. Invalid-transition handling constraints.
- `from_status`/`to_status` constrained to canonical status enum.
- `resolution_state` constrained to `open|accepted_override|dismissed`.
- `status_event_id` uniqueness ensures one review record per rejected event.

3. Connector poll API contract.
- `POST /connectors/{ahj}/poll` exists.
- `Idempotency-Key` required.
- `connector` enum limited to:
  - `accela_api`
  - `opengov_api`
  - `cloudpermit_portal_runner`.

4. Event schema compliance.
- `permit.status_changed` remains at `event_version=1`.
- Shared envelope fields required.
- Payload requires `permit_id`, `old_status`, `new_status`, `source_event_id`.

5. Rollback safety.
- Rollback script removes Slice 4 tables in dependency-safe order.

## Execution command
- `python3 -m unittest tests/stage2/test_stage2_slice4_contracts.py`
