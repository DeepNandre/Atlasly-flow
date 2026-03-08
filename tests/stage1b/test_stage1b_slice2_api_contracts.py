import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.stage1b.tasking_api import Stage1BRequestError
from scripts.stage1b.tasking_api import evaluate_idempotent_replay
from scripts.stage1b.tasking_api import parse_create_tasks_request
from scripts.stage1b.tasking_api import validate_reassignment_payload


class Stage1BSlice2ApiContractTests(unittest.TestCase):
    def test_create_tasks_openapi_contract_contains_idempotency_and_statuses(self):
        path = ROOT / "contracts/stage1b/apis/create-tasks.v1.openapi.yaml"
        self.assertTrue(path.exists(), f"missing {path}")
        body = path.read_text()

        required_tokens = [
            "/comment-letters/{letterId}/create-tasks:",
            "Idempotency-Key",
            '"200":',
            '"201":',
            '"409":',
            '"422":',
            "approved_extraction_ids",
        ]
        for token in required_tokens:
            self.assertIn(token, body)

    def test_reassign_openapi_contract_contains_feedback_reason_and_validation(self):
        path = ROOT / "contracts/stage1b/apis/reassign-task.v1.openapi.yaml"
        self.assertTrue(path.exists(), f"missing {path}")
        body = path.read_text()

        required_tokens = [
            "/tasks/{taskId}/reassign:",
            "feedback_reason_code",
            "WRONG_DISCIPLINE",
            "MISSING_RULE",
            '"422":',
        ]
        for token in required_tokens:
            self.assertIn(token, body)

    def test_server_generated_idempotency_key_is_deterministic(self):
        kwargs = {
            "organization_id": "3550f393-cf47-46e9-b146-19d6fbe7e910",
            "project_id": "7a6dc13a-34a6-4fce-9f01-8d97f36d3d35",
            "letter_id": "0e2dd18d-76e4-4bfd-aad1-9e3078e7e6bb",
            "body": {
                "approved_extraction_ids": [
                    "05f315d5-1d16-4464-a855-cb4fdb8fa7e7",
                    "56ddbfcc-f6a8-42f1-8c9c-57b1402b7182",
                ],
                "dry_run": False,
            },
            "client_idempotency_key": None,
            "letter_version_hash": "letter-v3-hash",
        }
        first = parse_create_tasks_request(**kwargs)
        second = parse_create_tasks_request(**kwargs)
        self.assertEqual(first.idempotency_key, second.idempotency_key)
        self.assertEqual(first.request_hash, second.request_hash)

    def test_replay_decision_semantics(self):
        request = parse_create_tasks_request(
            organization_id="3550f393-cf47-46e9-b146-19d6fbe7e910",
            project_id="7a6dc13a-34a6-4fce-9f01-8d97f36d3d35",
            letter_id="0e2dd18d-76e4-4bfd-aad1-9e3078e7e6bb",
            body={
                "approved_extraction_ids": [
                    "05f315d5-1d16-4464-a855-cb4fdb8fa7e7",
                ],
                "dry_run": False,
            },
            client_idempotency_key="client-key-1",
            letter_version_hash="letter-v3-hash",
        )

        status, outcome = evaluate_idempotent_replay(
            existing_run_status=None,
            existing_request_hash=None,
            incoming_request_hash=request.request_hash,
        )
        self.assertEqual((status, outcome), (201, "create"))

        status, outcome = evaluate_idempotent_replay(
            existing_run_status="COMPLETED",
            existing_request_hash=request.request_hash,
            incoming_request_hash=request.request_hash,
        )
        self.assertEqual((status, outcome), (200, "replay"))

        status, outcome = evaluate_idempotent_replay(
            existing_run_status="COMPLETED",
            existing_request_hash="other-hash",
            incoming_request_hash=request.request_hash,
        )
        self.assertEqual((status, outcome), (409, "conflict"))

    def test_reassignment_feedback_validation(self):
        validate_reassignment_payload(
            {
                "from_assignee_id": "8ac5d9a8-c20f-4de3-a25e-84bb22a42544",
                "to_assignee_id": "31afdf4d-ce72-4b7f-99a7-3e8dc0f8ea2b",
                "feedback_reason_code": "WRONG_DISCIPLINE",
                "source_confidence": 0.88,
            }
        )

        with self.assertRaises(Stage1BRequestError) as same_assignee:
            validate_reassignment_payload(
                {
                    "from_assignee_id": "8ac5d9a8-c20f-4de3-a25e-84bb22a42544",
                    "to_assignee_id": "8ac5d9a8-c20f-4de3-a25e-84bb22a42544",
                    "feedback_reason_code": "WRONG_DISCIPLINE",
                }
            )
        self.assertEqual(same_assignee.exception.status, 422)

        with self.assertRaises(Stage1BRequestError) as bad_reason:
            validate_reassignment_payload(
                {
                    "from_assignee_id": "8ac5d9a8-c20f-4de3-a25e-84bb22a42544",
                    "to_assignee_id": "31afdf4d-ce72-4b7f-99a7-3e8dc0f8ea2b",
                    "feedback_reason_code": "NOT_ALLOWED",
                }
            )
        self.assertEqual(bad_reason.exception.status, 422)


if __name__ == "__main__":
    unittest.main()
