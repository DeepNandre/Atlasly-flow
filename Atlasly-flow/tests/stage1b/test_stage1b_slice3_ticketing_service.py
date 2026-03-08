from datetime import datetime, timezone
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.stage1b.tasking_api import Stage1BRequestError
from scripts.stage1b.ticketing_service import AuthContext
from scripts.stage1b.ticketing_service import TicketingStore
from scripts.stage1b.ticketing_service import create_tasks_from_approved_extractions
from scripts.stage1b.ticketing_service import reassign_task


class Stage1BSlice3TicketingServiceTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 3, 3, 15, 0, tzinfo=timezone.utc)
        self.org_id = "3550f393-cf47-46e9-b146-19d6fbe7e910"
        self.project_id = "7a6dc13a-34a6-4fce-9f01-8d97f36d3d35"
        self.letter_id = "0e2dd18d-76e4-4bfd-aad1-9e3078e7e6bb"
        self.extract_a = "05f315d5-1d16-4464-a855-cb4fdb8fa7e7"
        self.extract_b = "56ddbfcc-f6a8-42f1-8c9c-57b1402b7182"
        self.user_a = "8ac5d9a8-c20f-4de3-a25e-84bb22a42544"
        self.user_b = "31afdf4d-ce72-4b7f-99a7-3e8dc0f8ea2b"

        self.store = TicketingStore.empty()
        self.store.letters_by_id[self.letter_id] = {
            "id": self.letter_id,
            "organization_id": self.org_id,
            "project_id": self.project_id,
            "version_hash": "letter-v3-hash",
        }
        self.store.extractions_by_id[self.extract_a] = {
            "id": self.extract_a,
            "letter_id": self.letter_id,
            "comment_id": "c-1",
            "status": "approved_snapshot",
        }
        self.store.extractions_by_id[self.extract_b] = {
            "id": self.extract_b,
            "letter_id": self.letter_id,
            "comment_id": "c-2",
            "status": "approved_snapshot",
        }

        self.auth = AuthContext(
            organization_id=self.org_id,
            user_id="19a6140e-46de-42dd-839d-b7b4f3df8a0f",
            requester_role="pm",
        )

    def test_create_tasks_then_replay_same_key(self):
        request_body = {
            "approved_extraction_ids": [self.extract_a, self.extract_b],
            "dry_run": False,
        }
        first_status, first_response = create_tasks_from_approved_extractions(
            letter_id=self.letter_id,
            request_body=request_body,
            idempotency_key="idem-stage1b-001",
            trace_id="trace-001",
            auth_context=self.auth,
            store=self.store,
            now=self.now,
        )
        second_status, second_response = create_tasks_from_approved_extractions(
            letter_id=self.letter_id,
            request_body=request_body,
            idempotency_key="idem-stage1b-001",
            trace_id="trace-002",
            auth_context=self.auth,
            store=self.store,
            now=self.now,
        )

        self.assertEqual(first_status, 201)
        self.assertEqual(second_status, 200)
        self.assertEqual(first_response["task_ids"], second_response["task_ids"])
        self.assertEqual(len(self.store.tasks_by_id), 2)
        self.assertEqual(len(self.store.outbox_events), 1)
        event = self.store.outbox_events[0]
        self.assertEqual(event["event_type"], "tasks.bulk_created_from_extractions")
        self.assertEqual(event["event_version"], 1)
        self.assertEqual(event["aggregate_type"], "comment_letter")

    def test_idempotency_conflict_same_key_different_payload(self):
        create_tasks_from_approved_extractions(
            letter_id=self.letter_id,
            request_body={"approved_extraction_ids": [self.extract_a], "dry_run": False},
            idempotency_key="idem-stage1b-conflict",
            trace_id="trace-003",
            auth_context=self.auth,
            store=self.store,
            now=self.now,
        )

        with self.assertRaises(Stage1BRequestError) as ctx:
            create_tasks_from_approved_extractions(
                letter_id=self.letter_id,
                request_body={"approved_extraction_ids": [self.extract_b], "dry_run": False},
                idempotency_key="idem-stage1b-conflict",
                trace_id="trace-004",
                auth_context=self.auth,
                store=self.store,
                now=self.now,
            )
        self.assertEqual(ctx.exception.status, 409)

    def test_reassign_task_writes_feedback(self):
        _, created = create_tasks_from_approved_extractions(
            letter_id=self.letter_id,
            request_body={"approved_extraction_ids": [self.extract_a], "dry_run": False},
            idempotency_key="idem-stage1b-reassign",
            trace_id="trace-005",
            auth_context=self.auth,
            store=self.store,
            now=self.now,
        )
        task_id = created["task_ids"][0]
        self.store.tasks_by_id[task_id]["assignee_user_id"] = self.user_a
        self.store.tasks_by_id[task_id]["auto_assigned"] = True

        status, payload = reassign_task(
            task_id=task_id,
            payload={
                "from_assignee_id": self.user_a,
                "to_assignee_id": self.user_b,
                "feedback_reason_code": "WRONG_DISCIPLINE",
                "source_rule_id": "3dad70f0-76c9-4884-b9f5-74f86bb1487a",
                "source_confidence": 0.81,
            },
            auth_context=self.auth,
            store=self.store,
            now=self.now,
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["task_id"], task_id)
        self.assertEqual(self.store.tasks_by_id[task_id]["assignee_user_id"], self.user_b)
        feedback = self.store.task_feedback_by_id[payload["feedback_id"]]
        self.assertEqual(feedback["feedback_reason_code"], "WRONG_DISCIPLINE")
        self.assertEqual(feedback["was_auto_assigned"], True)

    def test_reassign_requires_task_write_role(self):
        _, created = create_tasks_from_approved_extractions(
            letter_id=self.letter_id,
            request_body={"approved_extraction_ids": [self.extract_a], "dry_run": False},
            idempotency_key="idem-stage1b-role",
            trace_id="trace-006",
            auth_context=self.auth,
            store=self.store,
            now=self.now,
        )
        task_id = created["task_ids"][0]
        self.store.tasks_by_id[task_id]["assignee_user_id"] = self.user_a

        bad_auth = AuthContext(
            organization_id=self.org_id,
            user_id="3f164e25-c4f0-495f-bf4d-5f58ca72ef1b",
            requester_role="subcontractor",
        )
        with self.assertRaises(Stage1BRequestError) as ctx:
            reassign_task(
                task_id=task_id,
                payload={
                    "from_assignee_id": self.user_a,
                    "to_assignee_id": self.user_b,
                    "feedback_reason_code": "WRONG_DISCIPLINE",
                },
                auth_context=bad_auth,
                store=self.store,
                now=self.now,
            )
        self.assertEqual(ctx.exception.status, 403)


if __name__ == "__main__":
    unittest.main()
