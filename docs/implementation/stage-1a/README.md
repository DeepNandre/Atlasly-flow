# Stage 1A Implementation Index

This directory tracks Stage 1A delivery in PR-sized slices.

## Slices
- `slice-1.md`: base tables, extraction schema contract, baseline checks.
- `slice-2.md`: state-transition guards and event emission dedupe table.
- `slice-3.md`: event emission helper and canonical emission-point enforcement.
- `slice-4.md`: approval workflow and immutable snapshot persistence.
- `slice-5.md`: read-model functions for status/extractions/snapshot retrieval.
- `slice-6.md`: pipeline entrypoint functions and operational scripts.
- `slice-7.md`: runtime service/api/evaluation modules and Stage 1A harness completion.

## Operational commands
From repo root:
- Drift checks: `scripts/stage1a-drift-check.sh`
- Apply all slices: `DATABASE_URL=... scripts/stage1a-apply.sh`
- Run all SQL checks: `DATABASE_URL=... scripts/stage1a-test.sh`
- Rollback all slices: `DATABASE_URL=... scripts/stage1a-rollback.sh`
- Full ephemeral DB validation: `scripts/db/test_stage1a.sh`

## Contract lock reminders
- Do not rename shared Stage 1A endpoint paths.
- Do not rename shared Stage 1A event types.
- Use `event_version` for versioning; keep internal `event_type` un-suffixed.
