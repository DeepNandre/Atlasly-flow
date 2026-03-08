import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class Stage2Slice4ContractTests(unittest.TestCase):
    def test_stage2_slice4_migration_structures_present(self):
        migration_path = ROOT / "db/migrations/000026_stage2_sync_ops_controls.sql"
        self.assertTrue(migration_path.exists(), f"missing {migration_path}")
        migration = migration_path.read_text()
        lower = migration.lower()

        self.assertIn("create table if not exists status_reconciliation_runs", lower)
        self.assertIn("create table if not exists status_transition_reviews", lower)
        self.assertIn("idx_status_recon_runs_org_started", migration)
        self.assertIn("uq_status_transition_reviews_event_once", migration)

    def test_stage2_slice4_migration_has_invalid_transition_controls(self):
        migration_path = ROOT / "db/migrations/000026_stage2_sync_ops_controls.sql"
        migration = migration_path.read_text()

        self.assertIn("check (from_status in ('submitted', 'in_review', 'corrections_required', 'approved', 'issued', 'expired'))", migration)
        self.assertIn("check (to_status in ('submitted', 'in_review', 'corrections_required', 'approved', 'issued', 'expired'))", migration)
        self.assertIn("check (resolution_state in ('open', 'accepted_override', 'dismissed'))", migration)

    def test_connector_poll_api_contract_exists(self):
        api_path = ROOT / "contracts/stage2/connectors-poll.v1.openapi.yaml"
        self.assertTrue(api_path.exists(), f"missing {api_path}")
        body = api_path.read_text()
        self.assertIn("/connectors/{ahj}/poll", body)
        self.assertIn("Idempotency-Key", body)
        self.assertIn("accela_api", body)
        self.assertIn("opengov_api", body)
        self.assertIn("cloudpermit_portal_runner", body)

    def test_status_changed_event_schema_exists_and_v1(self):
        schema_path = ROOT / "contracts/stage2/permit.status_changed.v1.schema.json"
        self.assertTrue(schema_path.exists(), f"missing {schema_path}")
        schema = json.loads(schema_path.read_text())
        self.assertEqual(schema["properties"]["event_type"]["const"], "permit.status_changed")
        self.assertEqual(schema["properties"]["event_version"]["const"], 1)
        payload_required = set(schema["properties"]["payload"]["required"])
        self.assertTrue(
            {"permit_id", "old_status", "new_status", "source_event_id"}.issubset(payload_required)
        )

    def test_stage2_slice4_rollback_exists(self):
        rollback_path = (
            ROOT / "db/migrations/rollback/000026_stage2_sync_ops_controls_rollback.sql"
        )
        self.assertTrue(rollback_path.exists(), f"missing {rollback_path}")
        rollback = rollback_path.read_text().lower()
        self.assertIn("drop table if exists status_transition_reviews", rollback)
        self.assertIn("drop table if exists status_reconciliation_runs", rollback)


if __name__ == "__main__":
    unittest.main()
