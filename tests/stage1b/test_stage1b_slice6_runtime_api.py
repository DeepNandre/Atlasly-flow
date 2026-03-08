from datetime import datetime, timedelta, timezone
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.stage1b.notification_policy import NotificationStore
from scripts.stage1b.runtime_api import post_create_tasks
from scripts.stage1b.runtime_api import post_reassign_task
from scripts.stage1b.runtime_api import run_assignment_overdue_worker
from scripts.stage1b.ticketing_service import AuthContext
from scripts.stage1b.ticketing_service import TicketingStore


class Stage1BSlice6RuntimeApiTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 3, 3, 18, 0, tzinfo=timezone.utc)
        self.org_id = "3550f393-cf47-46e9-b146-19d6fbe7e910"
        self.project_id = "7a6dc13a-34a6-4fce-9f01-8d97f36d3d35"
        self.letter_id = "0e2dd18d-76e4-4bfd-aad1-9e3078e7e6bb"
        self.extract_struct = "05f315d5-1d16-4464-a855-cb4fdb8fa7e7"
        self.extract_elec = "56ddbfcc-f6a8-42f1-8c9c-57b1402b7182"
        self.struct_assignee = "8ac5d9a8-c20f-4de3-a25e-84bb22a42544"

        self.ticket_store = TicketingStore.empty()
        self.notification_store = NotificationStore.empty()
        self.ticket_store.letters_by_id[self.letter_id] = {
            "id": self.letter_id,
            "organization_id": self.org_id,
            "project_id": self.project_id,
            "version_hash": "letter-v3-hash",
            "approved_at": self.now.isoformat(),
        }
        self.ticket_store.extractions_by_id[self.extract_struct] = {
            "id": self.extract_struct,
            "letter_id": self.letter_id,
            "comment_id": "c-1",
            "status": "approved_snapshot",
            "discipline": "structural",
        }
        self.ticket_store.extractions_by_id[self.extract_elec] = {
            "id": self.extract_elec,
            "letter_id": self.letter_id,
            "comment_id": "c-2",
            "status": "approved_snapshot",
            "discipline": "electrical",
        }
        self.ticket_store.routing_rules_by_id["rule-structural"] = {
            "id": "rule-structural",
            "organization_id": self.org_id,
            "project_id": self.project_id,
            "is_active": True,
            "priority": 1,
            "discipline": "structural",
            "assignee_user_id": self.struct_assignee,
            "confidence_base": 0.8,
            "created_at": "2026-03-01T10:00:00+00:00",
        }

        self.auth_pm = AuthContext(
            organization_id=self.org_id,
            user_id="19a6140e-46de-42dd-839d-b7b4f3df8a0f",
            requester_role="pm",
        )

    def test_post_create_tasks_success_and_replay(self):
        headers = {"Idempotency-Key": "runtime-idem-1", "X-Trace-Id": "trace-runtime-1"}
        status1, payload1 = post_create_tasks(
            letter_id=self.letter_id,
            request_body={"approved_extraction_ids": [self.extract_struct], "dry_run": False},
            headers=headers,
            auth_context=self.auth_pm,
            ticket_store=self.ticket_store,
            notification_store=self.notification_store,
            confidence_threshold=0.75,
            escalation_policy={"id": "policy-1", "ack_minutes_l1": 60, "max_levels": 3},
            now=self.now,
        )
        status2, payload2 = post_create_tasks(
            letter_id=self.letter_id,
            request_body={"approved_extraction_ids": [self.extract_struct], "dry_run": False},
            headers=headers,
            auth_context=self.auth_pm,
            ticket_store=self.ticket_store,
            notification_store=self.notification_store,
            confidence_threshold=0.75,
            escalation_policy={"id": "policy-1", "ack_minutes_l1": 60, "max_levels": 3},
            now=self.now + timedelta(minutes=1),
        )

        self.assertEqual(status1, 201)
        self.assertEqual(status2, 200)
        self.assertEqual(payload1["task_ids"], payload2["task_ids"])
        task_id = payload1["task_ids"][0]
        task = self.ticket_store.tasks_by_id[task_id]
        self.assertEqual(task["routing_decision"], "assigned")
        self.assertEqual(task["routing_rule_id"], "rule-structural")
        self.assertGreaterEqual(float(task["routing_confidence"]), 0.75)

    def test_post_create_tasks_conflict_same_key_different_payload(self):
        headers = {"Idempotency-Key": "runtime-idem-conflict"}
        post_create_tasks(
            letter_id=self.letter_id,
            request_body={"approved_extraction_ids": [self.extract_struct], "dry_run": False},
            headers=headers,
            auth_context=self.auth_pm,
            ticket_store=self.ticket_store,
            notification_store=self.notification_store,
            confidence_threshold=0.75,
            escalation_policy={"id": "policy-1", "ack_minutes_l1": 60, "max_levels": 3},
            now=self.now,
        )
        status, payload = post_create_tasks(
            letter_id=self.letter_id,
            request_body={"approved_extraction_ids": [self.extract_elec], "dry_run": False},
            headers=headers,
            auth_context=self.auth_pm,
            ticket_store=self.ticket_store,
            notification_store=self.notification_store,
            confidence_threshold=0.75,
            escalation_policy={"id": "policy-1", "ack_minutes_l1": 60, "max_levels": 3},
            now=self.now + timedelta(minutes=1),
        )
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"]["code"], "idempotency_conflict")

    def test_post_reassign_task_error_surface(self):
        create_status, create_payload = post_create_tasks(
            letter_id=self.letter_id,
            request_body={"approved_extraction_ids": [self.extract_struct], "dry_run": False},
            headers={"Idempotency-Key": "runtime-idem-2"},
            auth_context=self.auth_pm,
            ticket_store=self.ticket_store,
            notification_store=self.notification_store,
            confidence_threshold=0.75,
            escalation_policy={"id": "policy-1", "ack_minutes_l1": 60, "max_levels": 3},
            now=self.now,
        )
        self.assertEqual(create_status, 201)
        task_id = create_payload["task_ids"][0]
        self.ticket_store.tasks_by_id[task_id]["assignee_user_id"] = self.struct_assignee

        status, payload = post_reassign_task(
            task_id=task_id,
            request_body={
                "from_assignee_id": self.struct_assignee,
                "to_assignee_id": self.struct_assignee,
                "feedback_reason_code": "WRONG_DISCIPLINE",
            },
            headers={"X-Trace-Id": "trace-reassign"},
            auth_context=self.auth_pm,
            ticket_store=self.ticket_store,
            now=self.now,
        )
        self.assertEqual(status, 422)
        self.assertEqual(payload["error"]["code"], "validation_error")

    def test_run_assignment_overdue_worker(self):
        status, payload = post_create_tasks(
            letter_id=self.letter_id,
            request_body={"approved_extraction_ids": [self.extract_struct], "dry_run": False},
            headers={"Idempotency-Key": "runtime-idem-3"},
            auth_context=self.auth_pm,
            ticket_store=self.ticket_store,
            notification_store=self.notification_store,
            confidence_threshold=0.75,
            escalation_policy={"id": "policy-1", "ack_minutes_l1": 1, "max_levels": 3},
            now=self.now,
        )
        self.assertEqual(status, 201)
        self.assertEqual(payload["escalation_started_count"], 1)

        summary = run_assignment_overdue_worker(
            ticket_store=self.ticket_store,
            notification_store=self.notification_store,
            user_mode="immediate",
            now=self.now + timedelta(minutes=5),
        )
        self.assertGreaterEqual(summary["processed_events"], 1)
        self.assertGreaterEqual(summary["notifications_sent"], 1)

    def test_run_assignment_overdue_worker_tick_is_replay_safe(self):
        status, payload = post_create_tasks(
            letter_id=self.letter_id,
            request_body={"approved_extraction_ids": [self.extract_struct], "dry_run": False},
            headers={"Idempotency-Key": "runtime-idem-4"},
            auth_context=self.auth_pm,
            ticket_store=self.ticket_store,
            notification_store=self.notification_store,
            confidence_threshold=0.75,
            escalation_policy={"id": "policy-1", "ack_minutes_l1": 1, "max_levels": 3},
            now=self.now,
        )
        self.assertEqual(status, 201)
        self.assertEqual(payload["escalation_started_count"], 1)

        tick = "tick-2026-03-03T18:05"
        first = run_assignment_overdue_worker(
            ticket_store=self.ticket_store,
            notification_store=self.notification_store,
            user_mode="immediate",
            tick_key=tick,
            now=self.now + timedelta(minutes=5),
        )
        replay = run_assignment_overdue_worker(
            ticket_store=self.ticket_store,
            notification_store=self.notification_store,
            user_mode="immediate",
            tick_key=tick,
            now=self.now + timedelta(minutes=6),
        )
        self.assertIn("tick_key", first)
        self.assertEqual(first["tick_key"], tick)
        self.assertTrue(replay["replayed"])


if __name__ == "__main__":
    unittest.main()
