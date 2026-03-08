# Stage 2 Slice 2

Status: Implemented  
Date: 2026-03-03  
Owner: Agent-5

## Scope
- Add AHJ requirements versioning schema with active-version control.
- Add canonical form field-mapping registry schema for autofill engine setup.
- Add connector credential reference schema for API-first and fallback connectors.
- Lock `permit.application_generated` v1 event contract under shared envelope policy.

## Contract Safety
- No shared enum/event/API contract names were changed in this slice.
- Canonical contracts preserved:
  - `POST /permits/{permitId}/applications/generate`
  - `permit.application_generated` v1

## Files
- Migration:
  - `db/migrations/000024_stage2_requirements_mappings_connectors.sql`
- Rollback SQL:
  - `db/migrations/rollback/000024_stage2_requirements_mappings_connectors_rollback.sql`
- Event schema:
  - `contracts/stage2/permit.application_generated.v1.schema.json`
- Contract tests:
  - `tests/stage2/test_stage2_slice2_contracts.py`
  - `tests/stage2/slice-2-contract-tests.md`
- Rollback runbook:
  - `docs/implementation/stage-2/slice-2/rollback.md`
