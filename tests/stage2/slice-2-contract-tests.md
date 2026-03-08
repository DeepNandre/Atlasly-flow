# Stage 2 Slice 2 Contract Tests

Date: 2026-03-03  
Owner: Agent-5

## Scope
- AHJ requirement versioning invariants and active-version uniqueness.
- Form mapping lifecycle storage and required uniqueness/index constraints.
- Connector credential storage constraints for Stage 2 connector cohort.
- Event contract lock for `permit.application_generated` v1 shared envelope alignment.

## Contract tests
1. Migration integrity.
- Required tables exist:
  - `ahj_requirements`
  - `application_field_mappings`
  - `connector_credentials`.

2. AHJ requirement versioning constraints.
- `(ahj_id, permit_type, version_number)` must be unique.
- One active version only per `(ahj_id, permit_type)` via partial unique index.
- `version_number > 0` and MVP `permit_type` enum checks enforced.

3. Form mapping constraints.
- Unique mapping tuple enforced per template/version/canonical target.
- `target_field_type` restricted to approved set.
- `retired_at >= effective_at` when present.

4. Connector credential constraints.
- Connector enum restricted to:
  - `accela_api`
  - `opengov_api`
  - `cloudpermit_portal_runner`.
- Status restricted to `active|invalid|revoked|expired`.
- Uniqueness enforced by `(organization_id, connector, coalesce(ahj_id, '__global__'))`.

5. Event schema compliance.
- `permit.application_generated` remains `event_version=1`.
- Shared envelope fields required and payload requires:
  - `permit_id`, `application_id`, `form_template_id`, `mapping_version`, `generated_at`.

6. Rollback integrity.
- Rollback script drops Slice 2 tables in reverse dependency-safe order.

## Execution command
- `python3 -m unittest tests/stage2/test_stage2_slice2_contracts.py`
