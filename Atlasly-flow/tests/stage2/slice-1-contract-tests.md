# Stage 2 Slice 1 Contract Tests

Date: 2026-03-03  
Owner: Agent-5

## Scope
- Intake storage/migration safety (`intake_sessions`, `permit_applications`).
- Intake API contract compliance for `POST /intake-sessions` and `PATCH /intake-sessions/{sessionId}`.
- Shared envelope compliance for `intake.completed` v1.

## Test cases

1. Migration applies cleanly on empty schema.
- Assert both tables exist.
- Assert indexes:
  - `idx_intake_sessions_project_step`
  - `idx_permit_applications_permit_generated`.

2. Permit type enum validation at DB layer.
- Insert with `permit_type=commercial_ti` succeeds.
- Insert with `permit_type=unknown` fails with check-constraint violation.

3. Intake completion invariant.
- Update session to `status=completed` with `completed_at` set succeeds.
- Update session to `status=completed` without `completed_at` fails.

4. `POST /intake-sessions` contract.
- Missing `Idempotency-Key` -> `400`.
- Missing `project_id` or `permit_type` -> `422`.
- Unsupported `permit_type` -> `422`.
- Valid request -> `201` and response includes `session_id`, `current_step`, `status`, `version`.

5. `PATCH /intake-sessions/{sessionId}` optimistic concurrency.
- Missing `If-Match-Version` -> `400`.
- Stale `If-Match-Version` -> `409`.
- Valid patch increments `version` and returns `200`.

6. `intake.completed` event schema validation.
- Event must include shared envelope fields:
  `event_id`, `event_type`, `event_version`, `organization_id`, `aggregate_type`,
  `aggregate_id`, `occurred_at`, `produced_by`, `idempotency_key`, `trace_id`, `payload`.
- `event_type=intake.completed`, `event_version=1`, `aggregate_type=intake_session`.
- Payload includes `session_id`, `project_id`, `permit_type`, `ahj_id`.

7. Idempotency replay behavior.
- Replayed create request with same `Idempotency-Key` returns same resource identity.
- No duplicate `intake.completed` outbox event for the same idempotency key.

## Exit criteria for Slice 1
- All tests above pass in CI/integration environment.
- No shared contract changes introduced (event names and versions unchanged).
