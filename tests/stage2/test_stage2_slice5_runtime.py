from datetime import datetime, timezone
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.stage2.status_sync import AuthContext
from scripts.stage2.status_sync import Stage2SyncError
from scripts.stage2.status_sync import SyncStore
from scripts.stage2.status_sync import classify_drift
from scripts.stage2.status_sync import create_poll_run
from scripts.stage2.status_sync import normalize_status
from scripts.stage2.status_sync import record_status_observation


class Stage2Slice5RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 3, 3, 16, 0, tzinfo=timezone.utc)
        self.org_id = "3550f393-cf47-46e9-b146-19d6fbe7e910"
        self.permit_id = "f199bac0-85c9-4ca7-9586-c2f3309bc39a"
        self.auth = AuthContext(organization_id=self.org_id, requester_role="admin")
        self.store = SyncStore.empty()

    def test_connector_poll_idempotency(self):
        status1, run1 = create_poll_run(
            connector="accela_api",
            ahj_id="ca.san_jose.building",
            idempotency_key="idem-poll-001",
            auth_context=self.auth,
            store=self.store,
            now=self.now,
        )
        status2, run2 = create_poll_run(
            connector="accela_api",
            ahj_id="ca.san_jose.building",
            idempotency_key="idem-poll-001",
            auth_context=self.auth,
            store=self.store,
            now=self.now,
        )

        self.assertEqual(status1, 202)
        self.assertEqual(status2, 200)
        self.assertEqual(run1["run_id"], run2["run_id"])
        self.assertEqual(len(self.store.poll_runs_by_id), 1)

    def test_connector_poll_role_guard(self):
        with self.assertRaises(Stage2SyncError) as ctx:
            create_poll_run(
                connector="accela_api",
                ahj_id="ca.san_jose.building",
                idempotency_key="idem-poll-002",
                auth_context=AuthContext(
                    organization_id=self.org_id, requester_role="subcontractor"
                ),
                store=self.store,
                now=self.now,
            )
        self.assertEqual(ctx.exception.status, 403)

    def test_normalization_exact_regex_and_lexical(self):
        rules = [
            {
                "connector": "accela_api",
                "ahj_id": "ca.san_jose.building",
                "match_type": "exact",
                "raw_pattern": "Ready To Issue",
                "normalized_status": "approved",
                "confidence_score": 0.99,
                "priority": 1,
                "is_active": True,
            },
            {
                "connector": "accela_api",
                "ahj_id": "ca.san_jose.building",
                "match_type": "regex",
                "raw_pattern": "review",
                "normalized_status": "in_review",
                "confidence_score": 0.95,
                "priority": 5,
                "is_active": True,
            },
        ]

        exact = normalize_status(
            raw_status="Ready To Issue",
            connector="accela_api",
            ahj_id="ca.san_jose.building",
            rules=rules,
        )
        regex = normalize_status(
            raw_status="Under Department Review",
            connector="accela_api",
            ahj_id="ca.san_jose.building",
            rules=rules,
        )
        lexical = normalize_status(
            raw_status="Permit issued",
            connector="opengov_api",
            ahj_id="ca.san_diego.dsd",
            rules=[],
        )

        self.assertEqual(exact["normalized_status"], "approved")
        self.assertEqual(exact["confidence"], 0.99)
        self.assertEqual(regex["normalized_status"], "in_review")
        self.assertEqual(regex["confidence"], 0.95)
        self.assertEqual(lexical["normalized_status"], "issued")
        self.assertEqual(lexical["confidence"], 0.75)

    def test_invalid_transition_is_queued_for_review(self):
        result = record_status_observation(
            permit_id=self.permit_id,
            source="accela_api",
            raw_status="Submitted",
            old_status="expired",
            organization_id=self.org_id,
            connector="accela_api",
            ahj_id="ca.san_jose.building",
            observed_at=self.now,
            parser_version="v1",
            event_hash="evt_hash_001",
            trace_id="trc_stage2_001",
            idempotency_key="idem-status-001",
            rules=[
                {
                    "connector": "accela_api",
                    "ahj_id": "ca.san_jose.building",
                    "match_type": "exact",
                    "raw_pattern": "Submitted",
                    "normalized_status": "submitted",
                    "confidence_score": 0.99,
                    "priority": 1,
                    "is_active": True,
                }
            ],
            store=self.store,
        )

        self.assertFalse(result["applied"])
        self.assertIsNotNone(result["review"])
        self.assertEqual(result["review"]["rejection_reason"], "invalid_transition")
        self.assertEqual(len(self.store.transition_reviews), 1)
        self.assertIsNone(result["changed_event"])

    def test_unmapped_raw_status_goes_to_manual_review_without_apply(self):
        result = record_status_observation(
            permit_id=self.permit_id,
            source="accela_api",
            raw_status="Municipal Queue Pending Analyst Triage",
            old_status="submitted",
            organization_id=self.org_id,
            connector="accela_api",
            ahj_id="ca.san_jose.building",
            observed_at=self.now,
            parser_version="v1",
            event_hash="evt_hash_unmapped_001",
            trace_id="trc_stage2_unmapped_001",
            idempotency_key="idem-status-unmapped-001",
            rules=[],
            store=self.store,
        )
        self.assertFalse(result["applied"])
        self.assertEqual(result["normalized"]["strategy"], "unmapped")
        self.assertEqual(result["review"]["rejection_reason"], "unmapped_status")
        self.assertIsNone(result["observed_event"])
        self.assertIsNone(result["changed_event"])
        self.assertNotIn(self.permit_id, self.store.permit_current_status)

    def test_low_confidence_lexical_match_goes_to_manual_review_without_apply(self):
        result = record_status_observation(
            permit_id=self.permit_id,
            source="opengov_api",
            raw_status="Permit issued",
            old_status="submitted",
            organization_id=self.org_id,
            connector="opengov_api",
            ahj_id="ca.san_diego.dsd",
            observed_at=self.now,
            parser_version="v1",
            event_hash="evt_hash_lowconf_001",
            trace_id="trc_stage2_lowconf_001",
            idempotency_key="idem-status-lowconf-001",
            rules=[],
            store=self.store,
        )
        self.assertFalse(result["applied"])
        self.assertEqual(result["normalized"]["strategy"], "lexical")
        self.assertLess(result["normalized"]["confidence"], 0.90)
        self.assertEqual(result["review"]["rejection_reason"], "low_confidence")
        self.assertIsNotNone(result["observed_event"])
        self.assertIsNone(result["changed_event"])
        self.assertNotIn(self.permit_id, self.store.permit_current_status)

    def test_valid_high_confidence_transition_is_applied_and_emits_status_changed(self):
        result = record_status_observation(
            permit_id=self.permit_id,
            source="accela_api",
            raw_status="Under Review",
            old_status="submitted",
            organization_id=self.org_id,
            connector="accela_api",
            ahj_id="ca.san_jose.building",
            observed_at=self.now,
            parser_version="v1",
            event_hash="evt_hash_highconf_001",
            trace_id="trc_stage2_highconf_001",
            idempotency_key="idem-status-highconf-001",
            rules=[
                {
                    "connector": "accela_api",
                    "ahj_id": "ca.san_jose.building",
                    "match_type": "regex",
                    "raw_pattern": "review",
                    "normalized_status": "in_review",
                    "confidence_score": 0.95,
                    "priority": 1,
                    "is_active": True,
                }
            ],
            store=self.store,
        )
        self.assertTrue(result["applied"])
        self.assertIsNone(result["review"])
        self.assertEqual(self.store.permit_current_status[self.permit_id], "in_review")
        self.assertIsNotNone(result["observed_event"])
        self.assertIsNotNone(result["changed_event"])
        self.assertEqual(result["changed_event"]["event_type"], "permit.status_changed")

    def test_drift_classification_priority(self):
        self.assertEqual(
            classify_drift(
                projected_status="in_review",
                recomputed_status="approved",
                previous_ruleset_version="v1",
                current_ruleset_version="v2",
                previous_payload_hash="a1",
                current_payload_hash="b1",
            ),
            "mapping_drift",
        )
        self.assertEqual(
            classify_drift(
                projected_status="in_review",
                recomputed_status="approved",
                previous_ruleset_version="v2",
                current_ruleset_version="v2",
                previous_payload_hash="a1",
                current_payload_hash="b1",
            ),
            "source_drift",
        )
        self.assertEqual(
            classify_drift(
                projected_status="in_review",
                recomputed_status="approved",
                previous_ruleset_version="v2",
                current_ruleset_version="v2",
                previous_payload_hash="a1",
                current_payload_hash="a1",
            ),
            "timeline_gap",
        )


if __name__ == "__main__":
    unittest.main()
