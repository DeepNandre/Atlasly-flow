import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class Stage3Slice1ContractTests(unittest.TestCase):
    def test_event_envelope_required_fields(self):
        envelope_path = ROOT / "contracts/stage3/event-envelope-v1.json"
        self.assertTrue(envelope_path.exists(), f"missing {envelope_path}")
        envelope = json.loads(envelope_path.read_text())

        required = set(envelope.get("required", []))
        expected = {
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
        self.assertTrue(expected.issubset(required))

    def test_canonical_stage3_events_present(self):
        events_dir = ROOT / "contracts/stage3/events"
        self.assertTrue(events_dir.exists(), f"missing {events_dir}")

        expected_events = {
            "permit.preflight_scored.v1.json": "permit.preflight_scored",
            "permit.recommendations_generated.v1.json": "permit.recommendations_generated",
            "milestone.verified.v1.json": "milestone.verified",
            "payout.instruction_created.v1.json": "payout.instruction_created",
        }

        for filename, event_name in expected_events.items():
            path = events_dir / filename
            self.assertTrue(path.exists(), f"missing {path}")
            event_contract = json.loads(path.read_text())
            self.assertEqual(event_contract["event_type"], event_name)
            self.assertEqual(event_contract["event_version"], 1)
            self.assertIn("required_payload_fields", event_contract)
            self.assertGreater(len(event_contract["required_payload_fields"]), 0)

    def test_preflight_api_contract_exists(self):
        api_path = ROOT / "contracts/stage3/apis/get-project-preflight-risk.md"
        self.assertTrue(api_path.exists(), f"missing {api_path}")
        body = api_path.read_text()
        self.assertIn("permit_type", body)
        self.assertIn("ahj_id", body)
        self.assertIn("include_recommendations", body)

    def test_migration_has_required_tables_indexes_and_permit_fields(self):
        migration_path = ROOT / "db/migrations/000032_stage3_foundations.sql"
        self.assertTrue(migration_path.exists(), f"missing {migration_path}")
        migration = migration_path.read_text()

        required_tables = [
            "ahj_behavior_features",
            "preflight_risk_scores",
            "recommendation_runs",
            "milestones",
            "payout_instructions",
            "financial_events",
            "reconciliation_runs",
        ]
        for table in required_tables:
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", migration)

        required_indexes = [
            "idx_ahj_behavior_features_ahj_permit_updated",
            "idx_milestones_org_state_due",
            "idx_financial_events_org_event_occurred",
        ]
        for index_name in required_indexes:
            self.assertIn(index_name, migration)

        self.assertIn("ADD COLUMN IF NOT EXISTS risk_score", migration)
        self.assertIn("ADD COLUMN IF NOT EXISTS risk_band", migration)
        self.assertIn("ADD COLUMN IF NOT EXISTS last_recommendation_at", migration)

    def test_rollback_script_exists(self):
        rollback_path = (
            ROOT
            / "db/migrations/rollback/000032_stage3_foundations_rollback.sql"
        )
        self.assertTrue(rollback_path.exists(), f"missing {rollback_path}")
        rollback = rollback_path.read_text()
        self.assertIn("DROP TABLE IF EXISTS reconciliation_runs", rollback)
        self.assertIn("DROP COLUMN IF EXISTS risk_score", rollback)


if __name__ == "__main__":
    unittest.main()
