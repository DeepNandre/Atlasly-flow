from datetime import datetime, timedelta, timezone
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.stage1b.routing_engine import auto_assign_task
from scripts.stage1b.routing_engine import create_escalation
from scripts.stage1b.routing_engine import process_overdue_assignments
from scripts.stage1b.ticketing_service import TicketingStore


class Stage1BSlice4RoutingSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 3, 3, 16, 0, tzinfo=timezone.utc)
        self.org_id = "3550f393-cf47-46e9-b146-19d6fbe7e910"
        self.project_id = "7a6dc13a-34a6-4fce-9f01-8d97f36d3d35"
        self.task_id = "99f5e869-b69c-4e88-92f1-05ed91e98570"
        self.user_a = "8ac5d9a8-c20f-4de3-a25e-84bb22a42544"
        self.user_b = "31afdf4d-ce72-4b7f-99a7-3e8dc0f8ea2b"

        self.store = TicketingStore.empty()
        self.store.tasks_by_id[self.task_id] = {
            "id": self.task_id,
            "organization_id": self.org_id,
            "project_id": self.project_id,
            "discipline": "structural",
            "trade_partner_id": "2fc76eb4-1240-4ea1-a3e2-63c52f6db031",
            "project_role": "pm",
            "ahj_id": "ca.san_jose.building",
            "status": "todo",
            "assignee_user_id": None,
            "auto_assigned": False,
            "assignment_confidence": None,
            "created_at": self.now.isoformat(),
            "updated_at": self.now.isoformat(),
        }

    def test_deterministic_project_scope_precedence(self):
        self.store.routing_rules_by_id["org-default"] = {
            "id": "org-default",
            "organization_id": self.org_id,
            "project_id": None,
            "is_active": True,
            "priority": 1,
            "discipline": "structural",
            "assignee_user_id": self.user_a,
            "confidence_base": 0.8,
            "created_at": "2026-03-01T10:00:00+00:00",
        }
        self.store.routing_rules_by_id["project-specific"] = {
            "id": "project-specific",
            "organization_id": self.org_id,
            "project_id": self.project_id,
            "is_active": True,
            "priority": 10,
            "discipline": "structural",
            "assignee_user_id": self.user_b,
            "confidence_base": 0.8,
            "created_at": "2026-03-01T11:00:00+00:00",
        }

        result = auto_assign_task(
            task_id=self.task_id,
            trace_id="trace-routing-1",
            store=self.store,
            confidence_threshold=0.7,
            now=self.now,
        )
        self.assertEqual(result["status"], "ASSIGNED")
        self.assertEqual(result["assignee_id"], self.user_b)
        self.assertEqual(self.store.tasks_by_id[self.task_id]["assignee_user_id"], self.user_b)
        self.assertEqual(self.store.outbox_events[-1]["event_type"], "task.auto_assigned")

    def test_low_confidence_falls_back_to_manual_queue(self):
        self.store.routing_rules_by_id["low-confidence"] = {
            "id": "low-confidence",
            "organization_id": self.org_id,
            "project_id": self.project_id,
            "is_active": True,
            "priority": 1,
            "discipline": "structural",
            "assignee_user_id": self.user_a,
            "confidence_base": 0.5,
            "created_at": "2026-03-01T10:00:00+00:00",
        }

        result = auto_assign_task(
            task_id=self.task_id,
            trace_id="trace-routing-2",
            store=self.store,
            confidence_threshold=0.9,
            now=self.now,
        )
        self.assertEqual(result["status"], "MANUAL_QUEUE")
        self.assertEqual(result["reason"], "LOW_CONFIDENCE")
        self.assertIsNone(self.store.tasks_by_id[self.task_id]["assignee_user_id"])
        self.assertEqual(len(self.store.outbox_events), 0)

    def test_overdue_escalation_emits_and_suppresses_duplicates(self):
        self.store.tasks_by_id[self.task_id]["assignee_user_id"] = self.user_a
        policy = {
            "id": "de4e3df8-fb41-4195-8005-fc4a64f90f46",
            "ack_minutes_l1": 60,
            "max_levels": 3,
        }
        create_escalation(task_id=self.task_id, policy=policy, store=self.store, now=self.now - timedelta(hours=2))

        emitted_first = process_overdue_assignments(
            trace_id="trace-escalation-1",
            store=self.store,
            now=self.now,
        )
        self.assertEqual(len(emitted_first), 1)
        self.assertEqual(emitted_first[0]["event_type"], "task.assignment_overdue")
        self.assertEqual(emitted_first[0]["payload"]["escalation_level"], 2)

        emitted_second = process_overdue_assignments(
            trace_id="trace-escalation-2",
            store=self.store,
            now=self.now + timedelta(minutes=10),
        )
        self.assertEqual(len(emitted_second), 0)

        # Past suppression window and overdue again.
        self.store.assignment_escalations_by_task_id[self.task_id]["next_escalation_at"] = self.now + timedelta(minutes=31)
        emitted_third = process_overdue_assignments(
            trace_id="trace-escalation-3",
            store=self.store,
            now=self.now + timedelta(minutes=31),
        )
        self.assertEqual(len(emitted_third), 1)
        self.assertEqual(emitted_third[0]["payload"]["escalation_level"], 3)


if __name__ == "__main__":
    unittest.main()
