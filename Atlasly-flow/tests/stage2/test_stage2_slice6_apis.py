from datetime import datetime, timedelta, timezone
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.stage2.status_sync import AuthContext
from scripts.stage2.status_sync import Stage2SyncError
from scripts.stage2.status_sync import SyncStore
from scripts.stage2.status_sync import record_status_observation
from scripts.stage2.sync_api import get_status_timeline
from scripts.stage2.sync_api import post_connector_poll


class Stage2Slice6ApiTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 3, 3, 17, 0, tzinfo=timezone.utc)
        self.org_id = "3550f393-cf47-46e9-b146-19d6fbe7e910"
        self.permit_id = "f199bac0-85c9-4ca7-9586-c2f3309bc39a"
        self.auth = AuthContext(organization_id=self.org_id, requester_role="admin")
        self.store = SyncStore.empty()

    def test_post_connector_poll_happy_path_and_idempotent_replay(self):
        status1, run1 = post_connector_poll(
            ahj="ca.san_jose.building",
            request_body={"connector": "accela_api", "dry_run": False, "force": False},
            idempotency_key="idem-poll-api-001",
            auth_context=self.auth,
            store=self.store,
            now=self.now,
        )
        status2, run2 = post_connector_poll(
            ahj="ca.san_jose.building",
            request_body={"connector": "accela_api", "dry_run": False, "force": False},
            idempotency_key="idem-poll-api-001",
            auth_context=self.auth,
            store=self.store,
            now=self.now,
        )

        self.assertEqual(status1, 202)
        self.assertEqual(status2, 200)
        self.assertEqual(run1["run_id"], run2["run_id"])

    def test_post_connector_poll_validation(self):
        with self.assertRaises(Stage2SyncError) as ctx:
            post_connector_poll(
                ahj="invalid/ahj",
                request_body={"connector": "accela_api"},
                idempotency_key="idem-poll-api-002",
                auth_context=self.auth,
                store=self.store,
                now=self.now,
            )
        self.assertEqual(ctx.exception.status, 422)

        with self.assertRaises(Stage2SyncError) as ctx2:
            post_connector_poll(
                ahj="ca.san_jose.building",
                request_body={"connector": ""},
                idempotency_key="idem-poll-api-003",
                auth_context=self.auth,
                store=self.store,
                now=self.now,
            )
        self.assertEqual(ctx2.exception.status, 422)

    def test_get_status_timeline_happy_path_with_filters_and_provenance(self):
        record_status_observation(
            permit_id=self.permit_id,
            source="accela_api",
            raw_status="Submitted",
            old_status=None,
            organization_id=self.org_id,
            connector="accela_api",
            ahj_id="ca.san_jose.building",
            observed_at=self.now - timedelta(hours=2),
            parser_version="v1",
            event_hash="evt_hash_api_001",
            trace_id="trc-stage2-api-001",
            idempotency_key="idem-status-api-001",
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
            provenance_source_type="api",
            provenance_source_ref="accela/cases/123",
            source_payload_hash="payload_hash_001",
            store=self.store,
        )
        record_status_observation(
            permit_id=self.permit_id,
            source="accela_api",
            raw_status="Under Review",
            old_status="submitted",
            organization_id=self.org_id,
            connector="accela_api",
            ahj_id="ca.san_jose.building",
            observed_at=self.now - timedelta(minutes=30),
            parser_version="v1",
            event_hash="evt_hash_api_002",
            trace_id="trc-stage2-api-002",
            idempotency_key="idem-status-api-002",
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
            provenance_source_type="api",
            provenance_source_ref="accela/cases/123",
            source_payload_hash="payload_hash_002",
            store=self.store,
        )

        status, payload = get_status_timeline(
            permit_id=self.permit_id,
            query_params={"from": (self.now - timedelta(hours=1)).isoformat()},
            auth_context=self.auth,
            store=self.store,
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["permit_id"], self.permit_id)
        self.assertEqual(len(payload["timeline"]), 1)
        item = payload["timeline"][0]
        self.assertEqual(item["normalized_status"], "in_review")
        self.assertEqual(item["provenance"]["source_type"], "api")
        self.assertEqual(item["provenance"]["source_ref"], "accela/cases/123")

    def test_get_status_timeline_tenant_isolation(self):
        record_status_observation(
            permit_id=self.permit_id,
            source="accela_api",
            raw_status="Submitted",
            old_status=None,
            organization_id=self.org_id,
            connector="accela_api",
            ahj_id="ca.san_jose.building",
            observed_at=self.now,
            parser_version="v1",
            event_hash="evt_hash_api_003",
            trace_id="trc-stage2-api-003",
            idempotency_key="idem-status-api-003",
            rules=[],
            store=self.store,
        )

        with self.assertRaises(Stage2SyncError) as ctx:
            get_status_timeline(
                permit_id=self.permit_id,
                query_params={},
                auth_context=AuthContext(
                    organization_id="bf72b0e8-0d5d-4f14-b3f3-b0f2f551f1ef",
                    requester_role="admin",
                ),
                store=self.store,
            )
        self.assertEqual(ctx.exception.status, 403)

    def test_get_status_timeline_query_validation(self):
        with self.assertRaises(Stage2SyncError) as ctx:
            get_status_timeline(
                permit_id=self.permit_id,
                query_params={"limit": 500},
                auth_context=self.auth,
                store=self.store,
            )
        self.assertEqual(ctx.exception.status, 422)

        with self.assertRaises(Stage2SyncError) as ctx2:
            get_status_timeline(
                permit_id=self.permit_id,
                query_params={
                    "from": "2026-03-03T12:00:00Z",
                    "to": "2026-03-03T11:00:00Z",
                },
                auth_context=self.auth,
                store=self.store,
            )
        self.assertEqual(ctx2.exception.status, 422)


if __name__ == "__main__":
    unittest.main()
