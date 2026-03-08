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
from scripts.stage0_5.enterprise_service import archive_task_template
from scripts.stage0_5.enterprise_service import build_security_audit_evidence_pack
from scripts.stage0_5.enterprise_service import compute_ops_slo_snapshot
from scripts.stage0_5.enterprise_service import complete_connector_sync
from scripts.stage0_5.enterprise_service import create_task_template
from scripts.stage0_5.enterprise_service import mark_api_key_used
from scripts.stage0_5.enterprise_service import mark_security_audit_export_completed
from scripts.stage0_5.enterprise_service import mark_security_audit_export_failed
from scripts.stage0_5.enterprise_service import mark_security_audit_export_running
from scripts.stage0_5.enterprise_service import record_connector_error
from scripts.stage0_5.enterprise_service import record_webhook_delivery_attempt
from scripts.stage0_5.enterprise_service import request_security_audit_export
from scripts.stage0_5.enterprise_service import request_webhook_replay
from scripts.stage0_5.enterprise_service import rotate_api_key
from scripts.stage0_5.enterprise_service import scan_api_key_rotation_policy
from scripts.stage0_5.enterprise_service import upsert_dashboard_snapshot
from scripts.stage0_5.runtime_api import get_dashboard_portfolio_api
from scripts.stage0_5.runtime_api import get_webhook_events_api
from scripts.stage0_5.runtime_api import post_connector_sync
from scripts.stage0_5.runtime_api import post_org_api_keys
from scripts.stage0_5.runtime_api import post_webhooks


class Stage05RuntimeApiTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 3, 3, 20, 0, tzinfo=timezone.utc)
        self.org_id = "3550f393-cf47-46e9-b146-19d6fbe7e910"
        self.auth_owner = AuthContext(
            organization_id=self.org_id,
            requester_role="owner",
            user_id="4e2ae0f6-eb38-4f72-8868-7f24316d5d5f",
        )
        self.auth_admin = AuthContext(
            organization_id=self.org_id,
            requester_role="admin",
            user_id="7f57a88b-7bf4-4823-85de-2b8a1d3a5d45",
        )
        self.auth_pm = AuthContext(
            organization_id=self.org_id,
            requester_role="pm",
            user_id="4925bb89-a535-4589-9ec5-d52f2efe8dc7",
        )
        self.auth_reviewer = AuthContext(
            organization_id=self.org_id,
            requester_role="reviewer",
            user_id="c403d8be-8096-48f5-8cb2-2b8a51022b2f",
        )
        self.store = EnterpriseStore.empty()

    def test_webhook_registration_idempotency_and_listing(self):
        status1, body1 = post_webhooks(
            request_body={
                "target_url": "https://hooks.example.com/permit",
                "event_types": ["permit.status_changed", "task.created"],
            },
            headers={"Idempotency-Key": "idem-wh-1", "X-Trace-Id": "trc-wh-1"},
            auth_context=self.auth_admin,
            store=self.store,
            now=self.now,
        )
        status2, body2 = post_webhooks(
            request_body={
                "target_url": "https://hooks.example.com/permit",
                "event_types": ["permit.status_changed", "task.created"],
            },
            headers={"Idempotency-Key": "idem-wh-1", "X-Trace-Id": "trc-wh-2"},
            auth_context=self.auth_admin,
            store=self.store,
            now=self.now,
        )

        self.assertEqual(status1, 201)
        self.assertEqual(status2, 200)
        self.assertEqual(body1["subscription_id"], body2["subscription_id"])

        delivery = record_webhook_delivery_attempt(
            subscription_id=body1["subscription_id"],
            event_id="evt-wh-1",
            event_name="permit.status_changed",
            payload={"permit_id": "abc"},
            attempt=1,
            response_code=503,
            error_code="upstream_timeout",
            error_detail="gateway timeout",
            trace_id="trc-wh-3",
            auth_context=self.auth_admin,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(delivery["status"], "retrying")

        status_list, list_payload = get_webhook_events_api(
            query_params={"subscription_id": body1["subscription_id"], "attempt_gte": 1},
            auth_context=self.auth_admin,
            store=self.store,
        )
        self.assertEqual(status_list, 200)
        self.assertEqual(list_payload["count"], 1)

    def test_webhook_failure_dead_letter_event_and_replay(self):
        _, sub = post_webhooks(
            request_body={
                "target_url": "https://hooks.example.com/fail",
                "event_types": ["task.created"],
            },
            headers={"Idempotency-Key": "idem-wh-2", "X-Trace-Id": "trc-wh-4"},
            auth_context=self.auth_admin,
            store=self.store,
            now=self.now,
        )

        last = None
        for attempt in range(1, 8):
            last = record_webhook_delivery_attempt(
                subscription_id=sub["subscription_id"],
                event_id="evt-wh-2",
                event_name="task.created",
                payload={"task_id": "t-1"},
                attempt=attempt,
                response_code=503,
                error_code="upstream_timeout",
                error_detail="timeout",
                trace_id=f"trc-wh-fail-{attempt}",
                auth_context=self.auth_admin,
                store=self.store,
                now=self.now + timedelta(seconds=attempt),
            )

        self.assertIsNotNone(last)
        self.assertEqual(last["status"], "dead_lettered")

        failed_events = [e for e in self.store.outbox_events if e["event_type"] == "webhook.delivery_failed"]
        self.assertEqual(len(failed_events), 1)

        replay = request_webhook_replay(
            delivery_id=last["delivery_id"],
            reason="endpoint fixed",
            auth_context=self.auth_admin,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(replay["status"], "queued")

    def test_connector_sync_run_start_complete_and_error_taxonomy(self):
        status, run = post_connector_sync(
            connector_name="accela_api",
            request_body={"run_mode": "delta"},
            headers={"Idempotency-Key": "idem-run-1", "X-Trace-Id": "trc-run-1"},
            auth_context=self.auth_pm,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(status, 202)
        self.assertEqual(run["run_status"], "running")

        err = record_connector_error(
            run_id=run["run_id"],
            classification="rate_limit.exceeded",
            message="429 retry",
            auth_context=self.auth_pm,
            store=self.store,
            external_code="429",
        )
        self.assertTrue(err["is_retryable"])

        complete = complete_connector_sync(
            run_id=run["run_id"],
            final_status="partial",
            records_fetched=20,
            records_synced=18,
            records_failed=2,
            trace_id="trc-run-2",
            auth_context=self.auth_pm,
            store=self.store,
            now=self.now + timedelta(seconds=20),
        )
        self.assertEqual(complete["run_status"], "partial")

        types = [e["event_type"] for e in self.store.outbox_events]
        self.assertIn("integration.run_started", types)
        self.assertIn("integration.run_completed", types)

    def test_dashboard_snapshot_upsert_and_read_api(self):
        snapshot_at = self.now
        upsert_dashboard_snapshot(
            metrics={
                "permits_total": 100,
                "permit_cycle_time_p50_days": 10.5,
                "permit_cycle_time_p90_days": 24.0,
                "corrections_rate": 0.2,
                "approval_rate_30d": 0.7,
                "task_sla_breach_rate": 0.05,
                "connector_health_score": 88.0,
                "webhook_delivery_success_rate": 0.99,
            },
            snapshot_at=snapshot_at,
            source_max_event_at=self.now - timedelta(seconds=30),
            auth_context=self.auth_admin,
            store=self.store,
            now=self.now,
        )
        upsert_dashboard_snapshot(
            metrics={
                "permits_total": 101,
                "permit_cycle_time_p50_days": 10.0,
                "permit_cycle_time_p90_days": 23.5,
                "corrections_rate": 0.19,
                "approval_rate_30d": 0.71,
                "task_sla_breach_rate": 0.04,
                "connector_health_score": 89.0,
                "webhook_delivery_success_rate": 0.992,
            },
            snapshot_at=snapshot_at,
            source_max_event_at=self.now - timedelta(seconds=20),
            auth_context=self.auth_admin,
            store=self.store,
            now=self.now,
        )

        status, payload = get_dashboard_portfolio_api(auth_context=self.auth_reviewer, store=self.store)
        self.assertEqual(status, 200)
        self.assertEqual(payload["metrics"]["permits_total"], 101)

    def test_api_key_create_rotate_and_revoke_rules(self):
        created_status, key_payload = post_org_api_keys(
            org_id=self.org_id,
            request_body={
                "name": "svc key",
                "scopes": ["webhooks:read", "dashboard:read"],
                "expires_at": (self.now + timedelta(days=30)).isoformat(),
            },
            headers={"Idempotency-Key": "idem-key-1", "X-Trace-Id": "trc-key-1"},
            auth_context=self.auth_owner,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(created_status, 201)
        self.assertTrue(key_payload["plaintext_key"].startswith(key_payload["key_prefix"]))

        replay_status, replay_payload = post_org_api_keys(
            org_id=self.org_id,
            request_body={
                "name": "svc key",
                "scopes": ["webhooks:read", "dashboard:read"],
                "expires_at": (self.now + timedelta(days=30)).isoformat(),
            },
            headers={"Idempotency-Key": "idem-key-1", "X-Trace-Id": "trc-key-2"},
            auth_context=self.auth_owner,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(replay_status, 200)
        self.assertNotIn("plaintext_key", replay_payload)

        old_id = key_payload["credential_id"]
        rotate_status, rotated = rotate_api_key(
            credential_id=old_id,
            new_name="svc key 2",
            new_scopes=["webhooks:write"],
            idempotency_key="idem-key-2",
            auth_context=self.auth_owner,
            store=self.store,
            now=self.now,
            expires_at=self.now + timedelta(days=60),
        )
        self.assertEqual(rotate_status, 201)
        self.assertNotEqual(rotated["credential_id"], old_id)

    def test_api_key_usage_tracking_and_rotation_policy_scan(self):
        created_status, key_payload = post_org_api_keys(
            org_id=self.org_id,
            request_body={
                "name": "svc key usage",
                "scopes": ["dashboard:read"],
                "expires_at": (self.now + timedelta(days=120)).isoformat(),
            },
            headers={"Idempotency-Key": "idem-key-usage-1", "X-Trace-Id": "trc-key-usage-1"},
            auth_context=self.auth_owner,
            store=self.store,
            now=self.now - timedelta(days=95),
        )
        self.assertEqual(created_status, 201)
        mark_api_key_used(
            credential_id=key_payload["credential_id"],
            usage_source="integration-test",
            auth_context=self.auth_owner,
            store=self.store,
            now=self.now,
        )
        row = self.store.api_credentials_by_id[key_payload["credential_id"]]
        self.assertIsNotNone(row["last_used_at"])
        self.assertEqual(row["last_used_source"], "integration-test")

        policy = scan_api_key_rotation_policy(
            auth_context=self.auth_owner,
            store=self.store,
            max_age_days=90,
            warning_days=14,
            auto_revoke_overdue=False,
            now=self.now,
        )
        self.assertGreaterEqual(policy["counts"]["overdue"], 1)

    def test_slo_snapshot_and_audit_evidence_pack(self):
        sub_status, sub = post_webhooks(
            request_body={
                "target_url": "https://hooks.example.com/slo",
                "event_types": ["task.created"],
            },
            headers={"Idempotency-Key": "idem-slo-wh-1", "X-Trace-Id": "trc-slo-wh-1"},
            auth_context=self.auth_admin,
            store=self.store,
            now=self.now,
        )
        self.assertIn(sub_status, {200, 201})
        record_webhook_delivery_attempt(
            subscription_id=sub["subscription_id"],
            event_id="evt-slo-1",
            event_name="task.created",
            payload={"task_id": "t-11"},
            attempt=1,
            response_code=200,
            error_code=None,
            error_detail=None,
            trace_id="trc-slo-wh-2",
            auth_context=self.auth_admin,
            store=self.store,
            now=self.now,
        )
        slo = compute_ops_slo_snapshot(
            auth_context=self.auth_admin,
            store=self.store,
            now=self.now,
        )
        self.assertIn("webhook", slo)
        self.assertIn("connectors", slo)
        self.assertIn("api_keys", slo)

        export = request_security_audit_export(
            time_range_start=self.now - timedelta(days=1),
            time_range_end=self.now,
            export_type="audit_timeline",
            auth_context=self.auth_owner,
            store=self.store,
            now=self.now,
        )
        mark_security_audit_export_running(
            export_id=export["export_id"],
            generated_by=self.auth_owner.user_id,
            auth_context=self.auth_owner,
            store=self.store,
            now=self.now,
        )
        mark_security_audit_export_completed(
            export_id=export["export_id"],
            checksum="sha256:evidence",
            storage_uri="s3://audit/evidence.json",
            access_log_ref="log:evidence",
            generated_by=self.auth_owner.user_id,
            auth_context=self.auth_owner,
            store=self.store,
            now=self.now,
        )
        evidence = build_security_audit_evidence_pack(
            export_id=export["export_id"],
            auth_context=self.auth_owner,
            store=self.store,
            now=self.now,
        )
        self.assertIn("evidence_pack_id", evidence)
        self.assertEqual(evidence["manifest"]["export_id"], export["export_id"])

    def test_task_template_and_audit_export_controls(self):
        template = create_task_template(
            name="Default Permit Checklist",
            description="Base list",
            template={"steps": ["collect plans", "submit"]},
            auth_context=self.auth_pm,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(template["version"], 1)

        archive_task_template(
            template_id=template["template_id"],
            auth_context=self.auth_pm,
            store=self.store,
            now=self.now,
        )

        export = request_security_audit_export(
            time_range_start=self.now - timedelta(days=7),
            time_range_end=self.now,
            export_type="audit_timeline",
            auth_context=self.auth_owner,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(export["status"], "pending")

        mark_security_audit_export_running(
            export_id=export["export_id"],
            generated_by=self.auth_admin.user_id,
            auth_context=self.auth_admin,
            store=self.store,
            now=self.now,
        )

        mark_security_audit_export_completed(
            export_id=export["export_id"],
            checksum="sha256:abc",
            storage_uri="s3://audit/export.json",
            access_log_ref="log-ref-1",
            generated_by=self.auth_admin.user_id,
            auth_context=self.auth_admin,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(self.store.security_audit_exports_by_id[export["export_id"]]["status"], "completed")

    def test_pm_cannot_request_audit_export(self):
        with self.assertRaises(EnterpriseReadinessError) as ctx:
            request_security_audit_export(
                time_range_start=self.now - timedelta(days=1),
                time_range_end=self.now,
                export_type="audit_timeline",
                auth_context=self.auth_pm,
                store=self.store,
                now=self.now,
            )
        self.assertEqual(ctx.exception.status, 403)

    def test_failed_export_transition(self):
        export = request_security_audit_export(
            time_range_start=self.now - timedelta(days=2),
            time_range_end=self.now,
            export_type="compliance_evidence_pack",
            auth_context=self.auth_owner,
            store=self.store,
            now=self.now,
        )
        mark_security_audit_export_failed(
            export_id=export["export_id"],
            failure_reason="storage timeout",
            auth_context=self.auth_owner,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(self.store.security_audit_exports_by_id[export["export_id"]]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
