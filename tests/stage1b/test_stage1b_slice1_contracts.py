import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class Stage1BSlice1ContractTests(unittest.TestCase):
    def test_event_envelope_required_fields(self):
        envelope_path = ROOT / "contracts/stage1b/event-envelope-v1.json"
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

    def test_canonical_stage1b_events_present_and_locked(self):
        events_dir = ROOT / "contracts/stage1b/events"
        self.assertTrue(events_dir.exists(), f"missing {events_dir}")

        expected_events = {
            "tasks.bulk_created_from_extractions.v1.json": (
                "tasks.bulk_created_from_extractions",
                "comment_letter",
            ),
            "task.auto_assigned.v1.json": ("task.auto_assigned", "task"),
            "task.assignment_overdue.v1.json": ("task.assignment_overdue", "task"),
        }

        for filename, (event_name, aggregate_type) in expected_events.items():
            path = events_dir / filename
            self.assertTrue(path.exists(), f"missing {path}")
            event_contract = json.loads(path.read_text())
            self.assertEqual(event_contract["event_type"], event_name)
            self.assertEqual(event_contract["event_version"], 1)
            self.assertEqual(event_contract["aggregate_type"], aggregate_type)
            self.assertIn("required_payload_fields", event_contract)
            self.assertGreater(len(event_contract["required_payload_fields"]), 0)

    def test_migration_contains_core_idempotency_and_feedback_guards(self):
        migration_path = ROOT / "db/migrations/000022_stage1b_ticketing_routing.sql"
        self.assertTrue(migration_path.exists(), f"missing {migration_path}")
        body = migration_path.read_text()

        for required_table in [
            "routing_rules",
            "task_assignment_feedback",
            "assignment_escalations",
            "task_generation_runs",
            "routing_sla_policies",
        ]:
            self.assertIn(f"create table if not exists {required_table}", body.lower())

        self.assertIn("ux_tasks_org_source_extraction", body)
        self.assertIn("stage1b_enforce_task_source_extraction", body)
        self.assertIn("idx_domain_events_stage1b_pending", body)

    def test_rollback_script_exists(self):
        rollback_path = (
            ROOT
            / "db/migrations/rollback/000022_stage1b_ticketing_routing.rollback.sql"
        )
        self.assertTrue(rollback_path.exists(), f"missing {rollback_path}")
        rollback = rollback_path.read_text().lower()
        self.assertIn("drop table if exists task_generation_runs", rollback)
        self.assertIn("drop table if exists task_assignment_feedback", rollback)
        self.assertIn("drop index if exists ux_tasks_org_source_extraction", rollback)


if __name__ == "__main__":
    unittest.main()
