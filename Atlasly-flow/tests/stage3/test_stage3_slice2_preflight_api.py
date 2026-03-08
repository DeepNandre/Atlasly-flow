from datetime import datetime, timedelta, timezone
import unittest

from scripts.stage3.preflight_api import AuthContext
from scripts.stage3.preflight_api import PreflightRequestError
from scripts.stage3.preflight_api import get_preflight_risk


class Stage3Slice2PreflightApiTests(unittest.TestCase):
    def setUp(self):
        self.project_id = "7a6dc13a-34a6-4fce-9f01-8d97f36d3d35"
        self.now = datetime(2026, 3, 3, 10, 30, tzinfo=timezone.utc)
        self.project_record = {
            "organization_id": "3550f393-cf47-46e9-b146-19d6fbe7e910",
            "created_at": datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc),
        }
        self.auth = AuthContext(
            organization_id="3550f393-cf47-46e9-b146-19d6fbe7e910",
            requester_role="pm",
        )

    def test_happy_path_minimal_request(self):
        status, payload = get_preflight_risk(
            self.project_id,
            {
                "permit_type": "commercial_ti",
                "ahj_id": "ca.san_jose.building",
            },
            auth_context=self.auth,
            project_record=self.project_record,
            server_now=self.now,
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["permit_type"], "commercial_ti")
        self.assertEqual(payload["ahj_id"], "ca.san_jose.building")
        self.assertIn("risk_score", payload)
        self.assertIn("risk_band", payload)
        self.assertIn("confidence_score", payload)
        self.assertIn("top_risk_factors", payload)
        self.assertIn("recommended_actions", payload)

    def test_optional_flags_disable_sections(self):
        _, payload = get_preflight_risk(
            self.project_id,
            {
                "permit_type": "rooftop_solar",
                "ahj_id": "ca.san_diego.dsd",
                "include_recommendations": "false",
                "include_explainability": "false",
            },
            auth_context=self.auth,
            project_record=self.project_record,
            server_now=self.now,
        )
        self.assertNotIn("top_risk_factors", payload)
        self.assertNotIn("recommended_actions", payload)

    def test_missing_permit_type(self):
        with self.assertRaises(PreflightRequestError) as ctx:
            get_preflight_risk(
                self.project_id,
                {"ahj_id": "ca.san_jose.building"},
                auth_context=self.auth,
                project_record=self.project_record,
                server_now=self.now,
            )
        self.assertEqual(ctx.exception.status, 400)

    def test_unsupported_permit_type(self):
        with self.assertRaises(PreflightRequestError) as ctx:
            get_preflight_risk(
                self.project_id,
                {
                    "permit_type": "new_unknown_type",
                    "ahj_id": "ca.san_jose.building",
                },
                auth_context=self.auth,
                project_record=self.project_record,
                server_now=self.now,
            )
        self.assertEqual(ctx.exception.status, 422)

    def test_invalid_ahj_id_format(self):
        with self.assertRaises(PreflightRequestError) as ctx:
            get_preflight_risk(
                self.project_id,
                {
                    "permit_type": "commercial_ti",
                    "ahj_id": "CA/SAN-JOSE",
                },
                auth_context=self.auth,
                project_record=self.project_record,
                server_now=self.now,
            )
        self.assertEqual(ctx.exception.status, 422)

    def test_invalid_as_of(self):
        with self.assertRaises(PreflightRequestError) as ctx:
            get_preflight_risk(
                self.project_id,
                {
                    "permit_type": "commercial_ti",
                    "ahj_id": "ca.san_jose.building",
                    "as_of": "03-03-2026",
                },
                auth_context=self.auth,
                project_record=self.project_record,
                server_now=self.now,
            )
        self.assertEqual(ctx.exception.status, 422)

    def test_as_of_before_project_created(self):
        with self.assertRaises(PreflightRequestError) as ctx:
            get_preflight_risk(
                self.project_id,
                {
                    "permit_type": "commercial_ti",
                    "ahj_id": "ca.san_jose.building",
                    "as_of": "2026-02-01T00:00:00Z",
                },
                auth_context=self.auth,
                project_record=self.project_record,
                server_now=self.now,
            )
        self.assertEqual(ctx.exception.status, 422)

    def test_as_of_too_far_future(self):
        future = (self.now + timedelta(minutes=6)).isoformat().replace("+00:00", "Z")
        with self.assertRaises(PreflightRequestError) as ctx:
            get_preflight_risk(
                self.project_id,
                {
                    "permit_type": "commercial_ti",
                    "ahj_id": "ca.san_jose.building",
                    "as_of": future,
                },
                auth_context=self.auth,
                project_record=self.project_record,
                server_now=self.now,
            )
        self.assertEqual(ctx.exception.status, 422)

    def test_tenant_isolation(self):
        with self.assertRaises(PreflightRequestError) as ctx:
            get_preflight_risk(
                self.project_id,
                {
                    "permit_type": "commercial_ti",
                    "ahj_id": "ca.san_jose.building",
                },
                auth_context=AuthContext(
                    organization_id="bf72b0e8-0d5d-4f14-b3f3-b0f2f551f1ef",
                    requester_role="pm",
                ),
                project_record=self.project_record,
                server_now=self.now,
            )
        self.assertEqual(ctx.exception.status, 403)

    def test_deterministic_for_same_input(self):
        query = {
            "permit_type": "commercial_ti",
            "ahj_id": "ca.san_jose.building",
            "as_of": "2026-03-03T10:30:00Z",
        }
        _, first = get_preflight_risk(
            self.project_id,
            query,
            auth_context=self.auth,
            project_record=self.project_record,
            server_now=self.now,
        )
        _, second = get_preflight_risk(
            self.project_id,
            query,
            auth_context=self.auth,
            project_record=self.project_record,
            server_now=self.now,
        )
        self.assertEqual(first["risk_score"], second["risk_score"])
        self.assertEqual(first["model_version"], second["model_version"])


if __name__ == "__main__":
    unittest.main()
