# Stage 0 Slice 1 Rollback Notes

Date: 2026-03-03  
Scope: `000001_stage0_enable_extensions` to `000003_stage0_identity_and_tenancy` migrations.

## What Slice 1 Adds

- Extensions: `pgcrypto`, `citext`
- Enums: `membership_role`, `task_status`, `permit_status`, `document_ocr_status`, `notification_channel`, `notification_status`, `event_status`
- Tables: `users`, `organizations`, `workspaces`, `user_identities`, `memberships`
- Indexes: partial uniqueness fixes for nullable `memberships.workspace_id`

## Rollback Order

1. `db/migrations/000003_stage0_identity_and_tenancy.down.sql`
2. `db/migrations/000002_stage0_create_types.down.sql`
3. `db/migrations/000001_stage0_enable_extensions.down.sql`

## Rollback Caveats

- Data loss: rolling back `0003` drops all Slice 1 identity/tenancy data.
- Enum dependency: `0002` rollback requires that no remaining columns use these enums.
- Extension dependency: `0001` rollback requires no remaining objects depend on `citext` or `pgcrypto`.

## Pre-Rollback Checklist

1. Confirm snapshot/backup is available.
2. Confirm no downstream migrations depend on Slice 1 tables/types.
3. Place API writes in maintenance mode for identity/tenancy paths.
4. Execute rollback in strict reverse order.
5. Run post-rollback smoke query set (`\dt`, `\dT`) to verify cleanup.
