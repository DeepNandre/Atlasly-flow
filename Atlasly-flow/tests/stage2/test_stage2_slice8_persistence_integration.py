from datetime import datetime, timezone
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.stage2.intake_api import AuthContext as IntakeAuth
from scripts.stage2.intake_api import create_intake_session_persisted
from scripts.stage2.intake_api import generate_permit_application_persisted
from scripts.stage2.intake_api import update_intake_session_persisted
from scripts.stage2.reconciliation_runtime import run_permit_reconciliation
from scripts.stage2.repositories import Stage2PersistenceStore
from scripts.stage2.repositories import Stage2Repository
from scripts.stage2.status_sync import AuthContext as SyncAuth
from scripts.stage2.status_sync import record_status_observation_persisted
from scripts.stage2.sync_api import get_status_timeline_persisted
from scripts.stage2.sync_api import post_connector_poll_persisted


class Stage2Slice8PersistenceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 3, 3, 19, 0, tzinfo=timezone.utc)
        self.org_id = "3550f393-cf47-46e9-b146-19d6fbe7e910"
        self.project_id = "7a6dc13a-34a6-4fce-9f01-8d97f36d3d35"
        self.permit_id = "f199bac0-85c9-4ca7-9586-c2f3309bc39a"
        self.repo = Stage2Repository(Stage2PersistenceStore.empty())
        self.intake_auth = IntakeAuth(
            organization_id=self.org_id,
            requester_role="admin",
            user_id="19a6140e-46de-42dd-839d-b7b4f3df8a0f",
        )
        self.sync_auth = SyncAuth(organization_id=self.org_id, requester_role="admin")

    def test_intake_to_application_persisted_flow(self):
        _, session = create_intake_session_persisted(
            project_id=self.project_id,
            permit_type="commercial_ti",
            ahj_id="ca.san_jose.building",
            seed_answers={},
            idempotency_key="idem-persist-intake-1",
            trace_id="trc-persist-intake-1",
            auth_context=self.intake_auth,
            repository=self.repo,
            now=self.now,
        )
        update_intake_session_persisted(
            session_id=session["session_id"],
            if_match_version=1,
            payload={
                "answers_patch": {
                    "project_name": "Alpha TI",
                    "project_address_line1": "1 Main St",
                    "city": "San Jose",
                    "state": "CA",
                    "postal_code": "95113",
                    "scope_summary": "Tenant improvement scope",
                    "valuation_usd": 50000,
                    "owner_legal_name": "Owner LLC",
                    "applicant_email": "pm@example.com",
                    "contractor_company_name": "BuildCo",
                    "building_area_sqft": 1800,
                    "sprinklered_flag": True,
                },
                "status": "completed",
            },
            trace_id="trc-persist-intake-2",
            auth_context=self.intake_auth,
            repository=self.repo,
            now=self.now,
        )

        _, app = generate_permit_application_persisted(
            permit_id=self.permit_id,
            intake_session_id=session["session_id"],
            form_template_id="tmpl-ti-001",
            mapping_version=1,
            required_mapped_fields={
                "project_name",
                "project_address_line1",
                "city",
                "state",
                "postal_code",
                "scope_summary",
                "valuation_usd",
                "owner_legal_name",
                "applicant_email",
                "contractor_company_name",
                "building_area_sqft",
                "sprinklered_flag",
            },
            idempotency_key="idem-persist-app-1",
            trace_id="trc-persist-app-1",
            auth_context=self.intake_auth,
            repository=self.repo,
            now=self.now,
        )
        self.assertEqual(app["permit_id"], self.permit_id)
        event_types = {e["event_type"] for e in self.repo._store.outbox_events.values()}
        self.assertIn("intake.completed", event_types)
        self.assertIn("permit.application_generated", event_types)

    def test_sync_timeline_and_reconciliation_persisted_flow(self):
        post_connector_poll_persisted(
            ahj="ca.san_jose.building",
            request_body={"connector": "accela_api"},
            idempotency_key="idem-persist-poll-1",
            auth_context=self.sync_auth,
            repository=self.repo,
            now=self.now,
        )

        record_status_observation_persisted(
            permit_id=self.permit_id,
            source="accela_api",
            raw_status="Submitted",
            old_status=None,
            organization_id=self.org_id,
            connector="accela_api",
            ahj_id="ca.san_jose.building",
            observed_at=self.now,
            parser_version="v1",
            event_hash="evt_hash_persist_1",
            trace_id="trc-persist-sync-1",
            idempotency_key="idem-persist-sync-1",
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
            repository=self.repo,
        )

        _, timeline = get_status_timeline_persisted(
            permit_id=self.permit_id,
            query_params={},
            auth_context=self.sync_auth,
            repository=self.repo,
        )
        self.assertEqual(len(timeline["timeline"]), 1)
        self.assertEqual(timeline["timeline"][0]["normalized_status"], "submitted")

        result = run_permit_reconciliation(
            organization_id=self.org_id,
            permit_id=self.permit_id,
            connector="accela_api",
            ahj_id="ca.san_jose.building",
            current_ruleset_version="v2",
            previous_ruleset_version="v1",
            rules=[
                {
                    "connector": "accela_api",
                    "ahj_id": "ca.san_jose.building",
                    "match_type": "exact",
                    "raw_pattern": "Submitted",
                    "normalized_status": "approved",
                    "confidence_score": 0.99,
                    "priority": 1,
                    "is_active": True,
                }
            ],
            repository=self.repo,
            now=self.now,
        )
        self.assertEqual(result["run"]["status"], "mismatched")
        self.assertGreaterEqual(len(result["alerts"]), 1)


if __name__ == "__main__":
    unittest.main()
