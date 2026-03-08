# Stage 2 Slice 8/9 Persistence and Connector Runtime Tests

Date: 2026-03-03  
Owner: Agent-5

## Scope
- Persistence-backed Stage 2 APIs and runtime flows.
- SQLite-backed Stage 2 repository integration.
- Connector retry runtime and reconciliation drift alert generation.
- New migrations:
  - `000030_stage2_connector_poll_attempts.sql`
  - `000031_stage2_event_outbox.sql`

## Tests
1. In-memory persistence integration (`Stage2Repository`).
- Intake complete flow emits `intake.completed` v1.
- Application generation emits `permit.application_generated` v1.
- Connector poll + status ingest persists timeline/provenance.
- Reconciliation detects drift and writes alerts.

2. SQLite repository integration (`Stage2SQLiteRepository`).
- Intake idempotency and outbox persistence.
- Connector retry flow transitions to succeeded after transient failure.
- Timeline retrieval from persisted status/provenance.

3. Migration contract checks.
- Slice 8 poll attempt table/index/rollback.
- Slice 9 stage2 outbox table/index/rollback.

## Execution commands
- `python3 -m unittest tests/stage2/test_stage2_slice8_persistence_integration.py`
- `python3 -m unittest tests/stage2/test_stage2_slice9_sqlite_repository.py`
- `python3 -m unittest tests/stage2/test_stage2_slice8_9_contracts.py`
