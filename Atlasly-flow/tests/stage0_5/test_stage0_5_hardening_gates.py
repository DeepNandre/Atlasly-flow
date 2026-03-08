from datetime import datetime, timezone
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.stage0_5.hardening_gates import Stage05OperationalSignals
from scripts.stage0_5.hardening_gates import evaluate_release_gates
from scripts.stage0_5.persistence_adapter import InMemoryStage05Adapter
from scripts.stage0_5.persistence_adapter import SqlFunctionStage05Adapter
from scripts.stage0_5.persistence_adapter import required_stage0_5_mvp_contracts
from scripts.stage0_5.runtime_api import post_webhooks
from scripts.stage0_5.enterprise_service import AuthContext
from scripts.stage0_5.enterprise_service import EnterpriseStore


class Stage05HardeningGateTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 3, 3, 22, 0, tzinfo=timezone.utc)
        self.org_id = "3550f393-cf47-46e9-b146-19d6fbe7e910"
        self.auth_admin = AuthContext(
            organization_id=self.org_id,
            requester_role="admin",
            user_id="8386c232-c273-434d-aed7-181186ad8db9",
        )
        self.store = EnterpriseStore.empty()

    def test_runtime_boundary_blocks_in_memory_for_mvp(self):
        status, payload = post_webhooks(
            request_body={
                "target_url": "https://hooks.example.com/mvp",
                "event_types": ["task.created"],
            },
            headers={"Idempotency-Key": "idem-hardening-1", "X-Trace-Id": "trc-hardening-1"},
            auth_context=self.auth_admin,
            store=self.store,
            now=self.now,
            runtime_backend="in_memory",
            deployment_tier="mvp",
            persistence_ready=False,
        )
        self.assertEqual(status, 503)
        self.assertEqual(payload["error"]["code"], "runtime_not_hardened")

    def test_runtime_boundary_requires_explicit_persistence_signal(self):
        status, payload = post_webhooks(
            request_body={
                "target_url": "https://hooks.example.com/mvp2",
                "event_types": ["task.created"],
            },
            headers={"Idempotency-Key": "idem-hardening-2", "X-Trace-Id": "trc-hardening-2"},
            auth_context=self.auth_admin,
            store=self.store,
            now=self.now,
            runtime_backend="sql_functions",
            deployment_tier="mvp",
            persistence_ready=None,
        )
        self.assertEqual(status, 503)
        self.assertEqual(payload["error"]["code"], "persistence_check_missing")

    def test_runtime_boundary_allows_sql_backend_when_ready(self):
        status, _ = post_webhooks(
            request_body={
                "target_url": "https://hooks.example.com/mvp3",
                "event_types": ["task.created"],
            },
            headers={"Idempotency-Key": "idem-hardening-3", "X-Trace-Id": "trc-hardening-3"},
            auth_context=self.auth_admin,
            store=self.store,
            now=self.now,
            runtime_backend="sql_functions",
            deployment_tier="mvp",
            persistence_ready=True,
        )
        self.assertEqual(status, 201)

    def test_persistence_adapter_reports(self):
        memory_report = InMemoryStage05Adapter().capability_report()
        self.assertFalse(memory_report.production_ready)
        self.assertIn("NOT PRODUCTION READY", memory_report.notes)

        sql = SqlFunctionStage05Adapter(dsn="postgres://example")
        sql.discovered_contracts = set(required_stage0_5_mvp_contracts())
        sql_report = sql.capability_report()
        self.assertTrue(sql_report.production_ready)
        self.assertEqual(sql_report.missing_contracts, ())

    def test_release_gate_evaluator_and_rollback_triggers(self):
        good = Stage05OperationalSignals(
            webhook_success_rate_24h_pct=99.7,
            webhook_success_rate_60m_pct=99.2,
            webhook_dlq_growth_30m=2,
            connector_run_success_rate_24h_pct=99.0,
            connector_max_staleness_minutes=30,
            dashboard_refresh_p95_seconds=180,
            dashboard_max_staleness_seconds=120,
            api_key_rotation_coverage_pct=99.0,
            audit_export_success_rate_24h_pct=99.3,
            p1_incidents_last_24h=0,
        )
        good_eval = evaluate_release_gates(good)
        self.assertTrue(good_eval["ready_for_public_mvp"])
        self.assertFalse(good_eval["rollback_required_now"])

        bad = Stage05OperationalSignals(
            webhook_success_rate_24h_pct=96.0,
            webhook_success_rate_60m_pct=95.0,
            webhook_dlq_growth_30m=450,
            connector_run_success_rate_24h_pct=90.0,
            connector_max_staleness_minutes=200,
            dashboard_refresh_p95_seconds=1000,
            dashboard_max_staleness_seconds=1800,
            api_key_rotation_coverage_pct=70.0,
            audit_export_success_rate_24h_pct=80.0,
            p1_incidents_last_24h=3,
        )
        bad_eval = evaluate_release_gates(bad)
        self.assertFalse(bad_eval["ready_for_public_mvp"])
        self.assertTrue(bad_eval["rollback_required_now"])


if __name__ == "__main__":
    unittest.main()
