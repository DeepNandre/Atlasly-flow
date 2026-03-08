import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class ControlTowerContractTests(unittest.TestCase):
    def test_control_tower_openapi_contains_required_paths_and_keys(self):
        path = ROOT / "contracts/stage0_5/apis/control-tower.v1.openapi.yaml"
        self.assertTrue(path.exists(), f"missing {path}")
        body = path.read_text()
        for token in [
            "/api/portfolio:",
            "/api/activity:",
            "/api/permit-ops:",
            "/api/finance-ops:",
            "/api/enterprise/overview:",
            "/api/enterprise/webhook-events:",
            "/api/enterprise/dashboard:",
            "/api/enterprise/alerts:",
            "/api/enterprise/slo:",
            "/api/enterprise/integrations-readiness:",
            "/api/enterprise/launch-readiness:",
            "/api/enterprise/api-keys/policy-scan:",
            "/api/stage1a/quality-report:",
            "/api/stage1b/routing-audit:",
            "/api/stage3/payout:",
            "/api/stage3/provider-event:",
            "/api/stage3/reconcile:",
            "/api/sessions:",
            "/api/demo/reset:",
            "/api/demo/run-scenario:",
            "/api/feedback:",
            "/api/telemetry:",
            "/api/enterprise/webhooks:",
            "/api/enterprise/task-templates:",
            "/api/stage1a/extractions:",
            "/api/stage1a/review:",
            "/api/stage1b/assign:",
            "/api/stage2/poll-live:",
            "permit_status_breakdown",
            "transition_review_queue",
            "state_breakdown",
            "pending_count",
            "dead_letter_total",
            "integration_readiness",
            "launch_readiness",
            "transition_reviews",
            "payout_reconciliation",
        ]:
            self.assertIn(token, body)


if __name__ == "__main__":
    unittest.main()
