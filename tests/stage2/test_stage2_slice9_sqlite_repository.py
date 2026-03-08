from datetime import datetime, timezone
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.stage2.connector_runtime import AccelaApiAdapter
from scripts.stage2.connector_runtime import ConnectorObservation
from scripts.stage2.connector_runtime import ConnectorPollError
from scripts.stage2.connector_runtime import run_connector_poll_with_retries
from scripts.stage2.intake_api import AuthContext as IntakeAuth
from scripts.stage2.intake_api import create_intake_session_persisted
from scripts.stage2.intake_api import update_intake_session_persisted
from scripts.stage2.sqlite_repository import Stage2SQLiteRepository
from scripts.stage2.status_sync import AuthContext as SyncAuth
from scripts.stage2.sync_api import get_status_timeline_persisted


class Stage2Slice9SQLiteRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.repo = Stage2SQLiteRepository()
        self.now = datetime(2026, 3, 3, 20, 0, tzinfo=timezone.utc)
        self.org_id = "3550f393-cf47-46e9-b146-19d6fbe7e910"
        self.project_id = "7a6dc13a-34a6-4fce-9f01-8d97f36d3d35"
        self.permit_id = "f199bac0-85c9-4ca7-9586-c2f3309bc39a"

    def tearDown(self):
        self.repo.close()

    def test_persisted_intake_idempotency_with_sqlite_repo(self):
        auth = IntakeAuth(
            organization_id=self.org_id,
            requester_role="admin",
            user_id="19a6140e-46de-42dd-839d-b7b4f3df8a0f",
        )
        s1, first = create_intake_session_persisted(
            project_id=self.project_id,
            permit_type="commercial_ti",
            ahj_id="ca.san_jose.building",
            seed_answers={},
            idempotency_key="idem-sqlite-intake-1",
            trace_id="trc-sqlite-intake-1",
            auth_context=auth,
            repository=self.repo,
            now=self.now,
        )
        s2, second = create_intake_session_persisted(
            project_id=self.project_id,
            permit_type="commercial_ti",
            ahj_id="ca.san_jose.building",
            seed_answers={},
            idempotency_key="idem-sqlite-intake-1",
            trace_id="trc-sqlite-intake-2",
            auth_context=auth,
            repository=self.repo,
            now=self.now,
        )
        self.assertEqual(s1, 201)
        self.assertEqual(s2, 200)
        self.assertEqual(first["session_id"], second["session_id"])
        self.assertEqual(self.repo.count_rows("intake_sessions"), 1)

        update_intake_session_persisted(
            session_id=first["session_id"],
            if_match_version=1,
            payload={
                "answers_patch": {
                    "project_name": "Alpha",
                    "project_address_line1": "1 Main",
                    "city": "San Jose",
                    "state": "CA",
                    "postal_code": "95113",
                    "scope_summary": "Scope",
                    "valuation_usd": 5000,
                    "owner_legal_name": "Owner",
                    "applicant_email": "pm@example.com",
                    "contractor_company_name": "BuildCo",
                    "building_area_sqft": 1000,
                    "sprinklered_flag": True,
                },
                "status": "completed",
            },
            trace_id="trc-sqlite-intake-3",
            auth_context=auth,
            repository=self.repo,
            now=self.now,
        )
        self.assertEqual(self.repo.count_rows("stage2_event_outbox"), 1)

    def test_connector_runtime_retry_and_timeline_with_sqlite_repo(self):
        sync_auth = SyncAuth(organization_id=self.org_id, requester_role="admin")
        calls = {"count": 0}

        def flaky_client(*, ahj_id: str):
            calls["count"] += 1
            if calls["count"] == 1:
                raise ConnectorPollError("temporary upstream failure", retryable=True)
            return [
                ConnectorObservation(
                    permit_id=self.permit_id,
                    raw_status="Under Review",
                    source="accela_api",
                    observed_at=self.now,
                    parser_version="v1",
                    source_ref=f"{ahj_id}/cases/123",
                )
            ]

        result = run_connector_poll_with_retries(
            ahj_id="ca.san_jose.building",
            idempotency_key="idem-sqlite-poll-1",
            trace_id="trc-sqlite-poll-1",
            auth_context=sync_auth,
            adapter=AccelaApiAdapter(flaky_client),
            repository=self.repo,
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
            max_attempts=3,
            now=self.now,
        )

        self.assertEqual(result["run"]["status"], "succeeded")
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(result["observations_applied"], 1)
        self.assertEqual(result["observations_reviewed"], 0)
        self.assertEqual(self.repo.count_rows("portal_sync_runs"), 1)
        self.assertEqual(self.repo.count_rows("permit_status_events"), 1)
        self.assertGreaterEqual(self.repo.count_rows("stage2_event_outbox"), 1)

        _, timeline = get_status_timeline_persisted(
            permit_id=self.permit_id,
            query_params={},
            auth_context=sync_auth,
            repository=self.repo,
        )
        self.assertEqual(len(timeline["timeline"]), 1)
        self.assertEqual(timeline["timeline"][0]["normalized_status"], "in_review")

    def test_low_confidence_lexical_does_not_apply_or_emit_status_changed(self):
        sync_auth = SyncAuth(organization_id=self.org_id, requester_role="admin")

        def first_client(*, ahj_id: str):
            return [
                ConnectorObservation(
                    permit_id=self.permit_id,
                    raw_status="Submitted",
                    source="accela_api",
                    observed_at=self.now,
                    parser_version="v1",
                    source_ref=f"{ahj_id}/cases/1",
                )
            ]

        run_connector_poll_with_retries(
            ahj_id="ca.san_jose.building",
            idempotency_key="idem-sqlite-poll-lowconf-setup",
            trace_id="trc-sqlite-poll-lowconf-setup",
            auth_context=sync_auth,
            adapter=AccelaApiAdapter(first_client),
            repository=self.repo,
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
            max_attempts=1,
            now=self.now,
        )

        def lexical_client(*, ahj_id: str):
            return [
                ConnectorObservation(
                    permit_id=self.permit_id,
                    raw_status="Permit issued",
                    source="accela_api",
                    observed_at=self.now,
                    parser_version="v1",
                    source_ref=f"{ahj_id}/cases/1",
                )
            ]

        result = run_connector_poll_with_retries(
            ahj_id="ca.san_jose.building",
            idempotency_key="idem-sqlite-poll-lowconf",
            trace_id="trc-sqlite-poll-lowconf",
            auth_context=sync_auth,
            adapter=AccelaApiAdapter(lexical_client),
            repository=self.repo,
            rules=[],
            max_attempts=1,
            now=self.now,
        )
        self.assertEqual(result["observations_applied"], 0)
        self.assertEqual(result["observations_reviewed"], 1)

        projection = self.repo.get_status_projection(self.permit_id)
        self.assertEqual(projection["current_status"], "submitted")

        event_types = [
            r["event_type"]
            for r in self.repo.conn.execute(
                "SELECT event_type FROM stage2_event_outbox ORDER BY created_at ASC"
            ).fetchall()
        ]
        self.assertNotIn("permit.status_changed", event_types[-1:])

    def test_unmapped_status_does_not_emit_observed_event_or_apply(self):
        sync_auth = SyncAuth(organization_id=self.org_id, requester_role="admin")

        def unmapped_client(*, ahj_id: str):
            return [
                ConnectorObservation(
                    permit_id=self.permit_id,
                    raw_status="Awaiting City Analyst Triage",
                    source="accela_api",
                    observed_at=self.now,
                    parser_version="v1",
                    source_ref=f"{ahj_id}/cases/2",
                )
            ]

        before_outbox = self.repo.count_rows("stage2_event_outbox")
        result = run_connector_poll_with_retries(
            ahj_id="ca.san_jose.building",
            idempotency_key="idem-sqlite-poll-unmapped",
            trace_id="trc-sqlite-poll-unmapped",
            auth_context=sync_auth,
            adapter=AccelaApiAdapter(unmapped_client),
            repository=self.repo,
            rules=[],
            max_attempts=1,
            now=self.now,
        )
        self.assertEqual(result["observations_applied"], 0)
        self.assertEqual(result["observations_reviewed"], 1)
        self.assertEqual(self.repo.count_rows("stage2_event_outbox"), before_outbox)
        self.assertIsNone(self.repo.get_status_projection(self.permit_id))
        self.assertEqual(self.repo.count_rows("status_drift_alerts"), 1)

    def test_drift_alert_can_be_marked_resolved(self):
        sync_auth = SyncAuth(organization_id=self.org_id, requester_role="admin")

        def unmapped_client(*, ahj_id: str):
            return [
                ConnectorObservation(
                    permit_id=self.permit_id,
                    raw_status="Awaiting Staff Assignment",
                    source="accela_api",
                    observed_at=self.now,
                    parser_version="v1",
                    source_ref=f"{ahj_id}/cases/99",
                )
            ]

        run_connector_poll_with_retries(
            ahj_id="ca.san_jose.building",
            idempotency_key="idem-sqlite-poll-drift-resolve",
            trace_id="trc-sqlite-poll-drift-resolve",
            auth_context=sync_auth,
            adapter=AccelaApiAdapter(unmapped_client),
            repository=self.repo,
            rules=[],
            max_attempts=1,
            now=self.now,
        )
        alerts = self.repo.list_drift_alerts_by_org(self.org_id)
        self.assertGreaterEqual(len(alerts), 1)
        updated = self.repo.update_drift_alert_status(
            organization_id=self.org_id,
            alert_id=alerts[0]["id"],
            status="resolved",
        )
        self.assertEqual(updated["status"], "resolved")

    def test_ops_listing_helpers_return_recent_runs_and_reviews(self):
        sync_auth = SyncAuth(organization_id=self.org_id, requester_role="admin")

        def client(*, ahj_id: str):
            return [
                ConnectorObservation(
                    permit_id=self.permit_id,
                    raw_status="Under review",
                    source="accela_api",
                    observed_at=self.now,
                    parser_version="v1",
                    source_ref=f"{ahj_id}/cases/3",
                )
            ]

        run_connector_poll_with_retries(
            ahj_id="ca.san_jose.building",
            idempotency_key="idem-sqlite-poll-listing",
            trace_id="trc-sqlite-poll-listing",
            auth_context=sync_auth,
            adapter=AccelaApiAdapter(client),
            repository=self.repo,
            rules=[],
            max_attempts=1,
            now=self.now,
        )

        runs = self.repo.list_recent_poll_runs(organization_id=self.org_id, limit=5)
        self.assertGreaterEqual(len(runs), 1)
        self.assertIn(runs[0]["status"], {"succeeded", "partial", "failed"})

        reviews = self.repo.list_transition_reviews_by_org(
            organization_id=self.org_id,
            resolution_state="open",
            limit=10,
        )
        self.assertGreaterEqual(len(reviews), 1)
        self.assertEqual(reviews[0]["resolution_state"], "open")
        updated_review = self.repo.update_transition_review_resolution(
            organization_id=self.org_id,
            review_id=reviews[0]["id"],
            resolution_state="resolved",
        )
        self.assertEqual(updated_review["resolution_state"], "resolved")

        recon = self.repo.list_recent_reconciliation_runs_by_org(organization_id=self.org_id, limit=5)
        self.assertEqual(recon, [])

        alerts = self.repo.list_drift_alerts_by_org(self.org_id)
        self.assertEqual(alerts, [])

    def test_connector_credentials_upsert_get_and_list(self):
        record = self.repo.upsert_connector_credential(
            organization_id=self.org_id,
            connector="accela_api",
            ahj_id=None,
            credential={
                "credential_ref": "accela_prod_token",
                "auth_scheme": "bearer",
                "scopes_json": ["records:read"],
                "status": "active",
                "created_by": "owner-user",
            },
        )
        self.assertEqual(record["credential_ref"], "accela_prod_token")

        fetched = self.repo.get_connector_credential(
            organization_id=self.org_id,
            connector="accela_api",
            ahj_id="ca.san_jose.building",
        )
        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched["credential_ref"], "accela_prod_token")

        rotated = self.repo.upsert_connector_credential(
            organization_id=self.org_id,
            connector="accela_api",
            ahj_id=None,
            credential={
                "credential_ref": "accela_rotated_token",
                "auth_scheme": "bearer",
                "scopes_json": ["records:read"],
                "status": "active",
                "created_by": "owner-user",
            },
        )
        self.assertEqual(rotated["credential_ref"], "accela_rotated_token")

        items = self.repo.list_connector_credentials(
            organization_id=self.org_id,
            connector="accela_api",
            limit=10,
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["credential_ref"], "accela_rotated_token")


if __name__ == "__main__":
    unittest.main()
