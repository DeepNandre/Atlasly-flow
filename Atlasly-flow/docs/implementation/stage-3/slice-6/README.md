# Stage 3 Slice 6

Status: Implemented
Date: 2026-03-03
Owner: Agent-6

## Scope
- Add DB-backed Stage 3 repository implementation using SQLite for transactional integration tests.
- Add atomic payout-instruction + outbox insert path for replay safety.
- Add PostgreSQL migration contract test for Stage 3 persistence scaffolding constraints.

## Contract Safety
- No shared enum, event name, event envelope, or API path changes were introduced.
- Canonical Stage 3 event/API contracts remain unchanged.

## Files
- SQLite repository: `scripts/stage3/sqlite_repository.py`
- Repository adapter extension: `scripts/stage3/repositories.py`
- Persisted payout path update: `scripts/stage3/payout_api.py`
- DB contract test SQL: `db/tests/006_stage3_persistence_contracts.sql`
- DB test runner: `scripts/db/test_stage3_slice6.sh`
- DB test README update: `db/tests/README.md`
- Integration tests: `tests/stage3/test_stage3_slice6_sqlite_repository.py`

## Rollback Notes
1. Remove/disable SQLite repository usage in Stage 3 wiring if rollback required.
2. Apply `db/migrations/rollback/000033_stage3_persistence_scaffolding_rollback.sql` for DB rollback.
3. Keep Stage 3 foundational schema (`000032_stage3_foundations.sql`) unless full Stage 3 rollback is required.
