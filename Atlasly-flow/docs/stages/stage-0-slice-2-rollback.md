# Stage 0 Slice 2 Rollback Notes

Date: 2026-03-03  
Scope: `000004_stage0_core_domain` migration.

## What Slice 2 Adds

- Core Stage 0 entities:
  - `ahj_profiles`
  - `projects`
  - `project_contacts`
  - `permits`
  - `tasks`
  - `task_comments`
- Tenant-safe composite foreign keys across organization-owned relations.
- Canonical permit lifecycle guard:
  - `app_is_valid_permit_status_transition(...)`
  - `permits_enforce_status_transition()` trigger
- Utility triggers/functions:
  - `set_updated_at()`
  - `increment_task_version()`

## Rollback Order

1. `db/migrations/000004_stage0_core_domain.down.sql`
2. If full rollback to pre-Slice 1 is needed, continue:
  - `db/migrations/000003_stage0_identity_and_tenancy.down.sql`
  - `db/migrations/000002_stage0_create_types.down.sql`
  - `db/migrations/000001_stage0_enable_extensions.down.sql`

## Rollback Caveats

- Data loss: rolling back `0004` drops all core project/permit/task/AHJ data.
- Trigger dependencies: `0004` down removes trigger functions before table drops; do not drop manually out of order.
- Enum dependency: `permit_status` enum remains in Slice 1/2 baseline; if other objects depend on it, keep `0002` intact.

## Pre-Rollback Checklist

1. Capture backup/snapshot.
2. Disable writes for project/permit/task endpoints.
3. Confirm no downstream migration has already depended on `0004` tables/functions.
4. Apply `0004` down migration in a maintenance window.
5. Run smoke checks to confirm expected object removal and baseline integrity.

