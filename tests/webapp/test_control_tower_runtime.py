from __future__ import annotations

import base64
from datetime import datetime, timezone
import os
import pathlib
import sys
import tempfile
import unittest
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.stage2.connector_runtime import AccelaApiAdapter
from scripts.stage2.connector_runtime import ConnectorObservation
from scripts.stage2.connector_runtime import run_connector_poll_with_retries
from scripts.stage1a.comment_extraction_service import process_extraction_candidates
from scripts.stage1a.comment_letter_api import post_comment_letters
from scripts.stage1a.ingestion_runtime import enqueue_upload_job
from scripts.stage1a.ingestion_runtime import process_upload_job
from scripts.stage0_5.enterprise_service import archive_task_template
from scripts.stage0_5.enterprise_service import complete_connector_sync
from scripts.stage0_5.enterprise_service import mark_security_audit_export_completed
from scripts.stage0_5.enterprise_service import mark_security_audit_export_running
from scripts.stage0_5.enterprise_service import record_webhook_delivery_attempt
from scripts.stage0_5.enterprise_service import request_security_audit_export
from scripts.stage0_5.enterprise_service import request_webhook_replay
from scripts.stage0_5.enterprise_service import revoke_api_key
from scripts.stage0_5.enterprise_service import rotate_api_key
from scripts.stage0_5.enterprise_service import create_task_template
from scripts.stage0_5.runtime_api import post_connector_sync
from scripts.stage0_5.runtime_api import post_org_api_keys
from scripts.stage0_5.runtime_api import post_webhooks
from scripts.webapp_server import _build_candidates_from_page_text
from scripts.webapp_server import DemoAppState


class ControlTowerRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = DemoAppState()
        self.bootstrap_payload = self.state.bootstrap()
        self.assertIsNotNone(self.state.ids)

    def tearDown(self) -> None:
        self.state.stage2_repo.close()
        self.state.stage3_store.repository.close()
        if self.state.runtime_store is not None:
            self.state.runtime_store.close()

    def test_control_tower_payload_shapes(self):
        portfolio = self.state.portfolio()
        activity = self.state.activity_feed(limit=10)
        permit_ops = self.state.permit_ops(limit=10)
        finance_ops = self.state.finance_ops(limit=10)
        enterprise_ops = self.state.enterprise_ops(limit=10)
        enterprise_alerts = self.state.enterprise_alerts()
        quality_report = self.state.stage1a_quality_report(target="staging")

        self.assertTrue(portfolio["bootstrapped"])
        self.assertIn("kpis", portfolio)
        self.assertIn("projects", portfolio)

        self.assertTrue(activity["bootstrapped"])
        self.assertIn("events", activity)

        self.assertTrue(permit_ops["bootstrapped"])
        self.assertIn("connector_health", permit_ops)
        self.assertIn("transition_review_queue", permit_ops)

        self.assertTrue(finance_ops["bootstrapped"])
        self.assertIn("payouts", finance_ops)
        self.assertIn("outbox", finance_ops)

        self.assertTrue(enterprise_ops["bootstrapped"])
        self.assertIn("alerts", enterprise_ops)
        self.assertIn("slo", enterprise_ops)
        self.assertIn("telemetry", enterprise_ops)
        self.assertIn("integration_readiness", enterprise_ops)
        self.assertIn("launch_readiness", enterprise_ops)
        self.assertIn("transition_reviews", enterprise_ops["slo"])
        self.assertIn("payout_reconciliation", enterprise_ops["slo"])
        self.assertTrue(enterprise_alerts["bootstrapped"])
        self.assertIn("metrics", enterprise_alerts)
        self.assertTrue(quality_report["bootstrapped"])
        self.assertIn("release_gate", quality_report)

    def test_integration_readiness_defaults_to_blocked_without_external_env(self):
        readiness = self.state.integration_readiness()
        self.assertTrue(readiness["bootstrapped"])
        self.assertIn("launch_blockers", readiness)
        self.assertIn("stage2", readiness)
        self.assertIn("stage3", readiness)
        self.assertFalse(readiness["overall_ready"])

    def test_integration_readiness_does_not_block_on_stripe_when_disabled(self):
        previous_key = os.environ.pop("ATLASLY_STRIPE_SECRET_KEY", None)
        previous_enabled = os.environ.pop("ATLASLY_ENABLE_STRIPE", None)
        previous_signatures = os.environ.pop("ATLASLY_STAGE3_ENFORCE_SIGNATURES", None)
        try:
            readiness = self.state.integration_readiness()
            self.assertFalse(readiness["stage3"]["enabled"])
            self.assertNotIn("missing_env:ATLASLY_STRIPE_SECRET_KEY", readiness["launch_blockers"])
        finally:
            if previous_key is not None:
                os.environ["ATLASLY_STRIPE_SECRET_KEY"] = previous_key
            if previous_enabled is not None:
                os.environ["ATLASLY_ENABLE_STRIPE"] = previous_enabled
            if previous_signatures is not None:
                os.environ["ATLASLY_STAGE3_ENFORCE_SIGNATURES"] = previous_signatures

    def test_launch_readiness_includes_checklist_and_blockers(self):
        readiness = self.state.launch_readiness()
        self.assertTrue(readiness["bootstrapped"])
        self.assertIn("checklist", readiness)
        self.assertIn("blockers", readiness)
        self.assertGreaterEqual(len(readiness["checklist"]), 1)

    def test_stage1a_upload_ingestion_and_quality_report(self):
        assert self.state.ids is not None
        encoded = base64.b64encode(
            (
                "Revise panel schedule per NEC 408.4 and provide updated load calculations.\n"
                "Provide duct sizing report per IMC 603.2 and include stamped calculations.\n"
                "Clarify fire alarm sequence of operations per IFC 907.4.\n"
            ).encode("utf-8")
        ).decode("ascii")

        upload_status, upload = enqueue_upload_job(
            organization_id=self.state.ids.organization_id,
            project_id=self.state.ids.project_id,
            filename="comments.txt",
            mime_type="text/plain",
            document_base64=encoded,
            idempotency_key=f"ct-upload-{uuid.uuid4()}",
            trace_id=str(uuid.uuid4()),
            store=self.state.stage1a_ingestion_store,
            now=datetime.now(timezone.utc),
        )
        self.assertEqual(upload_status, 202)

        process_status, processed = process_upload_job(
            organization_id=self.state.ids.organization_id,
            job_id=upload["job_id"],
            store=self.state.stage1a_ingestion_store,
            now=datetime.now(timezone.utc),
        )
        self.assertEqual(process_status, 200)
        self.assertEqual(processed["status"], "completed")

        status, letter = post_comment_letters(
            request_body={
                "project_id": self.state.ids.project_id,
                "document_id": str(uuid.uuid4()),
                "source_filename": "comments.txt",
            },
            idempotency_key=f"ct-stage1a-letter-{uuid.uuid4()}",
            trace_id=str(uuid.uuid4()),
            auth_context=self.state._stage1a_reviewer_auth(),
            store=self.state.stage1a_store,
        )
        self.assertIn(status, {200, 202})

        candidates = _build_candidates_from_page_text(processed["page_text_by_number"])
        extraction_status, _ = process_extraction_candidates(
            letter_id=letter["letter_id"],
            candidates=candidates,
            page_text_by_number=processed["page_text_by_number"],
            ocr_quality_by_page=processed["ocr_quality_by_page"],
            trace_id=str(uuid.uuid4()),
            auth_context=self.state._stage1a_reviewer_auth(),
            store=self.state.stage1a_store,
        )
        self.assertEqual(extraction_status, 200)

        report = self.state.stage1a_quality_report(target="staging")
        self.assertIn("metrics", report)
        self.assertGreaterEqual(report["metrics"]["extraction_count"], 1)
        self.assertIn("drift", report)

    def test_feedback_and_telemetry_capture(self):
        sessions = self.bootstrap_payload.get("sessions", [])
        owner = [row for row in sessions if row.get("role") == "owner"][0]
        session = self.state.require_session(token=owner["token"], allowed_roles={"owner", "admin", "pm", "reviewer", "subcontractor"})

        feedback = self.state.record_feedback(
            message="Great flow, but add clearer success toasts.",
            rating=4,
            category="ux",
            context={"view": "overview"},
            session=session,
        )
        telemetry = self.state.record_telemetry(
            event_type="ui.button_click",
            level="info",
            payload={"button_id": "refreshBtn"},
            session=session,
        )

        self.assertEqual(feedback["category"], "ux")
        self.assertEqual(telemetry["event_type"], "ui.button_click")
        self.assertGreaterEqual(len(self.state.feedback_entries), 1)
        self.assertGreaterEqual(len(self.state.telemetry_events), 1)

    def test_reset_workspace_bootstraps_new_org(self):
        assert self.state.ids is not None
        old_org_id = self.state.ids.organization_id
        payload = self.state.reset_workspace(bootstrap=True)
        self.assertTrue(payload["bootstrapped"])
        self.assertNotEqual(payload["ids"]["organization_id"], old_org_id)
        self.assertEqual(len(self.state.feedback_entries), 0)

    def test_multiple_demo_states_use_isolated_stage2_sqlite_paths(self):
        secondary = DemoAppState()
        try:
            bootstrap_payload = secondary.bootstrap()
            self.assertTrue(bootstrap_payload["bootstrapped"])
            self.assertNotEqual(str(self.state.stage2_db_path), str(secondary.stage2_db_path))
        finally:
            secondary.stage2_repo.close()
            secondary.stage3_store.repository.close()
            if secondary.runtime_store is not None:
                secondary.runtime_store.close()

    def test_mvp_runtime_persists_feedback_and_ids_across_restart(self):
        previous = {
            "ATLASLY_DEPLOYMENT_TIER": os.environ.get("ATLASLY_DEPLOYMENT_TIER"),
            "ATLASLY_STAGE05_RUNTIME_BACKEND": os.environ.get("ATLASLY_STAGE05_RUNTIME_BACKEND"),
            "ATLASLY_STAGE05_PERSISTENCE_READY": os.environ.get("ATLASLY_STAGE05_PERSISTENCE_READY"),
            "ATLASLY_DATA_DIR": os.environ.get("ATLASLY_DATA_DIR"),
        }
        with tempfile.TemporaryDirectory(prefix="atlasly-runtime-test-") as tmpdir:
            os.environ["ATLASLY_DEPLOYMENT_TIER"] = "mvp"
            os.environ["ATLASLY_STAGE05_RUNTIME_BACKEND"] = "sqlite"
            os.environ["ATLASLY_STAGE05_PERSISTENCE_READY"] = "true"
            os.environ["ATLASLY_DATA_DIR"] = tmpdir

            first = DemoAppState()
            try:
                first.bootstrap()
                owner = first.require_session(
                    token=first.session_token_by_role["owner"],
                    allowed_roles={"owner"},
                )
                first.record_feedback(
                    message="persist me",
                    rating=5,
                    category="pilot",
                    context={"mode": "mvp"},
                    session=owner,
                )
                first.persist_if_configured()
                first_org_id = first.ids.organization_id if first.ids else None
            finally:
                first.stage2_repo.close()
                first.stage3_store.repository.close()
                if first.runtime_store is not None:
                    first.runtime_store.close()

            second = DemoAppState()
            try:
                self.assertFalse(second.demo_routes_enabled)
                self.assertIsNotNone(second.ids)
                self.assertEqual(second.ids.organization_id if second.ids else None, first_org_id)
                self.assertEqual(len(second.feedback_entries), 1)
                self.assertTrue(second.summary()["runtime"]["persistence_ready"])
            finally:
                second.stage2_repo.close()
                second.stage3_store.repository.close()
                if second.runtime_store is not None:
                    second.runtime_store.close()

        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_permit_and_finance_ops_reflect_runtime_activity(self):
        assert self.state.ids is not None

        observed_at = datetime.now(timezone.utc)

        def _client_callable(*, ahj_id: str):
            return [
                ConnectorObservation(
                    permit_id=self.state.ids.permit_id,
                    raw_status="Under review",
                    source="accela_api",
                    observed_at=observed_at,
                    parser_version="v1",
                    source_ref=f"accela:{ahj_id}",
                    old_status=None,
                )
            ]

        run_connector_poll_with_retries(
            ahj_id="ca.san_jose.building",
            idempotency_key=f"ct-ops-{uuid.uuid4()}",
            trace_id=str(uuid.uuid4()),
            auth_context=self.state._stage2_sync_auth(),
            adapter=AccelaApiAdapter(client_callable=_client_callable),
            repository=self.state.stage2_repo,
            rules=None,
            max_attempts=1,
        )

        permit_ops = self.state.permit_ops(limit=20)
        self.assertGreaterEqual(permit_ops["transition_review_queue"]["open_count"], 1)
        review_id = permit_ops["transition_review_queue"]["items"][0]["id"]
        resolved_review = self.state.stage2_repo.update_transition_review_resolution(
            organization_id=self.state.ids.organization_id,
            review_id=review_id,
            resolution_state="resolved",
        )
        self.assertEqual(resolved_review["resolution_state"], "resolved")

        payout_status, payout_payload = self.state.stage3_api.post_milestone_financial_actions(
            milestone_id=self.state.ids.milestone_id,
            request_body={
                "amount": 1250.0,
                "currency": "USD",
                "beneficiary_id": "beneficiary-ct-tests",
                "provider": "provider_sandbox",
                "step_up_authenticated": True,
            },
            headers={"Idempotency-Key": f"ct-payout-{uuid.uuid4()}", "X-Trace-Id": str(uuid.uuid4())},
            auth_context=self.state._stage3_auth(),
        )
        self.assertIn(payout_status, {200, 201})

        self.state.stage3_api.post_provider_webhook(
            request_body={
                "instruction_id": payout_payload["instruction_id"],
                "provider_event_type": "instruction.submitted",
                "provider_reference": f"ct-sub-{uuid.uuid4().hex[:8]}",
                "amount": 1250.0,
                "currency": "USD",
            },
            headers={"X-Trace-Id": str(uuid.uuid4())},
            auth_context=self.state._stage3_auth(),
        )

        self.state.stage3_api.post_provider_webhook(
            request_body={
                "instruction_id": payout_payload["instruction_id"],
                "provider_event_type": "instruction.settled",
                "provider_reference": f"ct-settle-{uuid.uuid4().hex[:8]}",
                "amount": 1250.0,
                "currency": "USD",
            },
            headers={"X-Trace-Id": str(uuid.uuid4())},
            auth_context=self.state._stage3_auth(),
        )

        self.state.stage3_api.post_financial_reconciliation_runs(
            request_body={
                "provider": "provider_sandbox",
                "settlements": [
                    {
                        "instruction_id": payout_payload["instruction_id"],
                        "amount": 1250.0,
                        "currency": "USD",
                        "provider_reference": f"ct-recon-{uuid.uuid4().hex[:8]}",
                    }
                ],
            },
            headers={"X-Trace-Id": str(uuid.uuid4())},
            auth_context=self.state._stage3_auth(),
        )

        finance_ops = self.state.finance_ops(limit=20)
        self.assertGreaterEqual(finance_ops["payouts"]["total"], 1)
        self.assertGreaterEqual(len(finance_ops["reconciliation"]["runs"]), 1)
        publish_result = self.state.stage3_api.run_outbox_publisher(max_events=200)
        self.assertIn("published_count", publish_result)

    def test_enterprise_ops_reflect_runtime_activity(self):
        assert self.state.ids is not None

        status_webhook, webhook = post_webhooks(
            request_body={
                "target_url": "https://hooks.example.com/atlasly",
                "event_types": ["permit.status_changed", "task.created"],
            },
            headers={"Idempotency-Key": f"ct-wh-{uuid.uuid4()}", "X-Trace-Id": str(uuid.uuid4())},
            auth_context=self.state._stage05_owner_auth(),
            store=self.state.stage05_store,
            now=datetime.now(timezone.utc),
        )
        self.assertIn(status_webhook, {200, 201})

        delivery = record_webhook_delivery_attempt(
            subscription_id=webhook["subscription_id"],
            event_id=f"evt-{uuid.uuid4().hex[:8]}",
            event_name="task.created",
            payload={"task_id": "ct-enterprise"},
            attempt=7,
            response_code=503,
            error_code="upstream_timeout",
            error_detail="simulated failure",
            trace_id=str(uuid.uuid4()),
            auth_context=self.state._stage05_owner_auth(),
            store=self.state.stage05_store,
            now=datetime.now(timezone.utc),
        )
        self.assertEqual(delivery["status"], "dead_lettered")

        replay = request_webhook_replay(
            delivery_id=delivery["delivery_id"],
            reason="control tower replay",
            auth_context=self.state._stage05_owner_auth(),
            store=self.state.stage05_store,
            now=datetime.now(timezone.utc),
        )
        self.assertEqual(replay["status"], "queued")

        status_run, run = post_connector_sync(
            connector_name="accela_api",
            request_body={"run_mode": "delta"},
            headers={"Idempotency-Key": f"ct-sync-{uuid.uuid4()}", "X-Trace-Id": str(uuid.uuid4())},
            auth_context=self.state._stage05_owner_auth(),
            store=self.state.stage05_store,
            now=datetime.now(timezone.utc),
        )
        self.assertIn(status_run, {200, 202})
        complete_connector_sync(
            run_id=run["run_id"],
            final_status="succeeded",
            records_fetched=10,
            records_synced=10,
            records_failed=0,
            trace_id=str(uuid.uuid4()),
            auth_context=self.state._stage05_owner_auth(),
            store=self.state.stage05_store,
            now=datetime.now(timezone.utc),
        )

        status_key, key = post_org_api_keys(
            org_id=self.state.ids.organization_id,
            request_body={"name": "ct key", "scopes": ["dashboard:read", "webhooks:read"]},
            headers={"Idempotency-Key": f"ct-key-{uuid.uuid4()}", "X-Trace-Id": str(uuid.uuid4())},
            auth_context=self.state._stage05_owner_auth(),
            store=self.state.stage05_store,
            now=datetime.now(timezone.utc),
        )
        self.assertIn(status_key, {200, 201})

        rotate_status, rotated = rotate_api_key(
            credential_id=key["credential_id"],
            new_name="ct key rotated",
            new_scopes=["dashboard:read"],
            idempotency_key=f"ct-key-rotate-{uuid.uuid4()}",
            auth_context=self.state._stage05_owner_auth(),
            store=self.state.stage05_store,
            now=datetime.now(timezone.utc),
        )
        self.assertIn(rotate_status, {200, 201})
        revoked = revoke_api_key(
            credential_id=rotated["credential_id"],
            reason="manual revoke",
            auth_context=self.state._stage05_owner_auth(),
            store=self.state.stage05_store,
            now=datetime.now(timezone.utc),
        )
        self.assertIsNotNone(revoked.get("revoked_at"))

        template = create_task_template(
            name="CT Template",
            description="Runtime test template",
            template={"steps": ["one", "two"]},
            auth_context=self.state._stage05_owner_auth(),
            store=self.state.stage05_store,
            now=datetime.now(timezone.utc),
        )
        archived = archive_task_template(
            template_id=template["template_id"],
            auth_context=self.state._stage05_owner_auth(),
            store=self.state.stage05_store,
            now=datetime.now(timezone.utc),
        )
        self.assertFalse(archived["is_active"])

        export = request_security_audit_export(
            time_range_start=datetime.now(timezone.utc),
            time_range_end=datetime.now(timezone.utc),
            export_type="audit_timeline",
            auth_context=self.state._stage05_owner_auth(),
            store=self.state.stage05_store,
            now=datetime.now(timezone.utc),
        )
        mark_security_audit_export_running(
            export_id=export["export_id"],
            generated_by=self.state.ids.owner_user_id,
            auth_context=self.state._stage05_owner_auth(),
            store=self.state.stage05_store,
            now=datetime.now(timezone.utc),
        )
        mark_security_audit_export_completed(
            export_id=export["export_id"],
            checksum="sha256:ct",
            storage_uri="s3://ct/export.json",
            access_log_ref="ct-log-ref",
            generated_by=self.state.ids.owner_user_id,
            auth_context=self.state._stage05_owner_auth(),
            store=self.state.stage05_store,
            now=datetime.now(timezone.utc),
        )

        ops = self.state.enterprise_ops(limit=20)
        self.assertTrue(ops["bootstrapped"])
        self.assertGreaterEqual(ops["webhooks"]["dead_letter_total"], 1)
        self.assertGreaterEqual(ops["connector_runs"]["total"], 1)
        self.assertGreaterEqual(ops["api_credentials"]["total"], 1)
        self.assertGreaterEqual(ops["task_templates"]["total"], 1)
        self.assertGreaterEqual(ops["audit_exports"]["total"], 1)


if __name__ == "__main__":
    unittest.main()
