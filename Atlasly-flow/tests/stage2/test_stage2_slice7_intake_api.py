from datetime import datetime, timezone
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.stage2.intake_api import AuthContext
from scripts.stage2.intake_api import IntakeRequestError
from scripts.stage2.intake_api import IntakeStore
from scripts.stage2.intake_api import create_intake_session
from scripts.stage2.intake_api import generate_permit_application
from scripts.stage2.intake_api import update_intake_session


class Stage2Slice7IntakeApiTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 3, 3, 18, 0, tzinfo=timezone.utc)
        self.org_id = "3550f393-cf47-46e9-b146-19d6fbe7e910"
        self.project_id = "7a6dc13a-34a6-4fce-9f01-8d97f36d3d35"
        self.permit_id = "f199bac0-85c9-4ca7-9586-c2f3309bc39a"
        self.auth = AuthContext(
            organization_id=self.org_id,
            requester_role="admin",
            user_id="19a6140e-46de-42dd-839d-b7b4f3df8a0f",
        )
        self.store = IntakeStore.empty()

    def test_create_intake_session_and_idempotent_replay(self):
        status1, session1 = create_intake_session(
            project_id=self.project_id,
            permit_type="commercial_ti",
            ahj_id="ca.san_jose.building",
            seed_answers={"project_name": "Alpha TI"},
            idempotency_key="idem-intake-001",
            trace_id="trc-intake-001",
            auth_context=self.auth,
            store=self.store,
            now=self.now,
        )
        status2, session2 = create_intake_session(
            project_id=self.project_id,
            permit_type="commercial_ti",
            ahj_id="ca.san_jose.building",
            seed_answers={"project_name": "Alpha TI"},
            idempotency_key="idem-intake-001",
            trace_id="trc-intake-002",
            auth_context=self.auth,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(status1, 201)
        self.assertEqual(status2, 200)
        self.assertEqual(session1["session_id"], session2["session_id"])

    def test_complete_intake_emits_event(self):
        _, session = create_intake_session(
            project_id=self.project_id,
            permit_type="commercial_ti",
            ahj_id="ca.san_jose.building",
            seed_answers={},
            idempotency_key="idem-intake-003",
            trace_id="trc-intake-003",
            auth_context=self.auth,
            store=self.store,
            now=self.now,
        )

        status, updated = update_intake_session(
            session_id=session["session_id"],
            if_match_version=1,
            payload={
                "answers_patch": {
                    "project_name": "Alpha TI",
                    "project_address_line1": "1 Main St",
                    "city": "San Jose",
                    "state": "CA",
                    "postal_code": "95113",
                    "scope_summary": "Tenant improvement of existing shell",
                    "valuation_usd": 120000,
                    "owner_legal_name": "Owner LLC",
                    "applicant_email": "pm@example.com",
                    "contractor_company_name": "BuildCo",
                    "building_area_sqft": 3000,
                    "sprinklered_flag": True,
                },
                "status": "completed",
            },
            trace_id="trc-intake-004",
            auth_context=self.auth,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(status, 200)
        self.assertEqual(updated["status"], "completed")
        self.assertEqual(len(self.store.outbox_events), 1)
        self.assertEqual(self.store.outbox_events[0]["event_type"], "intake.completed")
        self.assertEqual(self.store.outbox_events[0]["event_version"], 1)

    def test_stale_version_conflict(self):
        _, session = create_intake_session(
            project_id=self.project_id,
            permit_type="commercial_ti",
            ahj_id="ca.san_jose.building",
            seed_answers={},
            idempotency_key="idem-intake-005",
            trace_id="trc-intake-005",
            auth_context=self.auth,
            store=self.store,
            now=self.now,
        )
        with self.assertRaises(IntakeRequestError) as ctx:
            update_intake_session(
                session_id=session["session_id"],
                if_match_version=99,
                payload={"answers_patch": {"project_name": "Mismatch"}},
                trace_id="trc-intake-006",
                auth_context=self.auth,
                store=self.store,
                now=self.now,
            )
        self.assertEqual(ctx.exception.status, 409)

    def test_generate_permit_application_emits_event(self):
        _, session = create_intake_session(
            project_id=self.project_id,
            permit_type="rooftop_solar",
            ahj_id="ca.san_diego.dsd",
            seed_answers={},
            idempotency_key="idem-intake-007",
            trace_id="trc-intake-007",
            auth_context=self.auth,
            store=self.store,
            now=self.now,
        )
        update_intake_session(
            session_id=session["session_id"],
            if_match_version=1,
            payload={
                "answers_patch": {
                    "project_name": "Solar Rooftop",
                    "project_address_line1": "2 Main St",
                    "city": "San Diego",
                    "state": "CA",
                    "postal_code": "92101",
                    "scope_summary": "Install rooftop solar on commercial building",
                    "valuation_usd": 80000,
                    "owner_legal_name": "Owner Solar LLC",
                    "applicant_email": "solar@example.com",
                    "contractor_company_name": "SolarCo",
                    "solar_kw_dc": 250.5,
                    "solar_inverter_count": 6,
                    "contractor_license_number": "LIC12345",
                },
                "status": "completed",
            },
            trace_id="trc-intake-008",
            auth_context=self.auth,
            store=self.store,
            now=self.now,
        )

        required_fields = {
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
            "solar_kw_dc",
            "solar_inverter_count",
            "contractor_license_number",
        }
        status, app = generate_permit_application(
            permit_id=self.permit_id,
            intake_session_id=session["session_id"],
            form_template_id="tmpl-solar-001",
            mapping_version=1,
            required_mapped_fields=required_fields,
            idempotency_key="idem-appgen-001",
            trace_id="trc-appgen-001",
            auth_context=self.auth,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(status, 201)
        self.assertEqual(app["permit_id"], self.permit_id)
        event_types = [e["event_type"] for e in self.store.outbox_events]
        self.assertIn("permit.application_generated", event_types)

    def test_generate_application_missing_mapping_fails(self):
        _, session = create_intake_session(
            project_id=self.project_id,
            permit_type="commercial_ti",
            ahj_id="ca.san_jose.building",
            seed_answers={},
            idempotency_key="idem-intake-009",
            trace_id="trc-intake-009",
            auth_context=self.auth,
            store=self.store,
            now=self.now,
        )
        update_intake_session(
            session_id=session["session_id"],
            if_match_version=1,
            payload={
                "answers_patch": {
                    "project_name": "Alpha TI",
                    "project_address_line1": "1 Main St",
                    "city": "San Jose",
                    "state": "CA",
                    "postal_code": "95113",
                    "scope_summary": "Tenant improvement",
                    "valuation_usd": 10000,
                    "owner_legal_name": "Owner",
                    "applicant_email": "a@b.com",
                    "contractor_company_name": "BuildCo",
                    "building_area_sqft": 1200,
                    "sprinklered_flag": True,
                },
                "status": "completed",
            },
            trace_id="trc-intake-010",
            auth_context=self.auth,
            store=self.store,
            now=self.now,
        )
        with self.assertRaises(IntakeRequestError) as ctx:
            generate_permit_application(
                permit_id=self.permit_id,
                intake_session_id=session["session_id"],
                form_template_id="tmpl-ti-001",
                mapping_version=1,
                required_mapped_fields={"project_name"},
                idempotency_key="idem-appgen-002",
                trace_id="trc-appgen-002",
                auth_context=self.auth,
                store=self.store,
                now=self.now,
            )
        self.assertEqual(ctx.exception.status, 422)


if __name__ == "__main__":
    unittest.main()
