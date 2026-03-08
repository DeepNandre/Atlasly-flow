import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class Stage05ContractTests(unittest.TestCase):
    def test_openapi_files_exist_and_include_required_paths(self):
        required = {
            "contracts/stage0_5/apis/webhooks.v1.openapi.yaml": ["/webhooks:", "Idempotency-Key", '"201":'],
            "contracts/stage0_5/apis/webhook-events.v1.openapi.yaml": ["/webhook-events:", "attempt_gte", '"200":'],
            "contracts/stage0_5/apis/connectors-sync.v1.openapi.yaml": ["/connectors/{name}/sync:", "run_mode", '"202":'],
            "contracts/stage0_5/apis/dashboard-portfolio.v1.openapi.yaml": ["/dashboard/portfolio:", "freshness_seconds"],
            "contracts/stage0_5/apis/org-api-keys.v1.openapi.yaml": ["/orgs/{orgId}/api-keys:", "scopes", "audit:read"],
            "contracts/stage0_5/apis/control-tower.v1.openapi.yaml": [
                "/api/portfolio:",
                "/api/activity:",
                "/api/permit-ops:",
                "/api/finance-ops:",
                "/api/permit-ops/resolve-transition:",
                "/api/permit-ops/resolve-drift:",
                "/api/enterprise/overview:",
                "/api/enterprise/webhook-events:",
                "/api/enterprise/dashboard:",
                "/api/enterprise/alerts:",
                "/api/enterprise/slo:",
                "/api/enterprise/audit-evidence:",
                "/api/enterprise/webhooks:",
                "/api/enterprise/webhook-delivery:",
                "/api/enterprise/webhook-replay:",
                "/api/enterprise/connector-sync:",
                "/api/enterprise/connector-complete:",
                "/api/enterprise/api-keys:",
                "/api/enterprise/api-keys/mark-used:",
                "/api/enterprise/api-keys/policy-scan:",
                "/api/enterprise/api-keys/rotate:",
                "/api/enterprise/api-keys/revoke:",
                "/api/enterprise/task-templates:",
                "/api/enterprise/task-templates/archive:",
                "/api/enterprise/audit-exports/request:",
                "/api/enterprise/audit-exports/run:",
                "/api/enterprise/audit-exports/complete:",
                "/api/enterprise/dashboard-snapshot:",
                "/api/stage1a/upload:",
                "/api/stage1a/process-upload:",
                "/api/stage1a/quality-report:",
                "/api/stage1b/routing-audit:",
                "/api/stage1b/escalation-tick:",
                "/api/sessions:",
                "/api/demo/reset:",
                "/api/feedback:",
                "/api/telemetry:",
                "/api/stage2/resolve-ahj:",
                "/api/stage2/connector-credentials:",
                "/api/stage2/connector-credentials/rotate:",
                "/api/stage2/poll-live:",
                "/api/stage3/publish-outbox:",
                "bearerAuth",
                "success_rate",
                "state_breakdown",
                "dead_letter_total",
            ],
        }
        for rel, tokens in required.items():
            path = ROOT / rel
            self.assertTrue(path.exists(), f"missing {path}")
            body = path.read_text()
            for token in tokens:
                self.assertIn(token, body)

    def test_event_schema_files_exist_and_reference_required_fields(self):
        required = {
            "contracts/stage0_5/events/integration.run_started.v1.schema.json": [
                '"connector"',
                '"organization_id"',
                '"run_id"',
                '"started_at"',
            ],
            "contracts/stage0_5/events/integration.run_completed.v1.schema.json": [
                '"run_id"',
                '"status"',
                '"duration_ms"',
                '"records_synced"',
            ],
            "contracts/stage0_5/events/webhook.delivery_failed.v1.schema.json": [
                '"subscription_id"',
                '"event_id"',
                '"attempt"',
                '"error_code"',
            ],
        }
        for rel, tokens in required.items():
            path = ROOT / rel
            self.assertTrue(path.exists(), f"missing {path}")
            body = path.read_text()
            for token in tokens:
                self.assertIn(token, body)


if __name__ == "__main__":
    unittest.main()
