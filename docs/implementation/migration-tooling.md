# Migration Tooling (Sprint 2 Start)

## Scope
- Added a migration orchestrator for planning, checksum verification, manifest writing, and SQLite apply/rollback rehearsal.
- Added backup/restore rehearsal script for the local SQLite runtime artifact.

## Commands
- Plan migrations:
  - `python3 scripts/db/migration_orchestrator.py --action plan --direction up`
- Write checksum manifest:
  - `python3 scripts/db/migration_orchestrator.py --action write-manifest`
- Verify checksum manifest:
  - `python3 scripts/db/migration_orchestrator.py --action verify`
- Dry-run apply:
  - `python3 scripts/db/migration_orchestrator.py --action apply --direction up --dry-run`
- Apply one rollback step:
  - `python3 scripts/db/migration_orchestrator.py --action apply --direction down --steps 1`
- Backup/restore rehearsal:
  - `bash scripts/db/backup_restore_rehearsal.sh atlasly_stage2_demo.sqlite3`

## Files
- `scripts/db/migration_orchestrator.py`
- `scripts/db/backup_restore_rehearsal.sh`
- `tests/db/test_migration_orchestrator.py`

## Current limitations
- Apply/rollback execution path is SQLite-focused for local rehearsal.
- Postgres production migration execution remains a Sprint 2 follow-up.
