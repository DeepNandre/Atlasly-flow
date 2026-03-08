from datetime import datetime, timezone
import unittest

from scripts.stage3.milestone_api import verify_milestone
from scripts.stage3.milestone_api import verify_milestone_persisted
from scripts.stage3.payout_api import AuthContext
from scripts.stage3.payout_api import PayoutRequestError
from scripts.stage3.repositories import Stage3PersistenceStore
from scripts.stage3.repositories import Stage3Repository


class Stage3Slice7MilestoneVerificationTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 3, 3, 19, 0, tzinfo=timezone.utc)
        self.org_id = "3550f393-cf47-46e9-b146-19d6fbe7e910"
        self.auth = AuthContext(organization_id=self.org_id, requester_role="admin")
        self.milestone = {
            "id": "941f2df0-69a8-4868-a892-d3f908e96ce4",
            "organization_id": self.org_id,
            "project_id": "7a6dc13a-34a6-4fce-9f01-8d97f36d3d35",
            "permit_id": "f199bac0-85c9-4ca7-9586-c2f3309bc39a",
            "milestone_state": "pending_verification",
        }
        self.evidence = {
            "permit_event_ids": ["evt_1", "evt_2"],
            "raw_source_ref": "connector:accela:run_9",
            "occurred_at": "2026-03-03T18:50:00Z",
            "received_at": "2026-03-03T18:52:00Z",
        }

    def test_verify_milestone_happy_path(self):
        updated, event = verify_milestone(
            milestone=self.milestone,
            verification_source="connector_event",
            evidence=self.evidence,
            verification_rule_version="v1.0.0",
            trace_id="trc_m_1",
            idempotency_key="idem_m_1",
            auth_context=self.auth,
            now=self.now,
        )
        self.assertEqual(updated["milestone_state"], "verified")
        self.assertEqual(event["event_type"], "milestone.verified")
        self.assertEqual(event["event_version"], 1)
        self.assertEqual(event["aggregate_type"], "milestone")
        self.assertEqual(event["aggregate_id"], self.milestone["id"])

    def test_invalid_state_rejected(self):
        bad = dict(self.milestone)
        bad["milestone_state"] = "payout_eligible"
        with self.assertRaises(PayoutRequestError) as ctx:
            verify_milestone(
                milestone=bad,
                verification_source="connector_event",
                evidence=self.evidence,
                verification_rule_version="v1.0.0",
                trace_id="trc_m_2",
                idempotency_key="idem_m_2",
                auth_context=self.auth,
                now=self.now,
            )
        self.assertEqual(ctx.exception.status, 409)

    def test_evidence_requirements_enforced(self):
        bad_evidence = dict(self.evidence)
        del bad_evidence["raw_source_ref"]
        with self.assertRaises(PayoutRequestError) as ctx:
            verify_milestone(
                milestone=self.milestone,
                verification_source="connector_event",
                evidence=bad_evidence,
                verification_rule_version="v1.0.0",
                trace_id="trc_m_3",
                idempotency_key="idem_m_3",
                auth_context=self.auth,
                now=self.now,
            )
        self.assertEqual(ctx.exception.status, 422)

    def test_tenant_isolation(self):
        with self.assertRaises(PayoutRequestError) as ctx:
            verify_milestone(
                milestone=self.milestone,
                verification_source="connector_event",
                evidence=self.evidence,
                verification_rule_version="v1.0.0",
                trace_id="trc_m_4",
                idempotency_key="idem_m_4",
                auth_context=AuthContext(
                    organization_id="bf72b0e8-0d5d-4f14-b3f3-b0f2f551f1ef",
                    requester_role="admin",
                ),
                now=self.now,
            )
        self.assertEqual(ctx.exception.status, 403)

    def test_persisted_verification_writes_outbox(self):
        repo = Stage3Repository(Stage3PersistenceStore.empty())
        _, event = verify_milestone_persisted(
            milestone=self.milestone,
            verification_source="connector_event",
            evidence=self.evidence,
            verification_rule_version="v1.0.0",
            trace_id="trc_m_5",
            idempotency_key="idem_m_5",
            auth_context=self.auth,
            repository=repo,
            now=self.now,
        )
        self.assertEqual(event["event_type"], "milestone.verified")
        self.assertEqual(len(repo._store.outbox_events), 1)


if __name__ == "__main__":
    unittest.main()
