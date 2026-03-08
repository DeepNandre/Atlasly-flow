import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class Stage2Slice2ContractTests(unittest.TestCase):
    def test_stage2_migration_has_required_tables(self):
        migration_path = (
            ROOT / "db/migrations/000024_stage2_requirements_mappings_connectors.sql"
        )
        self.assertTrue(migration_path.exists(), f"missing {migration_path}")
        migration = migration_path.read_text()

        self.assertIn("create table if not exists ahj_requirements", migration.lower())
        self.assertIn("create table if not exists application_field_mappings", migration.lower())
        self.assertIn("create table if not exists connector_credentials", migration.lower())

    def test_stage2_migration_has_required_indexes_and_constraints(self):
        migration_path = (
            ROOT / "db/migrations/000024_stage2_requirements_mappings_connectors.sql"
        )
        migration = migration_path.read_text()

        required_tokens = [
            "uq_ahj_requirements_ahj_permit_version",
            "uq_ahj_requirements_single_active",
            "idx_app_field_mappings_template_lookup",
            "uq_app_field_mapping_unique_target",
            "idx_connector_credentials_org_connector",
            "check (connector in ('accela_api', 'opengov_api', 'cloudpermit_portal_runner'))",
        ]
        for token in required_tokens:
            self.assertIn(token, migration)

    def test_stage2_event_schema_exists_and_is_v1(self):
        schema_path = ROOT / "contracts/stage2/permit.application_generated.v1.schema.json"
        self.assertTrue(schema_path.exists(), f"missing {schema_path}")

        schema = json.loads(schema_path.read_text())
        self.assertEqual(schema["properties"]["event_type"]["const"], "permit.application_generated")
        self.assertEqual(schema["properties"]["event_version"]["const"], 1)

        required_fields = set(schema.get("required", []))
        expected_envelope_fields = {
            "event_id",
            "event_type",
            "event_version",
            "organization_id",
            "aggregate_type",
            "aggregate_id",
            "occurred_at",
            "produced_by",
            "idempotency_key",
            "trace_id",
            "payload",
        }
        self.assertTrue(expected_envelope_fields.issubset(required_fields))

    def test_stage2_rollback_exists(self):
        rollback_path = (
            ROOT
            / "db/migrations/rollback/000024_stage2_requirements_mappings_connectors_rollback.sql"
        )
        self.assertTrue(rollback_path.exists(), f"missing {rollback_path}")
        rollback = rollback_path.read_text().lower()
        self.assertIn("drop table if exists connector_credentials", rollback)
        self.assertIn("drop table if exists application_field_mappings", rollback)
        self.assertIn("drop table if exists ahj_requirements", rollback)


if __name__ == "__main__":
    unittest.main()
