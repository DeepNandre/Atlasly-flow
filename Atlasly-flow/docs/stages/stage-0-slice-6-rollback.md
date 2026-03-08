# Stage 0 Slice 6 Rollback Notes

Date: 2026-03-03  
Scope: `000008_stage0_rls_policies` migration.

## What Slice 6 Adds

- Session helper functions:
  - `app_current_organization_id()`
  - `app_current_user_id()`
  - `app_has_org_role(...)`
  - `app_has_org_access(...)`
  - `app_can_access_project(...)`
  - `app_is_task_assignee(...)`
- RLS enabled + forced for tenant-scoped Stage 0 tables.
- Role-based policies aligned to Stage 0 RBAC baseline.

## Rollback Order

1. `db/migrations/000008_stage0_rls_policies.down.sql`
2. If full rollback is needed, continue with prior slice downs (`0007`..`0001`) in reverse order.

## Rollback Caveats

- Security regression risk: rollback disables tenant isolation at DB policy layer.
- Application dependency: service code expecting `app_*` helper functions must be updated before rollback.

## Pre-Rollback Checklist

1. Confirm maintenance window and temporary compensating controls at API layer.
2. Backup/snapshot DB.
3. Disable direct app traffic if DB-level isolation is mandatory.
4. Apply `0008` down.
5. Validate policy/function removal and re-enable traffic intentionally.

