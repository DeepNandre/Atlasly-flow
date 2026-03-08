# Sprint 3 Delivery (Phase 1)

## Tickets advanced
- `INT-001` (partial): Added live connector adapter path (`accela_api`, configurable `opengov_api`) and `POST /api/stage2/poll-live`.
- `INT-002` (partial): Added Shovels-backed AHJ lookup + intake flow hook (`POST /api/stage2/resolve-ahj`).
- `INT-003` (partial): Added connector credential vault primitives and rotation/list endpoints.
- `OPS-003` (partial): Added enterprise alert surface for DLQ/replay backlog monitoring.

## Files
- `scripts/stage2/live_connectors.py`
- `scripts/stage2/ahj_intelligence.py`
- `scripts/stage2/connector_credentials.py`
- `scripts/stage2/repositories.py`
- `scripts/stage2/sqlite_repository.py`
- `scripts/webapp_server.py`
- `webapp/index.html`
- `webapp/app.js`
- `tests/stage2/test_stage2_slice10_live_integrations.py`
- `tests/stage2/test_stage2_slice9_sqlite_repository.py`

## Validation
- `python3 -m unittest discover -s tests/stage2 -p 'test_*.py'`
- `python3 -m unittest discover -s tests/webapp -p 'test_*.py'`
- `bash scripts/webapp-smoke-test.sh`
- `bash scripts/mvp-gates.sh`

## Remaining for Sprint 3 completion
- Production credential manager (beyond env-ref fallback).
- Live OpenGov path validation against real sandbox credentials.
- End-to-end staging runbook with real connector telemetry and error-budget checks.
