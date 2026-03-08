from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from scripts.stage3.payout_api import AuthContext
from scripts.stage3.provider_adapter import build_provider_signature_payload
from scripts.stage3.provider_adapter import compute_provider_signature
from scripts.stage3.runtime_api import Stage3RuntimeAPI
from scripts.stage3.runtime_api import Stage3RuntimeStore


class Stage3Slice8RuntimeEndpointsTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 3, 3, 20, 0, tzinfo=timezone.utc)
        self.org_id = "3550f393-cf47-46e9-b146-19d6fbe7e910"
        self.auth_admin = AuthContext(organization_id=self.org_id, requester_role="admin")
        self.runtime_store = Stage3RuntimeStore.bootstrap()
        self.api = Stage3RuntimeAPI(self.runtime_store)

        self.project_id = "7a6dc13a-34a6-4fce-9f01-8d97f36d3d35"
        self.permit_id = "f199bac0-85c9-4ca7-9586-c2f3309bc39a"
        self.milestone_id = "941f2df0-69a8-4868-a892-d3f908e96ce4"

        self.api.register_project(
            {
                "project_id": self.project_id,
                "organization_id": self.org_id,
                "permit_id": self.permit_id,
                "created_at": datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc),
                "profile": {"completeness_score": 0.73, "complexity_score": 0.55},
            }
        )
        self.api.register_milestone(
            {
                "id": self.milestone_id,
                "organization_id": self.org_id,
                "project_id": self.project_id,
                "permit_id": self.permit_id,
                "milestone_state": "payout_eligible",
            }
        )

    def tearDown(self):
        self.runtime_store.repository.close()

    def test_get_preflight_risk_and_recommendations(self):
        headers = {"X-Trace-Id": "trc_rt_1"}
        status, payload = self.api.get_project_preflight_risk(
            project_id=self.project_id,
            query_params={
                "permit_type": "commercial_ti",
                "ahj_id": "ca.san_jose.building",
                "as_of": "2026-03-03T20:00:00Z",
                "include_recommendations": "true",
                "include_explainability": "true",
            },
            headers=headers,
            auth_context=self.auth_admin,
            now=self.now,
        )
        self.assertEqual(status, 200)
        self.assertIn("risk_score", payload)
        self.assertIn("recommended_actions", payload)
        self.assertIn("top_risk_factors", payload)

        # Same request should not duplicate outbox events.
        status2, _ = self.api.get_project_preflight_risk(
            project_id=self.project_id,
            query_params={
                "permit_type": "commercial_ti",
                "ahj_id": "ca.san_jose.building",
                "as_of": "2026-03-03T20:00:00Z",
                "include_recommendations": "true",
                "include_explainability": "true",
            },
            headers=headers,
            auth_context=self.auth_admin,
            now=self.now,
        )
        self.assertEqual(status2, 200)

        outbox = self.runtime_store.repository.list_outbox_events(publish_state=None, limit=100)
        event_types = [event["event_type"] for event in outbox]
        self.assertEqual(event_types.count("permit.preflight_scored"), 1)
        self.assertEqual(event_types.count("permit.recommendations_generated"), 1)

    def test_post_milestone_financial_actions_then_webhook_then_reconcile(self):
        headers = {"Idempotency-Key": "idem_rt_pay_1", "X-Trace-Id": "trc_rt_pay_1"}
        status, instruction = self.api.post_milestone_financial_actions(
            milestone_id=self.milestone_id,
            request_body={
                "amount": 1200.0,
                "currency": "USD",
                "beneficiary_id": "db4f6205-17af-4f17-8e8f-5107af6f2f16",
                "provider": "provider_sandbox",
                "step_up_authenticated": True,
            },
            headers=headers,
            auth_context=self.auth_admin,
            now=self.now,
        )
        self.assertEqual(status, 201)

        status_replay, replay = self.api.post_milestone_financial_actions(
            milestone_id=self.milestone_id,
            request_body={
                "amount": 1200.0,
                "currency": "USD",
                "beneficiary_id": "db4f6205-17af-4f17-8e8f-5107af6f2f16",
                "provider": "provider_sandbox",
                "step_up_authenticated": True,
            },
            headers=headers,
            auth_context=self.auth_admin,
            now=self.now,
        )
        self.assertEqual(status_replay, 200)
        self.assertEqual(replay["instruction_id"], instruction["instruction_id"])

        webhook_status_1, webhook_payload_1 = self.api.post_provider_webhook(
            request_body={
                "instruction_id": instruction["instruction_id"],
                "provider_event_type": "instruction.submitted",
                "provider_reference": "settl_rt_1_submitted",
                "amount": 1200.0,
                "currency": "USD",
            },
            headers={"X-Trace-Id": "trc_rt_webhook_1a"},
            auth_context=self.auth_admin,
            now=self.now,
        )
        self.assertEqual(webhook_status_1, 200)
        self.assertEqual(webhook_payload_1["instruction_state"], "submitted")

        webhook_status, webhook_payload = self.api.post_provider_webhook(
            request_body={
                "instruction_id": instruction["instruction_id"],
                "provider_event_type": "instruction.settled",
                "provider_reference": "settl_rt_1",
                "amount": 1200.0,
                "currency": "USD",
            },
            headers={"X-Trace-Id": "trc_rt_webhook_1b"},
            auth_context=self.auth_admin,
            now=self.now,
        )
        self.assertEqual(webhook_status, 200)
        self.assertEqual(webhook_payload["instruction_state"], "settled")

        rec_status, run = self.api.post_financial_reconciliation_runs(
            request_body={
                "provider": "provider_sandbox",
                "settlements": [
                    {
                        "instruction_id": instruction["instruction_id"],
                        "amount": 1200.0,
                        "currency": "USD",
                        "provider_reference": "settl_rt_1",
                    }
                ],
            },
            headers={"X-Trace-Id": "trc_rt_recon_1"},
            auth_context=self.auth_admin,
            now=self.now,
        )
        self.assertEqual(rec_status, 201)
        self.assertEqual(run["run_status"], "matched")

        get_status, fetched = self.api.get_financial_reconciliation_run(
            run_id=run["id"],
            auth_context=self.auth_admin,
        )
        self.assertEqual(get_status, 200)
        self.assertEqual(fetched["matched_count"], 1)

    def test_outbox_publisher(self):
        self.api.get_project_preflight_risk(
            project_id=self.project_id,
            query_params={
                "permit_type": "commercial_ti",
                "ahj_id": "ca.san_jose.building",
            },
            headers={"X-Trace-Id": "trc_rt_outbox_1"},
            auth_context=self.auth_admin,
            now=self.now,
        )
        pending = self.runtime_store.repository.list_outbox_events(publish_state="pending", limit=100)
        self.assertGreaterEqual(len(pending), 1)

        dispatch = self.api.run_outbox_publisher(max_events=100)
        self.assertGreaterEqual(dispatch["published_count"], 1)

        pending_after = self.runtime_store.repository.list_outbox_events(publish_state="pending", limit=100)
        self.assertEqual(len(pending_after), 0)

    def test_cross_tenant_webhook_cannot_mutate_instruction(self):
        headers = {"Idempotency-Key": "idem_rt_pay_cross_tenant", "X-Trace-Id": "trc_rt_pay_cross_tenant"}
        status, instruction = self.api.post_milestone_financial_actions(
            milestone_id=self.milestone_id,
            request_body={
                "amount": 300.0,
                "currency": "USD",
                "beneficiary_id": "db4f6205-17af-4f17-8e8f-5107af6f2f16",
                "provider": "provider_sandbox",
                "step_up_authenticated": True,
            },
            headers=headers,
            auth_context=self.auth_admin,
            now=self.now,
        )
        self.assertEqual(status, 201)

        foreign_auth = AuthContext(
            organization_id="bf72b0e8-0d5d-4f14-b3f3-b0f2f551f1ef",
            requester_role="admin",
        )
        webhook_status, webhook_payload = self.api.post_provider_webhook(
            request_body={
                "instruction_id": instruction["instruction_id"],
                "provider_event_type": "instruction.submitted",
                "provider_reference": "settl_rt_cross_tenant",
                "amount": 300.0,
                "currency": "USD",
            },
            headers={"X-Trace-Id": "trc_rt_webhook_cross_tenant"},
            auth_context=foreign_auth,
            now=self.now,
        )
        self.assertEqual(webhook_status, 404)
        self.assertEqual(webhook_payload["error"]["code"], "not_found")

        same_org_record = self.runtime_store.repository.get_payout_instruction(
            organization_id=self.org_id,
            instruction_id=instruction["instruction_id"],
        )
        self.assertIsNotNone(same_org_record)
        self.assertEqual(same_org_record["instruction_state"], "created")

    def test_provider_webhook_signature_enforcement(self):
        status, instruction = self.api.post_milestone_financial_actions(
            milestone_id=self.milestone_id,
            request_body={
                "amount": 500.0,
                "currency": "USD",
                "beneficiary_id": "db4f6205-17af-4f17-8e8f-5107af6f2f16",
                "provider": "provider_sandbox",
                "step_up_authenticated": True,
            },
            headers={"Idempotency-Key": "idem_rt_sig_1", "X-Trace-Id": "trc_rt_sig_1"},
            auth_context=self.auth_admin,
            now=self.now,
        )
        self.assertEqual(status, 201)

        self.api.enforce_webhook_signatures = True
        self.api.webhook_signature_secret = "test-webhook-secret"
        request_body = {
            "instruction_id": instruction["instruction_id"],
            "provider_event_type": "instruction.submitted",
            "provider_reference": "settl_rt_sig_1",
            "amount": 500.0,
            "currency": "USD",
        }

        missing_sig_status, missing_sig_payload = self.api.post_provider_webhook(
            request_body=request_body,
            headers={"X-Trace-Id": "trc_rt_sig_missing"},
            auth_context=self.auth_admin,
            now=self.now,
        )
        self.assertEqual(missing_sig_status, 401)
        self.assertEqual(missing_sig_payload["error"]["code"], "signature_missing")

        payload = build_provider_signature_payload(request_body=request_body)
        signature = compute_provider_signature(secret="test-webhook-secret", payload=payload)
        signed_status, signed_payload = self.api.post_provider_webhook(
            request_body=request_body,
            headers={"X-Trace-Id": "trc_rt_sig_ok", "X-Provider-Signature": signature},
            auth_context=self.auth_admin,
            now=self.now,
        )
        self.assertEqual(signed_status, 200)
        self.assertEqual(signed_payload["instruction_state"], "submitted")

    @patch("scripts.stage3.runtime_api.submit_provider_instruction")
    def test_stripe_sandbox_provider_submission_advances_to_submitted(self, submit_mock):
        submit_mock.return_value = {
            "accepted": True,
            "provider_event_type": "instruction.submitted",
            "provider_reference": "pi_test_123",
            "submitted_at": "2026-03-03T20:00:00+00:00",
        }
        status, instruction = self.api.post_milestone_financial_actions(
            milestone_id=self.milestone_id,
            request_body={
                "amount": 700.0,
                "currency": "USD",
                "beneficiary_id": "db4f6205-17af-4f17-8e8f-5107af6f2f16",
                "provider": "stripe_sandbox",
                "step_up_authenticated": True,
            },
            headers={"Idempotency-Key": "idem_rt_stripe_1", "X-Trace-Id": "trc_rt_stripe_1"},
            auth_context=self.auth_admin,
            now=self.now,
        )
        self.assertEqual(status, 201)
        self.assertEqual(instruction["instruction_state"], "submitted")
        self.assertEqual(instruction["provider_reference"], "pi_test_123")

        stored = self.runtime_store.repository.get_payout_instruction(
            organization_id=self.org_id,
            instruction_id=instruction["instruction_id"],
        )
        self.assertIsNotNone(stored)
        self.assertEqual(stored["instruction_state"], "submitted")


if __name__ == "__main__":
    unittest.main()
