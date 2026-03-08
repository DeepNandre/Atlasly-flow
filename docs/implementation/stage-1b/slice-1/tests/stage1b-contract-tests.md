# Stage 1B Contract Tests (Slice 1)

Date: 2026-03-03
Owner: Agent-4

## Test Scope
- Duplicate request handling for `POST /comment-letters/{letterId}/create-tasks`.
- Duplicate event safety for Stage 1B event producers/consumers.
- Reassignment feedback integrity requirements.

## Preconditions
- Stage 0 tables exist: `tasks`, `domain_events`, `event_consumer_dedup`.
- Stage 1A tables exist: `comment_letters`, `comment_extractions`.
- Slice 1 migration applied.

## A) Duplicate Request Tests

### A1. Idempotent replay with same key
1. Seed one approved extraction item.
2. Call create-tasks with `Idempotency-Key: K1`.
3. Retry same request with key `K1`.
Expected:
- exactly one `task_generation_runs` row for `(org_id, K1)`.
- one `tasks` row for seeded `source_extraction_id`.
- second response matches first `task_ids` and counts.

### A2. Concurrent duplicate generation under race
1. Seed N approved extraction items.
2. Issue two concurrent create-tasks requests for same letter.
Expected:
- no duplicate `(organization_id, source_extraction_id)` rows.
- total tasks equals N.
- run ledger resolves deterministically (`COMPLETED` once, replay/duplicate outcome documented).

### A3. Mixed approved/unapproved extraction request
1. Seed one approved and one non-approved extraction.
2. Call create-tasks including both ids.
Expected:
- request fails.
- no tasks inserted for this run (transaction rollback).

## B) Duplicate Event Tests

### B1. Producer duplicate outbox write
1. Simulate two publish attempts with same outbox idempotency key.
Expected:
- one logical event persists due to `domain_events` unique `(organization_id, idempotency_key)`.

### B2. Consumer duplicate delivery dedupe
1. Deliver same `event_id` twice to same consumer.
Expected:
- first processed; second skipped by `event_consumer_dedup`.
- no duplicate side effects.

### B3. Out-of-order duplicate assignment event
1. Emit `task.auto_assigned` twice around manual reassignment.
Expected:
- final task assignee reflects latest valid state.
- feedback/audit has no duplicate effective assignment action.

## C) Reassignment Feedback Integrity Tests

### C1. Missing feedback reason
1. Call `POST /tasks/{taskId}/reassign` without `feedback_reason_code`.
Expected:
- validation failure (`422`).

### C2. Invalid reassignment target
1. Attempt reassignment where `from_assignee_id == to_assignee_id`.
Expected:
- write rejected by API and DB check constraint.

### C3. Successful reassignment with prior auto-assignment
1. Reassign an auto-assigned task.
Expected:
- `task_assignment_feedback` row exists with:
  - `source_rule_id` and `source_confidence` populated.
  - non-null `actor_user_id`, `feedback_reason_code`, `was_auto_assigned=true`.

### C4. Cross-tenant tamper attempt
1. Attempt reassignment referencing task/rule from different org or project.
Expected:
- rejected by authorization and tenant consistency checks.

## Event Contract Snapshot Checks
- Validate each Stage 1B event uses canonical envelope fields:
  - `event_type`, `event_version`, `idempotency_key`, `trace_id`.
- Locked event registry names:
  - `tasks.bulk_created_from_extractions` v1
  - `task.auto_assigned` v1
  - `task.assignment_overdue` v1
- Breaking payload changes must fail snapshot tests unless new `event_version` introduced.

## CI Gate
- Run this suite on every migration change and every API/event contract change.
- Block promotion if duplicate-protection or snapshot checks fail.
