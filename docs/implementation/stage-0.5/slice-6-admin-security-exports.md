# Stage 0.5 Slice 6: Admin Controls (Task Templates) + Security Audit Exports

## Scope
- Add task template lifecycle controls (versioning, archive flow, active-name uniqueness).
- Add security audit export lifecycle controls and owner/admin access gating.
- Add SQL helpers for export request/start/complete/fail paths.
- Add contract tests and rollback-tested runner.

## Contract-change note
- No shared enums/events/API contracts were changed in this slice.
- This slice implements admin/security operational controls on existing Stage 0.5 data paths.

## Delivered artifacts
- Migration up: `db/migrations/000015_stage0_5_admin_security_exports.up.sql`
- Migration down: `db/migrations/000015_stage0_5_admin_security_exports.down.sql`
- SQL tests: `db/tests/006_stage0_5_admin_security_exports.sql`
- Runner: `scripts/db/test_slice6_stage0_5.sh`

## Operational behavior implemented
- Task templates:
  - version increment on updates
  - archive path toggles `is_active=false` and stores actor/timestamp
  - active template-name uniqueness per org (`lower(name)`)
- Security audit exports:
  - strict status lifecycle values
  - export type allowlist
  - owner/admin-only request gate via org-level membership role
  - running/completed/failed transition helpers

## Rollout plan
1. Apply Stage 0 and Stage 0.5 Slice 1-5 migrations.
2. Apply `000015_stage0_5_admin_security_exports.up.sql`.
3. Run `scripts/db/test_slice6_stage0_5.sh` in CI/staging.
4. Enable admin/support service paths behind feature flags.

## Rollback plan
1. Disable task-template mutation and audit-export lifecycle write paths.
2. Apply `000015_stage0_5_admin_security_exports.down.sql`.
3. Keep prior Stage 0.5 schema in place unless full rollback required.

## Rollback risk notes
- Rollback removes owner/admin export gate helper and template lifecycle helpers.
- Existing template and export rows remain, but lifecycle guards and transitions become unenforced.
