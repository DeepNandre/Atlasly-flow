import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class Stage0ContractTests(unittest.TestCase):
    def test_openapi_contains_required_stage0_endpoints(self):
        path = ROOT / "contracts/stage0/foundation.v1.openapi.yaml"
        self.assertTrue(path.exists(), f"missing {path}")
        body = path.read_text()
        required_tokens = [
            "/orgs:",
            "/orgs/{orgId}/users:",
            "/projects:",
            "/projects/{projectId}/documents:",
            "/projects/{projectId}/tasks:",
            "/tasks/{taskId}:",
            "/projects/{projectId}/timeline:",
            "Idempotency-Key",
            "If-Match",
            '"201":',
            '"412":',
        ]
        for token in required_tokens:
            self.assertIn(token, body)

    def test_event_envelope_contract_contains_stage0_events(self):
        path = ROOT / "contracts/stage0/event-envelope-v1.json"
        self.assertTrue(path.exists(), f"missing {path}")
        body = path.read_text()
        required_tokens = [
            '"event_id"',
            '"event_type"',
            '"document.uploaded"',
            '"document.ocr_completed"',
            '"task.created"',
            '"task.assigned"',
            '"permit.status_changed"',
            '"signature"',
            '"idempotency_key"',
        ]
        for token in required_tokens:
            self.assertIn(token, body)


if __name__ == "__main__":
    unittest.main()

