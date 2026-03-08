# Stage 2 Slice 1

Status: Implemented  
Date: 2026-03-03  
Owner: Agent-5

## Scope
- Add Stage 2 intake persistence foundations (`intake_sessions`, `permit_applications`).
- Lock permit-type validation at migration layer for MVP permit cohorts.
- Add intake API and event contract specs for implementation alignment.
- Define rollback path and contract test coverage for intake slice.

## Contract Safety
- No shared enum/event/API contract names were changed in this slice.
- Canonical Stage 2 contract names remain:
  - `POST /intake-sessions`
  - `PATCH /intake-sessions/{sessionId}`
  - `intake.completed` v1

## Files
- Migration: `db/migrations/000023_stage2_intake_foundations.sql`
- Rollback SQL: `db/migrations/rollback/000023_stage2_intake_foundations_rollback.sql`
- API contract: `contracts/stage2/intake-sessions.v1.openapi.yaml`
- Event schema: `contracts/stage2/intake.completed.v1.schema.json`
- Contract tests: `tests/stage2/slice-1-contract-tests.md`
- Rollback runbook: `docs/implementation/stage-2/slice-1/rollback.md`
