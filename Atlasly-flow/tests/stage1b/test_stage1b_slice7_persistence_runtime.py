from datetime import datetime, timedelta, timezone
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.stage1b.runtime_service import Stage1BRuntimeService
from scripts.stage1b.sqlite_repository import Stage1BSQLiteRepository
from scripts.stage1b.ticketing_service import AuthContext


class Stage1BSlice7PersistenceRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 3, 3, 20, 0, tzinfo=timezone.utc)
        self.org_id = "3550f393-cf47-46e9-b146-19d6fbe7e910"
        self.project_id = "7a6dc13a-34a6-4fce-9f01-8d97f36d3d35"
        self.letter_id = "0e2dd18d-76e4-4bfd-aad1-9e3078e7e6bb"
        self.extract_struct = "05f315d5-1d16-4464-a855-cb4fdb8fa7e7"
        self.extract_elec = "56ddbfcc-f6a8-42f1-8c9c-57b1402b7182"
        self.struct_assignee = "8ac5d9a8-c20f-4de3-a25e-84bb22a42544"
        self.auth_pm = AuthContext(
            organization_id=self.org_id,
            user_id="19a6140e-46de-42dd-839d-b7b4f3df8a0f",
            requester_role="pm",
        )
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.repo = Stage1BSQLiteRepository(self.tmp.name)

        # Seed data once into repo state.
        store = self.repo.load_ticket_store()
        store.letters_by_id[self.letter_id] = {
            "id": self.letter_id,
            "organization_id": self.org_id,
            "project_id": self.project_id,
            "version_hash": "letter-v3-hash",
            "approved_at": self.now.isoformat(),
        }
        store.extractions_by_id[self.extract_struct] = {
            "id": self.extract_struct,
            "letter_id": self.letter_id,
            "comment_id": "c-1",
            "status": "approved_snapshot",
            "discipline": "structural",
        }
        store.extractions_by_id[self.extract_elec] = {
            "id": self.extract_elec,
            "letter_id": self.letter_id,
            "comment_id": "c-2",
            "status": "approved_snapshot",
            "discipline": "electrical",
        }
        store.routing_rules_by_id["rule-structural"] = {
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
        self.repo.save_ticket_store(store)

    def tearDown(self):
        self.repo.close()

    def test_idempotent_create_tasks_across_restart(self):
        svc1 = Stage1BRuntimeService(self.repo)
        status1, payload1 = svc1.post_create_tasks(
            letter_id=self.letter_id,
            request_body={"approved_extraction_ids": [self.extract_struct], "dry_run": False},
            headers={"Idempotency-Key": "restart-idem-1", "X-Trace-Id": "trace-r1"},
            auth_context=self.auth_pm,
            confidence_threshold=0.75,
            escalation_policy={"id": "policy-1", "ack_minutes_l1": 60, "max_levels": 3},
            now=self.now,
        )
        svc2 = Stage1BRuntimeService(self.repo)
        status2, payload2 = svc2.post_create_tasks(
            letter_id=self.letter_id,
            request_body={"approved_extraction_ids": [self.extract_struct], "dry_run": False},
            headers={"Idempotency-Key": "restart-idem-1", "X-Trace-Id": "trace-r2"},
            auth_context=self.auth_pm,
            confidence_threshold=0.75,
            escalation_policy={"id": "policy-1", "ack_minutes_l1": 60, "max_levels": 3},
            now=self.now + timedelta(minutes=1),
        )

        self.assertEqual(status1, 201)
        self.assertEqual(status2, 200)
        self.assertEqual(payload1["task_ids"], payload2["task_ids"])

        store = self.repo.load_ticket_store()
        self.assertEqual(len(store.tasks_by_id), 1)
        bulk_events = [e for e in store.outbox_events if e["event_type"] == "tasks.bulk_created_from_extractions"]
        self.assertEqual(len(bulk_events), 1)

    def test_replay_is_side_effect_free_for_manual_queue(self):
        svc1 = Stage1BRuntimeService(self.repo)
        status1, _ = svc1.post_create_tasks(
            letter_id=self.letter_id,
            request_body={"approved_extraction_ids": [self.extract_elec], "dry_run": False},
            headers={"Idempotency-Key": "restart-idem-2", "X-Trace-Id": "trace-r3"},
            auth_context=self.auth_pm,
            confidence_threshold=0.75,
            escalation_policy={"id": "policy-1", "ack_minutes_l1": 60, "max_levels": 3},
            now=self.now,
        )
        self.assertEqual(status1, 201)
        store_after_first = self.repo.load_ticket_store()
        first_manual_count = len(store_after_first.manual_queue_by_task_id)

        svc2 = Stage1BRuntimeService(self.repo)
        status2, _ = svc2.post_create_tasks(
            letter_id=self.letter_id,
            request_body={"approved_extraction_ids": [self.extract_elec], "dry_run": False},
            headers={"Idempotency-Key": "restart-idem-2", "X-Trace-Id": "trace-r4"},
            auth_context=self.auth_pm,
            confidence_threshold=0.75,
            escalation_policy={"id": "policy-1", "ack_minutes_l1": 60, "max_levels": 3},
            now=self.now + timedelta(minutes=1),
        )
        self.assertEqual(status2, 200)
        store_after_second = self.repo.load_ticket_store()
        self.assertEqual(len(store_after_second.manual_queue_by_task_id), first_manual_count)

    def test_overdue_worker_replay_safe_across_restart(self):
        svc1 = Stage1BRuntimeService(self.repo)
        status, payload = svc1.post_create_tasks(
            letter_id=self.letter_id,
            request_body={"approved_extraction_ids": [self.extract_struct], "dry_run": False},
            headers={"Idempotency-Key": "restart-idem-3"},
            auth_context=self.auth_pm,
            confidence_threshold=0.75,
            escalation_policy={"id": "policy-1", "ack_minutes_l1": 1, "max_levels": 3},
            now=self.now,
        )
        self.assertEqual(status, 201)
        self.assertEqual(payload["escalation_started_count"], 1)

        summary1 = svc1.run_assignment_overdue_worker(
            user_mode="immediate",
            now=self.now + timedelta(minutes=5),
        )
        self.assertGreaterEqual(summary1["processed_events"], 1)

        svc2 = Stage1BRuntimeService(self.repo)
        summary2 = svc2.run_assignment_overdue_worker(
            user_mode="immediate",
            now=self.now + timedelta(minutes=10),
        )
        self.assertEqual(summary2["processed_events"], 0)


if __name__ == "__main__":
    unittest.main()
