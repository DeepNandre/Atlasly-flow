# Migration Index (Canonical Global Order)

This index defines the globally deterministic migration order for this repository.

## Forward Migrations
1. `000001_stage0_enable_extensions.up.sql`
2. `000002_stage0_create_types.up.sql`
3. `000003_stage0_identity_and_tenancy.up.sql`
4. `000004_stage0_core_domain.up.sql`
5. `000005_stage0_documents_and_versions.up.sql`
6. `000006_stage0_audit_and_domain_events.up.sql`
7. `000007_stage0_notifications.up.sql`
8. `000008_stage0_rls_policies.up.sql`
9. `000009_stage0_future_moat_tables.up.sql`
10. `000010_stage0_5_enterprise_readiness.up.sql`
11. `000011_stage0_5_webhook_control_plane.up.sql`
12. `000012_stage0_5_webhook_delivery_runtime.up.sql`
13. `000013_stage0_5_connector_runtime.up.sql`
14. `000014_stage0_5_dashboard_api_credentials.up.sql`
15. `000015_stage0_5_admin_security_exports.up.sql`
16. `000016_stage1a_comment_extraction.sql`
17. `000017_stage1a_state_and_event_guards.sql`
18. `000018_stage1a_event_emit_function.sql`
19. `000019_stage1a_approval_workflow.sql`
20. `000020_stage1a_read_models.sql`
21. `000021_stage1a_pipeline_entrypoints.sql`
22. `000022_stage1b_ticketing_routing.sql`
23. `000023_stage2_intake_foundations.sql`
24. `000024_stage2_requirements_mappings_connectors.sql`
25. `000025_stage2_status_sync_foundations.sql`
26. `000026_stage2_sync_ops_controls.sql`
27. `000027_stage2_normalization_and_drift_rules.sql`
28. `000028_stage2_status_projection_cache.sql`
29. `000029_stage2_application_generation_runs.sql`
30. `000030_stage2_connector_poll_attempts.sql`
31. `000031_stage2_event_outbox.sql`
32. `000032_stage3_foundations.sql`
33. `000033_stage3_persistence_scaffolding.sql`

## Down/Rollback Pairing
- Stage 0 and Stage 0.5 down files are paired by identical numeric prefix (`.down.sql`).
- Stage 1A/1B/2/3 rollback scripts in `db/migrations/rollback/` share the same numeric prefix as their forward migration.
