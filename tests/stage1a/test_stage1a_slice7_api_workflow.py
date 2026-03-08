from datetime import datetime, timezone
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.stage1a.comment_extraction_service import AuthContext
from scripts.stage1a.comment_extraction_service import Stage1ARequestError
from scripts.stage1a.comment_extraction_service import Stage1AStore
from scripts.stage1a.comment_extraction_service import process_extraction_candidates
from scripts.stage1a.comment_extraction_service import review_extraction
from scripts.stage1a.comment_letter_api import get_comment_letter
from scripts.stage1a.comment_letter_api import get_comment_letter_extractions
from scripts.stage1a.comment_letter_api import post_comment_letter_approve
from scripts.stage1a.comment_letter_api import post_comment_letters


class Stage1ASlice7ApiWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 3, 3, 14, 0, tzinfo=timezone.utc)
        self.org_id = "3550f393-cf47-46e9-b146-19d6fbe7e910"
        self.auth = AuthContext(
            organization_id=self.org_id,
            requester_role="reviewer",
            user_id="8ac5d9a8-c20f-4de3-a25e-84bb22a42544",
        )
        self.store = Stage1AStore.empty()
        self.project_id = "7a6dc13a-34a6-4fce-9f01-8d97f36d3d35"
        self.document_id = "0e2dd18d-76e4-4bfd-aad1-9e3078e7e6bb"

    def _create_letter(self) -> str:
        status, payload = post_comment_letters(
            request_body={"project_id": self.project_id, "document_id": self.document_id},
            idempotency_key="stage1a-s7-idem-001",
            trace_id="trc-stage1a-001",
            auth_context=self.auth,
            store=self.store,
        )
        self.assertEqual(status, 202)
        return payload["letter_id"]

    def test_openapi_contract_has_required_paths(self):
        body = (ROOT / "contracts/stage1a/api/comment-letters.openapi.yaml").read_text()
        for token in [
            "/comment-letters:",
            "/comment-letters/{letterId}:",
            "/comment-letters/{letterId}/extractions:",
            "/comment-letters/{letterId}/approve:",
        ]:
            self.assertIn(token, body)
        self.assertNotIn("required: [approved_by]", body)

    def test_create_letter_idempotent_and_parsing_started_emitted_once(self):
        first_status, first = post_comment_letters(
            request_body={"project_id": self.project_id, "document_id": self.document_id},
            idempotency_key="stage1a-s7-idem-002",
            trace_id="trc-stage1a-002",
            auth_context=self.auth,
            store=self.store,
        )
        second_status, second = post_comment_letters(
            request_body={"project_id": self.project_id, "document_id": self.document_id},
            idempotency_key="stage1a-s7-idem-002",
            trace_id="trc-stage1a-002",
            auth_context=self.auth,
            store=self.store,
        )

        self.assertEqual(first_status, 202)
        self.assertEqual(second_status, 200)
        self.assertEqual(first["letter_id"], second["letter_id"])

        events = [
            e
            for e in self.store.outbox_events
            if e["aggregate_id"] == first["letter_id"] and e["event_type"] == "comment_letter.parsing_started"
        ]
        self.assertEqual(len(events), 1)

    def test_extract_review_approve_workflow(self):
        letter_id = self._create_letter()

        page_text = {
            1: "Revise panel schedule per NEC 408.4 and provide updated load calculations.",
            2: "Provide duct sizing report per IMC 603.2 and include stamped calculations.",
        }

        status, summary = process_extraction_candidates(
            letter_id=letter_id,
            candidates=[
                {
                    "raw_text": "Revise panel schedule per NEC 408.4 and provide updated load calculations.",
                    "discipline": "electrical",
                    "severity": "major",
                    "requested_action": "Revise panel schedule and submit updated load calculations signed by the engineer of record.",
                    "code_reference": "NEC 408.4",
                    "page_number": 1,
                    "citation": {"quote": "panel schedule per NEC 408.4", "char_start": 7, "char_end": 35},
                    "model_prob_discipline": 0.98,
                    "model_prob_severity": 0.95,
                    "model_prob_code_reference": 0.97,
                },
                {
                    "raw_text": "Provide duct sizing report per IMC 603.2 and include stamped calculations.",
                    "discipline": "mechanical",
                    "severity": "major",
                    "requested_action": "Provide duct sizing report and include stamped calculations with revision clouding.",
                    "code_reference": "NOT-A-CODE",
                    "page_number": 2,
                    "citation": {"quote": "duct sizing report per IMC 603.2", "char_start": 8, "char_end": 40},
                    "model_prob_discipline": 0.95,
                    "model_prob_severity": 0.94,
                    "model_prob_code_reference": 0.95,
                },
            ],
            page_text_by_number=page_text,
            ocr_quality_by_page={1: 0.94, 2: 0.93},
            trace_id="trc-stage1a-003",
            auth_context=self.auth,
            store=self.store,
            now=self.now,
        )

        self.assertEqual(status, 200)
        self.assertEqual(summary["status"], "review_queueing")
        self.assertEqual(summary["extraction_count"], 2)
        self.assertEqual(summary["requires_review_count"], 1)

        get_status, letter = get_comment_letter(letter_id=letter_id, auth_context=self.auth, store=self.store)
        self.assertEqual(get_status, 200)
        self.assertEqual(letter["requires_review_count"], 1)

        list_status, extractions_payload = get_comment_letter_extractions(
            letter_id=letter_id,
            auth_context=self.auth,
            store=self.store,
        )
        self.assertEqual(list_status, 200)
        self.assertEqual(len(extractions_payload["extractions"]), 2)

        bad_row = [row for row in extractions_payload["extractions"] if row["code_reference"] == "NOT-A-CODE"][0]
        self.assertEqual(bad_row["status"], "needs_review")

        with self.assertRaises(Stage1ARequestError) as not_ready:
            post_comment_letter_approve(
                letter_id=letter_id,
                request_body={},
                trace_id="trc-stage1a-004",
                auth_context=self.auth,
                store=self.store,
            )
        self.assertEqual(not_ready.exception.status, 409)

        review_status, _ = review_extraction(
            letter_id=letter_id,
            extraction_id=bad_row["id"],
            decision="corrected",
            correction_payload={"code_reference": "IMC 603.2"},
            rationale="Validated against cited section.",
            auth_context=self.auth,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(review_status, 200)

        approve_status, approve_payload = post_comment_letter_approve(
            letter_id=letter_id,
            request_body={"approved_by": "31afdf4d-ce72-4b7f-99a7-3e8dc0f8ea2b"},
            trace_id="trc-stage1a-005",
            auth_context=self.auth,
            store=self.store,
        )
        self.assertEqual(approve_status, 200)
        self.assertIn("snapshot_id", approve_payload)
        self.assertEqual(approve_payload["approved_by"], self.auth.user_id)

        replay_status, replay_payload = post_comment_letter_approve(
            letter_id=letter_id,
            request_body={"approved_by": "bf72b0e8-0d5d-4f14-b3f3-b0f2f551f1ef"},
            trace_id="trc-stage1a-005",
            auth_context=self.auth,
            store=self.store,
        )
        self.assertEqual(replay_status, 200)
        self.assertEqual(replay_payload["snapshot_id"], approve_payload["snapshot_id"])
        self.assertEqual(replay_payload["approved_by"], self.auth.user_id)

        approved_events = [
            e
            for e in self.store.outbox_events
            if e["aggregate_id"] == letter_id and e["event_type"] == "comment_letter.approved"
        ]
        self.assertEqual(len(approved_events), 1)
        self.assertEqual(approved_events[0]["payload"]["approved_by"], self.auth.user_id)

    def test_approve_requires_authenticated_user_identity(self):
        letter_id = self._create_letter()
        unauth_actor = AuthContext(
            organization_id=self.org_id,
            requester_role="reviewer",
            user_id=None,
        )
        with self.assertRaises(Stage1ARequestError) as ctx:
            post_comment_letter_approve(
                letter_id=letter_id,
                request_body={"approved_by": "31afdf4d-ce72-4b7f-99a7-3e8dc0f8ea2b"},
                trace_id="trc-stage1a-006",
                auth_context=unauth_actor,
                store=self.store,
            )
        self.assertEqual(ctx.exception.status, 401)
        self.assertEqual(ctx.exception.code, "unauthorized")
        self.assertIn("authenticated user identity is required", ctx.exception.message)

    def test_tenant_isolation(self):
        letter_id = self._create_letter()
        other_auth = AuthContext(
            organization_id="bf72b0e8-0d5d-4f14-b3f3-b0f2f551f1ef",
            requester_role="reviewer",
            user_id="31afdf4d-ce72-4b7f-99a7-3e8dc0f8ea2b",
        )
        with self.assertRaises(Stage1ARequestError) as ctx:
            get_comment_letter(letter_id=letter_id, auth_context=other_auth, store=self.store)
        self.assertEqual(ctx.exception.status, 403)


if __name__ == "__main__":
    unittest.main()
