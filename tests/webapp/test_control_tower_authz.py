from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.webapp_server import DemoAppState
from scripts.webapp_server import SessionAuthError
from scripts.stage0_5.enterprise_service import EnterpriseReadinessError


class ControlTowerAuthzTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = DemoAppState()
        self.bootstrap_payload = self.state.bootstrap()

    def tearDown(self) -> None:
        self.state.stage2_repo.close()
        self.state.stage3_store.repository.close()
        if self.state.runtime_store is not None:
            self.state.runtime_store.close()

    def _token_for_role(self, role: str) -> str:
        sessions = self.bootstrap_payload.get("sessions", [])
        for session in sessions:
            if session.get("role") == role:
                return str(session["token"])
        self.fail(f"missing token for role {role}")

    def test_bootstrap_emits_sessions_for_all_roles(self):
        roles = {session["role"] for session in self.bootstrap_payload.get("sessions", [])}
        self.assertEqual(roles, {"owner", "admin", "pm", "reviewer", "subcontractor"})

    def test_missing_token_rejected_for_protected_route(self):
        allowed = self.state.allowed_roles_for_route(method="GET", path="/api/portfolio")
        self.assertIsNotNone(allowed)
        with self.assertRaises(SessionAuthError) as ctx:
            self.state.require_session(token="", allowed_roles=allowed)
        self.assertEqual(ctx.exception.status, 401)

    def test_demo_reset_is_unprotected_route(self):
        allowed = self.state.allowed_roles_for_route(method="POST", path="/api/demo/reset")
        self.assertIsNone(allowed)

    def test_demo_routes_are_blocked_in_mvp_tier(self):
        self.state.deployment_tier = "mvp"
        self.state.demo_routes_enabled = False
        allowed = self.state.allowed_roles_for_route(method="POST", path="/api/demo/reset")
        self.assertEqual(allowed, {"owner", "admin"})

    def test_role_escalation_blocked_on_enterprise_write(self):
        pm_token = self._token_for_role("pm")
        allowed = self.state.allowed_roles_for_route(method="POST", path="/api/enterprise/api-keys")
        self.assertEqual(allowed, {"owner", "admin"})
        with self.assertRaises(SessionAuthError) as ctx:
            self.state.require_session(token=pm_token, allowed_roles=allowed)
        self.assertEqual(ctx.exception.status, 403)

    def test_pm_cannot_access_enterprise_audit_evidence_read(self):
        pm_token = self._token_for_role("pm")
        allowed = self.state.allowed_roles_for_route(method="GET", path="/api/enterprise/audit-evidence")
        self.assertEqual(allowed, {"owner", "admin"})
        with self.assertRaises(SessionAuthError) as ctx:
            self.state.require_session(token=pm_token, allowed_roles=allowed)
        self.assertEqual(ctx.exception.status, 403)

    def test_reviewer_can_access_enterprise_integration_readiness(self):
        reviewer_token = self._token_for_role("reviewer")
        allowed = self.state.allowed_roles_for_route(method="GET", path="/api/enterprise/integrations-readiness")
        self.assertEqual(allowed, {"owner", "admin", "pm", "reviewer"})
        session = self.state.require_session(token=reviewer_token, allowed_roles=allowed)
        self.assertEqual(session["role"], "reviewer")

    def test_reviewer_can_access_enterprise_launch_readiness(self):
        reviewer_token = self._token_for_role("reviewer")
        allowed = self.state.allowed_roles_for_route(method="GET", path="/api/enterprise/launch-readiness")
        self.assertEqual(allowed, {"owner", "admin", "pm", "reviewer"})
        session = self.state.require_session(token=reviewer_token, allowed_roles=allowed)
        self.assertEqual(session["role"], "reviewer")

    def test_reviewer_cannot_execute_stage2_write_routes(self):
        reviewer_token = self._token_for_role("reviewer")
        allowed = self.state.allowed_roles_for_route(method="POST", path="/api/stage2/intake-complete")
        self.assertEqual(allowed, {"owner", "admin", "pm"})
        with self.assertRaises(SessionAuthError) as ctx:
            self.state.require_session(token=reviewer_token, allowed_roles=allowed)
        self.assertEqual(ctx.exception.status, 403)

    def test_owner_can_access_finance_write_routes(self):
        owner_token = self._token_for_role("owner")
        allowed = self.state.allowed_roles_for_route(method="POST", path="/api/stage3/payout")
        self.assertEqual(allowed, {"owner", "admin"})
        session = self.state.require_session(token=owner_token, allowed_roles=allowed)
        self.assertEqual(session["role"], "owner")

    def test_cross_tenant_token_rejected(self):
        owner_token = self._token_for_role("owner")
        self.state.sessions_by_token[owner_token]["organization_id"] = "org-other"
        allowed = self.state.allowed_roles_for_route(method="GET", path="/api/activity")
        with self.assertRaises(SessionAuthError) as ctx:
            self.state.require_session(token=owner_token, allowed_roles=allowed)
        self.assertEqual(ctx.exception.status, 403)

    def test_enterprise_boundary_rejects_in_memory_on_mvp(self):
        self.state.deployment_tier = "mvp"
        self.state.stage05_runtime_backend = "in_memory"
        self.state.stage05_persistence_ready = False
        with self.assertRaises(EnterpriseReadinessError):
            self.state.enterprise_ops(limit=5)


if __name__ == "__main__":
    unittest.main()
