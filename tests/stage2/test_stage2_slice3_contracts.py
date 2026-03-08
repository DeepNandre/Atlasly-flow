import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class Stage2Slice3ContractTests(unittest.TestCase):
    def test_stage2_slice3_migration_tables_and_indexes(self):
        migration_path = ROOT / "db/migrations/000025_stage2_status_sync_foundations.sql"
        self.assertTrue(migration_path.exists(), f"missing {migration_path}")
        migration = migration_path.read_text()
        lower = migration.lower()

        self.assertIn("create table if not exists portal_sync_runs", lower)
        self.assertIn("create table if not exists permit_status_events", lower)
        self.assertIn("create table if not exists status_source_provenance", lower)

        required_tokens = [
            "idx_portal_sync_runs_connector_org_started",
            "idx_permit_status_events_permit_observed",
            "idx_status_source_provenance_event_ingested",
            "uq_permit_status_events_org_hash",
        ]
        for token in required_tokens:
            self.assertIn(token, migration)

    def test_status_observed_event_schema_exists_and_v1(self):
        schema_path = ROOT / "contracts/stage2/permit.status_observed.v1.schema.json"
        self.assertTrue(schema_path.exists(), f"missing {schema_path}")
        schema = json.loads(schema_path.read_text())

        self.assertEqual(schema["properties"]["event_type"]["const"], "permit.status_observed")
        self.assertEqual(schema["properties"]["event_version"]["const"], 1)

        payload_required = set(schema["properties"]["payload"]["required"])
        self.assertTrue(
            {
                "permit_id",
                "raw_status",
                "normalized_status",
                "source",
                "confidence",
                "observed_at",
            }.issubset(payload_required)
        )

    def test_status_timeline_openapi_contract_exists(self):
        api_path = ROOT / "contracts/stage2/status-timeline.v1.openapi.yaml"
        self.assertTrue(api_path.exists(), f"missing {api_path}")
        body = api_path.read_text()
        self.assertIn("/permits/{permitId}/status-timeline", body)
        self.assertIn("normalized_status", body)
        self.assertIn("provenance", body)

    def test_stage2_slice3_rollback_exists(self):
        rollback_path = (
            ROOT
            / "db/migrations/rollback/000025_stage2_status_sync_foundations_rollback.sql"
        )
        self.assertTrue(rollback_path.exists(), f"missing {rollback_path}")
        rollback = rollback_path.read_text().lower()
        self.assertIn("drop table if exists status_source_provenance", rollback)
        self.assertIn("drop table if exists permit_status_events", rollback)
        self.assertIn("drop table if exists portal_sync_runs", rollback)


if __name__ == "__main__":
    unittest.main()
