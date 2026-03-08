import json
import pathlib
import sys
import unittest
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.stage1b.notification_policy import NotificationStore
from scripts.stage1b.runtime_api import post_create_tasks
from scripts.stage1b.runtime_api import run_assignment_overdue_worker
from scripts.stage1b.ticketing_service import AuthContext
from scripts.stage1b.ticketing_service import TicketingStore


class Stage1BSlice8EventEnvelopeComplianceTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 3, 3, 21, 0, tzinfo=timezone.utc)
        self.org_id = "3550f393-cf47-46e9-b146-19d6fbe7e910"
        self.project_id = "7a6dc13a-34a6-4fce-9f01-8d97f36d3d35"
        self.letter_id = "0e2dd18d-76e4-4bfd-aad1-9e3078e7e6bb"
        self.extract_id = "05f315d5-1d16-4464-a855-cb4fdb8fa7e7"
        self.assignee = "8ac5d9a8-c20f-4de3-a25e-84bb22a42544"

        self.ticket_store = TicketingStore.empty()
        self.notification_store = NotificationStore.empty()
        self.ticket_store.letters_by_id[self.letter_id] = {
            "id": self.letter_id,
            "organization_id": self.org_id,
            "project_id": self.project_id,
            "version_hash": "letter-v3-hash",
            "approved_at": self.now.isoformat(),
        }
        self.ticket_store.extractions_by_id[self.extract_id] = {
            "id": self.extract_id,
            "letter_id": self.letter_id,
            "comment_id": "c-1",
            "status": "approved_snapshot",
            "discipline": "structural",
        }
        self.ticket_store.routing_rules_by_id["rule-1"] = {
            "id": "rule-1",
            "organization_id": self.org_id,
            "project_id": self.project_id,
            "is_active": True,
            "priority": 1,
            "discipline": "structural",
            "assignee_user_id": self.assignee,
            "confidence_base": 0.8,
            "created_at": "2026-03-01T10:00:00+00:00",
        }

        self.auth = AuthContext(
            organization_id=self.org_id,
            user_id="19a6140e-46de-42dd-839d-b7b4f3df8a0f",
            requester_role="pm",
        )

    def test_emitted_events_match_envelope_and_payload_contracts(self):
        envelope = json.loads((ROOT / "contracts/stage1b/event-envelope-v1.json").read_text())
        required_envelope = set(envelope["required"])

        event_contract_files = [
            ROOT / "contracts/stage1b/events/tasks.bulk_created_from_extractions.v1.json",
            ROOT / "contracts/stage1b/events/task.auto_assigned.v1.json",
            ROOT / "contracts/stage1b/events/task.assignment_overdue.v1.json",
        ]
        expected_contracts = {}
        for path in event_contract_files:
            contract = json.loads(path.read_text())
            expected_contracts[contract["event_type"]] = set(contract["required_payload_fields"])

        status, _ = post_create_tasks(
            letter_id=self.letter_id,
            request_body={"approved_extraction_ids": [self.extract_id], "dry_run": False},
            headers={"Idempotency-Key": "env-001", "X-Trace-Id": "trace-env-1"},
            auth_context=self.auth,
            ticket_store=self.ticket_store,
            notification_store=self.notification_store,
            confidence_threshold=0.75,
            escalation_policy={"id": "policy-1", "ack_minutes_l1": 1, "max_levels": 3},
            now=self.now,
        )
        self.assertEqual(status, 201)
        run_assignment_overdue_worker(
            ticket_store=self.ticket_store,
            notification_store=self.notification_store,
            user_mode="immediate",
            now=self.now + timedelta(minutes=5),
        )

        self.assertGreaterEqual(len(self.ticket_store.outbox_events), 3)
        for event in self.ticket_store.outbox_events:
            self.assertTrue(required_envelope.issubset(set(event.keys())))
            self.assertEqual(event["event_version"], 1)
            self.assertIn(event["event_type"], expected_contracts)

            required_payload = expected_contracts[event["event_type"]]
            payload_keys = set(event.get("payload", {}).keys())
            self.assertTrue(required_payload.issubset(payload_keys))


if __name__ == "__main__":
    unittest.main()
