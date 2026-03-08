# Stage 2 Slice 3 Contract Tests

Date: 2026-03-03  
Owner: Agent-5

## Scope
- Status sync polling run storage (`portal_sync_runs`).
- Observed status capture and dedupe (`permit_status_events`).
- Provenance guarantees (`status_source_provenance`).
- API contract for `GET /permits/{permitId}/status-timeline`.
- Shared envelope event contract for `permit.status_observed` v1.

## Contract tests
1. Migration integrity.
- Required tables exist:
  - `portal_sync_runs`
  - `permit_status_events`
  - `status_source_provenance`.
- Required indexes exist:
  - `(connector, organization_id, run_started_at)` equivalent index on `portal_sync_runs`.
  - `(permit_id, observed_at)` equivalent index on `permit_status_events`.

2. Status normalization safety.
- `normalized_status` constrained to shared Stage 2 enum:
  - `submitted`, `in_review`, `corrections_required`, `approved`, `issued`, `expired`.
- `confidence` constrained between `0` and `1`.

3. Event dedupe contract.
- Unique `(organization_id, event_hash)` on `permit_status_events`.
- Replay of same upstream observation hash does not produce duplicate timeline entries.

4. Provenance completeness.
- Every timeline response event includes provenance fields:
  - `source_type`, `source_ref`, `source_payload_hash`.

5. `permit.status_observed` schema contract.
- `event_type=permit.status_observed`, `event_version=1`.
- Shared envelope fields required.
- Payload requires:
  - `permit_id`, `raw_status`, `normalized_status`, `source`, `confidence`, `observed_at`.

6. Rollback safety.
- Rollback script drops Slice 3 tables in dependency-safe order.

## Execution command
- `python3 -m unittest tests/stage2/test_stage2_slice3_contracts.py`
