from datetime import datetime, timedelta, timezone
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.stage0_5.enterprise_service import AuthContext
from scripts.stage0_5.enterprise_service import EnterpriseReadinessError
from scripts.stage0_5.enterprise_service import EnterpriseStore
from scripts.stage0_5.enterprise_service import record_webhook_delivery_attempt
from scripts.stage0_5.enterprise_service import request_webhook_replay
from scripts.stage0_5.runtime_api import post_webhooks


class Stage05WebhookFailureModeTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 3, 3, 21, 0, tzinfo=timezone.utc)
        self.org_id = "3550f393-cf47-46e9-b146-19d6fbe7e910"
        self.auth_admin = AuthContext(
            organization_id=self.org_id,
            requester_role="admin",
            user_id="46a2f8de-a9ff-447c-805a-78359a2d1892",
        )
        self.auth_pm = AuthContext(
            organization_id=self.org_id,
            requester_role="pm",
            user_id="7d33ec20-472f-4d71-952a-d06a77250322",
        )
        self.store = EnterpriseStore.empty()
        status, payload = post_webhooks(
            request_body={
                "target_url": "https://hooks.example.com/ops",
                "event_types": ["task.created"],
            },
            headers={"Idempotency-Key": "idem-ops-1", "X-Trace-Id": "trc-ops-1"},
            auth_context=self.auth_admin,
            store=self.store,
            now=self.now,
            runtime_backend="sql_functions",
            deployment_tier="mvp",
            persistence_ready=True,
        )
        self.assertEqual(status, 201)
        self.subscription_id = payload["subscription_id"]

    def test_non_retryable_4xx_is_terminal_and_dead_lettered(self):
        delivery = record_webhook_delivery_attempt(
            subscription_id=self.subscription_id,
            event_id="evt-nonretry-1",
            event_name="task.created",
            payload={"task_id": "t-1"},
            attempt=1,
            response_code=400,
            error_code="bad_request",
            error_detail="invalid payload",
            trace_id="trc-nonretry-1",
            auth_context=self.auth_admin,
            store=self.store,
            now=self.now,
        )

        self.assertEqual(delivery["status"], "failed_non_retryable")
        self.assertTrue(delivery["is_terminal"])
        self.assertIsNone(delivery["next_retry_at"])
        self.assertIn(delivery["delivery_id"], self.store.webhook_dead_letters_by_delivery)

        failed_events = [e for e in self.store.outbox_events if e["event_type"] == "webhook.delivery_failed"]
        self.assertEqual(len(failed_events), 1)

    def test_retry_schedule_edges_and_delivery_idempotent_dedupe(self):
        first = record_webhook_delivery_attempt(
            subscription_id=self.subscription_id,
            event_id="evt-retry-1",
            event_name="task.created",
            payload={"task_id": "t-2"},
            attempt=6,
            response_code=503,
            error_code="upstream_timeout",
            error_detail="timeout",
            trace_id="trc-retry-1",
            auth_context=self.auth_admin,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(first["status"], "retrying")
        scheduled = datetime.fromisoformat(first["next_retry_at"]).astimezone(timezone.utc)
        self.assertEqual(int((scheduled - self.now).total_seconds()), 28800)

        replay = record_webhook_delivery_attempt(
            subscription_id=self.subscription_id,
            event_id="evt-retry-1",
            event_name="task.created",
            payload={"task_id": "t-2"},
            attempt=6,
            response_code=503,
            error_code="upstream_timeout",
            error_detail="timeout",
            trace_id="trc-retry-2",
            auth_context=self.auth_admin,
            store=self.store,
            now=self.now + timedelta(seconds=1),
        )
        self.assertEqual(first["delivery_id"], replay["delivery_id"])

        terminal = record_webhook_delivery_attempt(
            subscription_id=self.subscription_id,
            event_id="evt-retry-1",
            event_name="task.created",
            payload={"task_id": "t-2"},
            attempt=7,
            response_code=503,
            error_code="upstream_timeout",
            error_detail="timeout",
            trace_id="trc-retry-3",
            auth_context=self.auth_admin,
            store=self.store,
            now=self.now + timedelta(seconds=2),
        )
        self.assertEqual(terminal["status"], "dead_lettered")
        self.assertIsNone(terminal["next_retry_at"])
        self.assertIn(terminal["delivery_id"], self.store.webhook_dead_letters_by_delivery)

    def test_replay_edge_cases_missing_dead_letter_and_forbidden_role(self):
        with self.assertRaises(EnterpriseReadinessError) as forbidden:
            request_webhook_replay(
                delivery_id="missing-delivery",
                reason="manual retry",
                auth_context=self.auth_pm,
                store=self.store,
                now=self.now,
            )
        self.assertEqual(forbidden.exception.status, 403)

        with self.assertRaises(EnterpriseReadinessError) as missing:
            request_webhook_replay(
                delivery_id="missing-delivery",
                reason="manual retry",
                auth_context=self.auth_admin,
                store=self.store,
                now=self.now,
            )
        self.assertEqual(missing.exception.status, 404)


if __name__ == "__main__":
    unittest.main()
