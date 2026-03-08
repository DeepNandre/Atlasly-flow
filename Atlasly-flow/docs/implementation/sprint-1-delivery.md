# Sprint 1 Delivery (Security + Runtime Boundary + CI)

## Tickets completed
- `PLAT-001`: Session auth middleware + route-level RBAC for `/api/*` (except `/api/health`, `/api/bootstrap`).
- `PLAT-002`: Added privilege-escalation and tenant-boundary tests for control tower route authorization.
- `OPS-001`: Enforced Stage 0.5 runtime hardening boundary on enterprise routes (reject in-memory for production-like tiers).
- `REL-001`: Added CI workflow to run MVP hard gates on push/PR.

## Files changed
- `scripts/webapp_server.py`
- `webapp/app.js`
- `scripts/webapp-smoke-test.sh`
- `tests/webapp/test_control_tower_authz.py`
- `contracts/stage0_5/apis/control-tower.v1.openapi.yaml`
- `.github/workflows/ci.yml`

## Validation
- `python3 -m py_compile scripts/webapp_server.py`
- `node --check webapp/app.js`
- `python3 -m unittest tests/webapp/test_control_tower_authz.py tests/webapp/test_control_tower_runtime.py tests/stage0_5/test_stage0_5_contracts.py tests/webapp/test_control_tower_contracts.py`
- `bash scripts/webapp-smoke-test.sh`
- `bash scripts/mvp-gates.sh`

## Notes
- Bootstrap now returns session tokens (`session` + `sessions`) for role-based testing in the demo runtime.
- API callers must include `Authorization: Bearer <token>` for protected routes.
