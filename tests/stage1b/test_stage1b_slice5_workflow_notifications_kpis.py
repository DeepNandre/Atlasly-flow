from datetime import datetime, timedelta, timezone
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.stage1b.notification_policy import NotificationStore
from scripts.stage1b.notification_policy import process_notification_event
from scripts.stage1b.ticketing_service import AuthContext
from scripts.stage1b.ticketing_service import TicketingStore
from scripts.stage1b.workflow_orchestrator import run_stage1b_workflow


class Stage1BSlice5WorkflowNotificationsKpiTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 3, 3, 17, 0, tzinfo=timezone.utc)
        self.org_id = "3550f393-cf47-46e9-b146-19d6fbe7e910"
        self.project_id = "7a6dc13a-34a6-4fce-9f01-8d97f36d3d35"
        self.letter_id = "0e2dd18d-76e4-4bfd-aad1-9e3078e7e6bb"
        self.extract_struct = "05f315d5-1d16-4464-a855-cb4fdb8fa7e7"
        self.extract_elec = "56ddbfcc-f6a8-42f1-8c9c-57b1402b7182"
        self.owner_id = "19a6140e-46de-42dd-839d-b7b4f3df8a0f"
        self.struct_assignee = "8ac5d9a8-c20f-4de3-a25e-84bb22a42544"

        self.store = TicketingStore.empty()
        self.notifications = NotificationStore.empty()
        self.store.letters_by_id[self.letter_id] = {
            "id": self.letter_id,
            "organization_id": self.org_id,
            "project_id": self.project_id,
            "version_hash": "letter-v3-hash",
            "approved_at": self.now.isoformat(),
        }
        self.store.extractions_by_id[self.extract_struct] = {
            "id": self.extract_struct,
            "letter_id": self.letter_id,
            "comment_id": "c-1",
            "status": "approved_snapshot",
            "discipline": "structural",
        }
        self.store.extractions_by_id[self.extract_elec] = {
            "id": self.extract_elec,
            "letter_id": self.letter_id,
            "comment_id": "c-2",
            "status": "approved_snapshot",
            "discipline": "electrical",
        }
        self.store.routing_rules_by_id["rule-structural"] = {
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

        self.auth = AuthContext(
            organization_id=self.org_id,
            user_id=self.owner_id,
            requester_role="pm",
        )
        self.escalation_policy = {
            "id": "de4e3df8-fb41-4195-8005-fc4a64f90f46",
            "ack_minutes_l1": 120,
            "max_levels": 3,
        }

    def test_end_to_end_mixed_outcome_and_kpi_snapshot(self):
        result = run_stage1b_workflow(
            letter_id=self.letter_id,
            request_body={"approved_extraction_ids": [self.extract_struct, self.extract_elec], "dry_run": False},
            idempotency_key="wf-001",
            trace_id="trace-wf-001",
            auth_context=self.auth,
            ticket_store=self.store,
            notification_store=self.notifications,
            user_mode="immediate",
            confidence_threshold=0.75,
            escalation_policy=self.escalation_policy,
            now=self.now,
        )

        self.assertEqual(result.create_status, 201)
        self.assertEqual(result.created_count, 2)
        self.assertEqual(result.auto_assigned_count, 1)
        self.assertEqual(result.manual_queue_count, 1)
        self.assertEqual(result.escalation_started_count, 1)

        self.assertEqual(len(self.store.manual_queue_by_task_id), 1)
        self.assertEqual(len(self.notifications.sent_notifications), 1)
        self.assertEqual(len(self.notifications.queued_digest_items), 1)

        routing_quality = result.kpi_snapshot["routing_quality"]
        self.assertEqual(routing_quality["auto_assigned_total"], 1)
        self.assertEqual(routing_quality["manual_override_count"], 0)

        operability = result.kpi_snapshot["operability"]
        self.assertEqual(operability["generation_request_count"], 1)
        self.assertEqual(operability["generation_replay_count"], 0)

    def test_replay_updates_operability_replay_ratio(self):
        run_stage1b_workflow(
            letter_id=self.letter_id,
            request_body={"approved_extraction_ids": [self.extract_struct], "dry_run": False},
            idempotency_key="wf-replay",
            trace_id="trace-wf-002",
            auth_context=self.auth,
            ticket_store=self.store,
            notification_store=self.notifications,
            user_mode="immediate",
            confidence_threshold=0.75,
            escalation_policy=self.escalation_policy,
            now=self.now,
        )
        second = run_stage1b_workflow(
            letter_id=self.letter_id,
            request_body={"approved_extraction_ids": [self.extract_struct], "dry_run": False},
            idempotency_key="wf-replay",
            trace_id="trace-wf-003",
            auth_context=self.auth,
            ticket_store=self.store,
            notification_store=self.notifications,
            user_mode="immediate",
            confidence_threshold=0.75,
            escalation_policy=self.escalation_policy,
            now=self.now + timedelta(minutes=1),
        )
        self.assertEqual(second.create_status, 200)
        self.assertGreater(second.kpi_snapshot["operability"]["generation_replay_ratio"], 0.0)

    def test_immediate_notification_suppression_window(self):
        event = {
            "event_id": "evt-1",
            "event_type": "task.assignment_overdue",
            "aggregate_id": "task-1",
            "payload": {"task_id": "task-1", "escalation_level": 2},
        }
        first = process_notification_event(
            event=event,
            user_id=self.owner_id,
            user_mode="immediate",
            notification_store=self.notifications,
            now=self.now,
        )
        second = process_notification_event(
            event=event,
            user_id=self.owner_id,
            user_mode="immediate",
            notification_store=self.notifications,
            now=self.now + timedelta(minutes=10),
        )
        third = process_notification_event(
            event=event,
            user_id=self.owner_id,
            user_mode="immediate",
            notification_store=self.notifications,
            now=self.now + timedelta(minutes=31),
        )
        self.assertEqual(first, "sent_immediate")
        self.assertEqual(second, "suppressed")
        self.assertEqual(third, "sent_immediate")


if __name__ == "__main__":
    unittest.main()
