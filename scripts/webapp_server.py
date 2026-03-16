from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
import json
import os
import pathlib
import re
import sys
import tempfile
import uuid
from http.server import HTTPServer
from urllib.parse import parse_qs
from urllib.parse import urlparse

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.stage0.foundation_api import post_org_user_invite_api
from scripts.stage0.foundation_api import post_orgs_api
from scripts.stage0.foundation_api import post_project_permits_api
from scripts.stage0.foundation_api import post_projects_api
from scripts.stage0.foundation_service import AuthContext as Stage0AuthContext
from scripts.stage0.foundation_service import Stage0Store

from scripts.stage1a.comment_extraction_service import AuthContext as Stage1AAuthContext
from scripts.stage1a.comment_extraction_service import Stage1ARequestError
from scripts.stage1a.comment_extraction_service import Stage1AStore
from scripts.stage1a.comment_extraction_service import process_extraction_candidates
from scripts.stage1a.comment_extraction_service import review_extraction
from scripts.stage1a.comment_letter_api import get_comment_letter_extractions
from scripts.stage1a.comment_letter_api import post_comment_letter_approve
from scripts.stage1a.comment_letter_api import post_comment_letters
from scripts.stage1a.evaluation import evaluate_benchmark
from scripts.stage1a.evaluation import release_gate_decision
from scripts.stage1a.ingestion_runtime import enqueue_upload_job
from scripts.stage1a.ingestion_runtime import IngestionStore
from scripts.stage1a.ingestion_runtime import process_next_upload_job
from scripts.stage1a.ingestion_runtime import process_upload_job

from scripts.stage1b.repositories import Stage1BInMemoryRepository
from scripts.stage1b.runtime_service import Stage1BRuntimeService
from scripts.stage1b.ticketing_service import AuthContext as Stage1BAuthContext

from scripts.stage2.connector_runtime import AccelaApiAdapter
from scripts.stage2.connector_runtime import ConnectorObservation
from scripts.stage2.connector_runtime import ConnectorPollError
from scripts.stage2.connector_runtime import run_connector_poll_with_retries
from scripts.stage2.connector_credentials import ConnectorCredentialError
from scripts.stage2.connector_credentials import ConnectorCredentialVault
from scripts.stage2.connector_credentials import default_secret_env_var
from scripts.stage2.live_connectors import build_live_connector_adapter
from scripts.stage2.intake_api import AuthContext as Stage2IntakeAuthContext
from scripts.stage2.intake_api import BASE_REQUIRED_FIELDS
from scripts.stage2.intake_api import PERMIT_SPECIFIC_REQUIRED_FIELDS
from scripts.stage2.intake_api import create_intake_session_persisted
from scripts.stage2.intake_api import generate_permit_application_persisted
from scripts.stage2.intake_api import update_intake_session_persisted
from scripts.stage2.sqlite_repository import Stage2SQLiteRepository
from scripts.stage2.status_sync import AuthContext as Stage2SyncAuthContext
from scripts.stage2.sync_api import get_status_timeline_persisted
from scripts.stage2.ahj_intelligence import AddressInput
from scripts.stage2.ahj_intelligence import AhjIntelligenceError
from scripts.stage2.ahj_intelligence import ShovelsClient

from scripts.stage3.payout_api import AuthContext as Stage3AuthContext
from scripts.stage3.runtime_api import Stage3RuntimeAPI
from scripts.stage3.runtime_api import Stage3RuntimeStore

from scripts.stage0_5.enterprise_service import AuthContext as Stage05AuthContext
from scripts.stage0_5.enterprise_service import EnterpriseReadinessError
from scripts.stage0_5.enterprise_service import EnterpriseStore
from scripts.stage0_5.enterprise_service import PROD_LIKE_DEPLOYMENT_TIERS
from scripts.stage0_5.enterprise_service import enforce_runtime_hardening_boundary
from scripts.stage0_5.enterprise_service import archive_task_template
from scripts.stage0_5.enterprise_service import complete_connector_sync
from scripts.stage0_5.enterprise_service import compute_ops_slo_snapshot
from scripts.stage0_5.enterprise_service import create_task_template
from scripts.stage0_5.enterprise_service import build_security_audit_evidence_pack
from scripts.stage0_5.enterprise_service import mark_security_audit_export_completed
from scripts.stage0_5.enterprise_service import mark_security_audit_export_running
from scripts.stage0_5.enterprise_service import mark_api_key_used
from scripts.stage0_5.enterprise_service import record_webhook_delivery_attempt
from scripts.stage0_5.enterprise_service import record_connector_error
from scripts.stage0_5.enterprise_service import request_webhook_replay
from scripts.stage0_5.enterprise_service import request_security_audit_export
from scripts.stage0_5.enterprise_service import revoke_api_key
from scripts.stage0_5.enterprise_service import rotate_api_key
from scripts.stage0_5.enterprise_service import scan_api_key_rotation_policy
from scripts.stage0_5.enterprise_service import upsert_dashboard_snapshot
from scripts.stage0_5.runtime_api import get_dashboard_portfolio_api
from scripts.stage0_5.runtime_api import get_webhook_events_api
from scripts.stage0_5.runtime_api import post_connector_sync
from scripts.stage0_5.runtime_api import post_org_api_keys
from scripts.stage0_5.runtime_api import post_webhooks
from scripts.runtime_state_store import RuntimeStateSQLiteStore


STATIC_DIR = ROOT / "webapp"

ALL_SESSION_ROLES = {"owner", "admin", "pm", "reviewer", "subcontractor"}
CONTROL_TOWER_READ_ROLES = {"owner", "admin", "pm", "reviewer"}
COMMENT_OPS_WRITE_ROLES = {"owner", "admin", "pm", "reviewer"}
PERMIT_OPS_WRITE_ROLES = {"owner", "admin", "pm"}
FINANCE_OPS_WRITE_ROLES = {"owner", "admin"}
ENTERPRISE_READ_ROLES = {"owner", "admin", "pm", "reviewer"}
ENTERPRISE_WRITE_ROLES = {"owner", "admin"}
ENTERPRISE_CONNECTOR_WRITE_ROLES = {"owner", "admin", "pm"}
ENTERPRISE_TEMPLATE_WRITE_ROLES = {"owner", "admin", "pm"}


class SessionAuthError(ValueError):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def _iso(ts: datetime | None = None) -> str:
    value = ts or datetime.now(timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _is_expired_session(session: dict | None, *, now: datetime | None = None) -> bool:
    if not session:
        return True
    if not bool(session.get("is_active", True)):
        return True
    expires_at = str(session.get("expires_at") or "").strip()
    if not expires_at:
        return False
    try:
        expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return True
    return (now or datetime.now(timezone.utc)) >= expiry


@dataclass
class DemoIds:
    organization_id: str
    workspace_id: str
    owner_user_id: str
    admin_user_id: str
    pm_user_id: str
    reviewer_user_id: str
    subcontractor_user_id: str
    project_id: str
    permit_id: str
    milestone_id: str


class DemoAppState:
    def __init__(self) -> None:
        self.deployment_tier = os.environ.get("ATLASLY_DEPLOYMENT_TIER", "dev").strip().lower()
        self.demo_routes_enabled = self.deployment_tier not in PROD_LIKE_DEPLOYMENT_TIERS
        self.stage05_runtime_backend = os.environ.get(
            "ATLASLY_STAGE05_RUNTIME_BACKEND",
            "in_memory" if self.demo_routes_enabled else "sqlite",
        ).strip().lower()
        self.stage05_persistence_ready = self._parse_optional_bool(os.environ.get("ATLASLY_STAGE05_PERSISTENCE_READY"))
        self.runtime_data_dir = self._resolve_runtime_data_dir()
        self.runtime_data_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_state_db_path = self._resolve_runtime_state_db_path()
        self.runtime_store = self._build_runtime_store()
        if self.stage05_persistence_ready is None and self.runtime_store is not None:
            self.stage05_persistence_ready = True
        self.stage0_store = Stage0Store.empty()
        self.stage05_store = EnterpriseStore.empty()
        self.stage1a_store = Stage1AStore.empty()
        self.stage1a_ingestion_store = IngestionStore.empty()
        self.stage1b_repo = Stage1BInMemoryRepository()
        self.stage1b_service = Stage1BRuntimeService(self.stage1b_repo)
        self.stage2_db_path = self._resolve_stage2_db_path()
        self.stage2_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.stage2_repo = Stage2SQLiteRepository(db_path=str(self.stage2_db_path))
        self.stage3_db_path = self._resolve_stage3_db_path()
        self.stage3_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.stage3_store = Stage3RuntimeStore.bootstrap(db_path=str(self.stage3_db_path))
        self.stage3_api = Stage3RuntimeAPI(self.stage3_store)

        self.ids: DemoIds | None = None
        self.sessions_by_token: dict[str, dict] = {}
        self.session_token_by_role: dict[str, str] = {}
        self.last_letter_id: str | None = None
        self.last_instruction_id: str | None = None
        self.last_webhook_subscription_id: str | None = None
        self.last_connector_run_id: str | None = None
        self.last_api_credential_id: str | None = None
        self.last_task_template_id: str | None = None
        self.last_audit_export_id: str | None = None
        self.last_stage1a_upload_job_id: str | None = None
        self.stage1a_quality_baseline: dict[str, float] | None = None
        self.feedback_entries: list[dict] = []
        self.telemetry_events: list[dict] = []
        self._restore_runtime_state()

    def _has_persistent_runtime(self) -> bool:
        return self.runtime_store is not None

    def _resolve_runtime_data_dir(self) -> pathlib.Path:
        configured = os.environ.get("ATLASLY_DATA_DIR", "").strip()
        if configured:
            return pathlib.Path(configured).expanduser().resolve()
        return (ROOT / ".atlasly-runtime").resolve()

    def _resolve_runtime_state_db_path(self) -> pathlib.Path:
        configured = os.environ.get("ATLASLY_RUNTIME_STATE_DB_PATH", "").strip()
        if configured:
            return pathlib.Path(configured).expanduser().resolve()
        return self.runtime_data_dir / "runtime_state.sqlite3"

    def _resolve_stage3_db_path(self) -> pathlib.Path:
        configured = os.environ.get("ATLASLY_STAGE3_DB_PATH", "").strip()
        if configured:
            return pathlib.Path(configured).expanduser().resolve()
        if self._has_prod_like_tier():
            return self.runtime_data_dir / "stage3.sqlite3"
        return self.runtime_data_dir / f"stage3_demo_{uuid.uuid4().hex}.sqlite3"

    def _build_runtime_store(self) -> RuntimeStateSQLiteStore | None:
        if not self._has_prod_like_tier() and not os.environ.get("ATLASLY_RUNTIME_STATE_DB_PATH", "").strip():
            return None
        self.runtime_state_db_path.parent.mkdir(parents=True, exist_ok=True)
        return RuntimeStateSQLiteStore(db_path=str(self.runtime_state_db_path))

    def _has_prod_like_tier(self) -> bool:
        return self.deployment_tier in PROD_LIKE_DEPLOYMENT_TIERS

    def _resolve_stage2_db_path(self) -> pathlib.Path:
        configured = os.environ.get("ATLASLY_STAGE2_DB_PATH", "").strip()
        if configured:
            return pathlib.Path(configured).expanduser().resolve()
        if self._has_prod_like_tier():
            return self.runtime_data_dir / "stage2.sqlite3"
        temp_root = pathlib.Path(tempfile.gettempdir()) / "atlasly-flow"
        temp_root.mkdir(parents=True, exist_ok=True)
        return temp_root / f"atlasly_stage2_demo_{uuid.uuid4().hex}.sqlite3"

    @staticmethod
    def _parse_optional_bool(raw: str | None) -> bool | None:
        if raw is None:
            return None
        value = raw.strip().lower()
        if value in {"1", "true", "yes", "on"}:
            return True
        if value in {"0", "false", "no", "off"}:
            return False
        return None

    def _stage05_runtime_kwargs(self) -> dict[str, object]:
        return {
            "runtime_backend": self.stage05_runtime_backend,
            "deployment_tier": self.deployment_tier,
            "persistence_ready": self.stage05_persistence_ready,
        }

    def _enforce_stage05_runtime_boundary(self) -> None:
        enforce_runtime_hardening_boundary(
            runtime_backend=self.stage05_runtime_backend,
            deployment_tier=self.deployment_tier,
            persistence_ready=self.stage05_persistence_ready,
        )

    def _runtime_snapshot(self) -> dict:
        return {
            "ids": None if self.ids is None else {
                "organization_id": self.ids.organization_id,
                "workspace_id": self.ids.workspace_id,
                "owner_user_id": self.ids.owner_user_id,
                "admin_user_id": self.ids.admin_user_id,
                "pm_user_id": self.ids.pm_user_id,
                "reviewer_user_id": self.ids.reviewer_user_id,
                "subcontractor_user_id": self.ids.subcontractor_user_id,
                "project_id": self.ids.project_id,
                "permit_id": self.ids.permit_id,
                "milestone_id": self.ids.milestone_id,
            },
            "stage0_store": self.stage0_store,
            "stage05_store": self.stage05_store,
            "stage1a_store": self.stage1a_store,
            "stage1a_ingestion_store": self.stage1a_ingestion_store,
            "stage1b_ticket_store": self.stage1b_repo.load_ticket_store(),
            "stage1b_notification_store": self.stage1b_repo.load_notification_store(),
            "sessions_by_token": self.sessions_by_token,
            "session_token_by_role": self.session_token_by_role,
            "last_letter_id": self.last_letter_id,
            "last_instruction_id": self.last_instruction_id,
            "last_webhook_subscription_id": self.last_webhook_subscription_id,
            "last_connector_run_id": self.last_connector_run_id,
            "last_api_credential_id": self.last_api_credential_id,
            "last_task_template_id": self.last_task_template_id,
            "last_audit_export_id": self.last_audit_export_id,
            "last_stage1a_upload_job_id": self.last_stage1a_upload_job_id,
            "stage1a_quality_baseline": self.stage1a_quality_baseline,
            "feedback_entries": self.feedback_entries,
            "telemetry_events": self.telemetry_events,
            "stage3_feature_store_data": self.stage3_store.feature_store.data,
            "stage3_model_registry_store": self.stage3_store.model_registry.store,
            "stage3_projects_by_id": self.stage3_store.projects_by_id,
            "stage3_milestones_by_id": self.stage3_store.milestones_by_id,
        }

    def _restore_runtime_state(self) -> None:
        if self.runtime_store is None:
            return
        snapshot = self.runtime_store.load(state_key="app_state")
        if not isinstance(snapshot, dict):
            return
        ids = snapshot.get("ids")
        if isinstance(ids, dict):
            self.ids = DemoIds(**ids)
        self.stage0_store = snapshot.get("stage0_store") or Stage0Store.empty()
        self.stage05_store = snapshot.get("stage05_store") or EnterpriseStore.empty()
        self.stage1a_store = snapshot.get("stage1a_store") or Stage1AStore.empty()
        self.stage1a_ingestion_store = snapshot.get("stage1a_ingestion_store") or IngestionStore.empty()
        self.stage1b_repo = Stage1BInMemoryRepository()
        ticket_store = snapshot.get("stage1b_ticket_store")
        notification_store = snapshot.get("stage1b_notification_store")
        if ticket_store is not None:
            self.stage1b_repo.save_ticket_store(ticket_store)
        if notification_store is not None:
            self.stage1b_repo.save_notification_store(notification_store)
        self.stage1b_service = Stage1BRuntimeService(self.stage1b_repo)
        self.sessions_by_token = dict(snapshot.get("sessions_by_token") or {})
        self.session_token_by_role = dict(snapshot.get("session_token_by_role") or {})
        self.last_letter_id = snapshot.get("last_letter_id")
        self.last_instruction_id = snapshot.get("last_instruction_id")
        self.last_webhook_subscription_id = snapshot.get("last_webhook_subscription_id")
        self.last_connector_run_id = snapshot.get("last_connector_run_id")
        self.last_api_credential_id = snapshot.get("last_api_credential_id")
        self.last_task_template_id = snapshot.get("last_task_template_id")
        self.last_audit_export_id = snapshot.get("last_audit_export_id")
        self.last_stage1a_upload_job_id = snapshot.get("last_stage1a_upload_job_id")
        self.stage1a_quality_baseline = snapshot.get("stage1a_quality_baseline")
        self.feedback_entries = list(snapshot.get("feedback_entries") or [])
        self.telemetry_events = list(snapshot.get("telemetry_events") or [])
        self.stage3_store.repository.close()
        self.stage3_store = Stage3RuntimeStore.bootstrap(
            db_path=str(self.stage3_db_path),
            feature_store_data=snapshot.get("stage3_feature_store_data"),
            model_registry_store=snapshot.get("stage3_model_registry_store"),
            projects_by_id=snapshot.get("stage3_projects_by_id") or {},
            milestones_by_id=snapshot.get("stage3_milestones_by_id") or {},
        )
        self.stage3_api = Stage3RuntimeAPI(self.stage3_store)

    def persist_if_configured(self) -> None:
        if self.runtime_store is None:
            return
        self.runtime_store.save(state_key="app_state", payload=self._runtime_snapshot())

    def _resolve_ahj_with_shovels(self, *, address: dict) -> dict | None:
        api_key = os.environ.get("ATLASLY_SHOVELS_API_KEY", "").strip()
        if not api_key:
            return None
        line1 = str(address.get("line1") or "").strip()
        city = str(address.get("city") or "").strip()
        state = str(address.get("state") or "").strip()
        postal_code = str(address.get("postal_code") or "").strip()
        if not all([line1, city, state, postal_code]):
            return None
        client = ShovelsClient(
            api_key=api_key,
            base_url=os.environ.get("ATLASLY_SHOVELS_BASE_URL", "https://api.shovels.ai"),
        )
        return client.resolve_ahj(
            address=AddressInput(
                line1=line1,
                city=city,
                state=state,
                postal_code=postal_code,
            )
        )

    def _placeholder_env_warnings(self) -> list[str]:
        checks = {
            "ATLASLY_SHOVELS_API_KEY": os.environ.get("ATLASLY_SHOVELS_API_KEY", ""),
            "ATLASLY_ACCELA_APP_ID": os.environ.get("ATLASLY_ACCELA_APP_ID", ""),
        }
        warnings: list[str] = []
        for env_name, raw_value in checks.items():
            value = str(raw_value or "").strip().lower()
            if not value:
                continue
            if value.startswith("your_") or value.endswith("_here") or "placeholder" in value:
                warnings.append(f"placeholder_env:{env_name}")
        return warnings

    def resolve_internal_permit_id(self, *, connector: str, ahj_id: str, external_permit_id: str) -> str | None:
        binding = self.stage2_repo.get_external_permit_binding_by_external_id(
            organization_id=self.ids.organization_id if self.ids else "",
            connector=connector,
            ahj_id=ahj_id,
            external_permit_id=external_permit_id,
        )
        if not binding:
            return None
        return str(binding.get("permit_id") or "").strip() or None

    def enterprise_alerts(self) -> dict:
        if not self.ids:
            return {
                "bootstrapped": False,
                "alerts": [],
                "metrics": {},
            }
        self._enforce_stage05_runtime_boundary()
        org_id = self.ids.organization_id
        now = datetime.now(timezone.utc)

        deliveries = [
            row
            for row in self.stage05_store.webhook_deliveries_by_id.values()
            if row.get("organization_id") == org_id
        ]
        recent_30m = []
        for row in deliveries:
            created_at = str(row.get("created_at") or "")
            try:
                ts = datetime.fromisoformat(created_at.replace("Z", "+00:00")).astimezone(timezone.utc)
            except ValueError:
                continue
            if now - ts <= timedelta(minutes=30):
                recent_30m.append(row)
        dlq_growth_30m = sum(1 for row in recent_30m if row.get("status") == "dead_lettered")
        replay_queue_depth = sum(
            1 for row in self.stage05_store.webhook_replay_jobs_by_id.values() if row.get("status") == "queued"
        )
        transition_open = len(
            self.stage2_repo.list_transition_reviews_by_org(
                organization_id=org_id,
                limit=500,
                resolution_state="open",
            )
        )
        alerts: list[dict] = []
        if dlq_growth_30m > 25:
            alerts.append(
                {
                    "severity": "high",
                    "code": "webhook_dlq_growth_high",
                    "message": f"Webhook dead-letter growth in 30m is {dlq_growth_30m} (> 25).",
                }
            )
        if replay_queue_depth > 10:
            alerts.append(
                {
                    "severity": "medium",
                    "code": "webhook_replay_queue_backlog",
                    "message": f"Webhook replay queue depth is {replay_queue_depth} (> 10).",
                }
            )
        if transition_open > 40:
            alerts.append(
                {
                    "severity": "medium",
                    "code": "transition_review_backlog",
                    "message": f"Stage 2 transition review backlog is {transition_open} (> 40).",
                }
            )
        return {
            "bootstrapped": True,
            "generated_at": _iso(now),
            "metrics": {
                "dlq_growth_30m": dlq_growth_30m,
                "replay_queue_depth": replay_queue_depth,
                "transition_review_open": transition_open,
            },
            "alerts": alerts,
        }

    def integration_readiness(self) -> dict:
        if not self.ids:
            return {
                "bootstrapped": False,
                "generated_at": _iso(),
                "overall_ready": False,
                "launch_blockers": ["workspace_not_bootstrapped"],
            }

        org_id = self.ids.organization_id
        connector_rows = self.stage2_repo.list_connector_credentials(
            organization_id=org_id,
            connector=None,
            limit=500,
        )

        def _connector_readiness(connector: str) -> dict:
            rows = [
                row
                for row in connector_rows
                if str(row.get("connector") or "").strip().lower() == connector
                and str(row.get("status") or "").strip().lower() == "active"
            ]
            credentials = []
            missing_secret_envs = []
            for row in rows:
                credential_ref = str(row.get("credential_ref") or "").strip()
                secret_env = default_secret_env_var(credential_ref) if credential_ref else ""
                secret_present = bool(secret_env and os.environ.get(secret_env, "").strip())
                credentials.append(
                    {
                        "credential_id": row.get("id"),
                        "credential_ref": credential_ref,
                        "ahj_id": row.get("ahj_id"),
                        "secret_env_var": secret_env,
                        "secret_present": secret_present,
                        "rotation_due_at": row.get("rotation_due_at"),
                    }
                )
                if secret_env and not secret_present:
                    missing_secret_envs.append(secret_env)
            ready = bool(credentials) and not missing_secret_envs
            return {
                "configured_credentials": len(credentials),
                "ready": ready,
                "missing_secret_envs": sorted(set(missing_secret_envs)),
                "credentials": credentials,
            }

        accela = _connector_readiness("accela_api")
        opengov = _connector_readiness("opengov_api")
        shovels_key_present = bool(os.environ.get("ATLASLY_SHOVELS_API_KEY", "").strip())
        stripe_enabled = os.environ.get("ATLASLY_ENABLE_STRIPE", "").strip().lower() in {"1", "true", "yes", "on"}
        stripe_key_present = bool(os.environ.get("ATLASLY_STRIPE_SECRET_KEY", "").strip())
        stripe_webhook_secret_present = bool(os.environ.get("ATLASLY_STAGE3_PROVIDER_WEBHOOK_SECRET", "").strip())
        enforce_stage3_signatures = (
            os.environ.get("ATLASLY_STAGE3_ENFORCE_SIGNATURES", "false").strip().lower() in {"1", "true", "yes", "on"}
        )
        stripe_required = stripe_enabled or stripe_key_present or enforce_stage3_signatures
        stripe_ready = (not stripe_required) or (
            stripe_key_present and (stripe_webhook_secret_present if enforce_stage3_signatures else True)
        )
        placeholder_warnings = self._placeholder_env_warnings()

        blockers: list[str] = []
        if not shovels_key_present:
            blockers.append("missing_env:ATLASLY_SHOVELS_API_KEY")
        if not accela["ready"] and not opengov["ready"]:
            blockers.append("live_connector_not_ready")
        for env_name in accela["missing_secret_envs"]:
            blockers.append(f"missing_env:{env_name}")
        for env_name in opengov["missing_secret_envs"]:
            blockers.append(f"missing_env:{env_name}")
        if stripe_required and not stripe_key_present:
            blockers.append("missing_env:ATLASLY_STRIPE_SECRET_KEY")
        if stripe_required and enforce_stage3_signatures and not stripe_webhook_secret_present:
            blockers.append("missing_env:ATLASLY_STAGE3_PROVIDER_WEBHOOK_SECRET")
        if self._has_prod_like_tier():
            blockers.extend(placeholder_warnings)

        return {
            "bootstrapped": True,
            "generated_at": _iso(),
            "overall_ready": len(blockers) == 0,
            "launch_blockers": sorted(set(blockers)),
            "warnings": placeholder_warnings,
            "stage2": {
                "shovels_api_key_present": shovels_key_present,
                "accela_api": accela,
                "opengov_api": opengov,
                "has_any_live_connector_ready": accela["ready"] or opengov["ready"],
            },
            "stage3": {
                "enabled": stripe_required,
                "stripe_secret_key_present": stripe_key_present,
                "webhook_signatures_enforced": enforce_stage3_signatures,
                "stripe_webhook_secret_present": stripe_webhook_secret_present,
                "stripe_ready": stripe_ready,
            },
        }

    def composite_slo_snapshot(self) -> dict:
        if not self.ids:
            return {
                "generated_at": _iso(),
                "window_hours": 24,
                "webhook": {},
                "connectors": {},
                "api_keys": {},
                "transition_reviews": {"open_count": 0, "target_max_open": 40},
                "payout_reconciliation": {
                    "runs_total": 0,
                    "matched_total": 0,
                    "mismatched_total": 0,
                    "mismatch_rate": 0.0,
                    "target_mismatch_rate": 0.01,
                },
                "incidents": [{"severity": "high", "code": "workspace_not_bootstrapped", "message": "Workspace not bootstrapped."}],
            }

        base = compute_ops_slo_snapshot(
            auth_context=self._stage05_owner_auth(),
            store=self.stage05_store,
            now=datetime.now(timezone.utc),
        )
        org_id = self.ids.organization_id
        review_open_count = len(
            self.stage2_repo.list_transition_reviews_by_org(
                organization_id=org_id,
                limit=500,
                resolution_state="open",
            )
        )
        base["transition_reviews"] = {
            "open_count": review_open_count,
            "target_max_open": 40,
        }

        now = datetime.now(timezone.utc)
        window_start = now - timedelta(hours=24)
        runs = self.stage3_store.repository.list_reconciliation_runs_by_org(
            organization_id=org_id,
            limit=500,
        )
        recent_runs = []
        for row in runs:
            started_at_raw = str(row.get("run_started_at") or "").strip()
            if not started_at_raw:
                continue
            try:
                started_at = datetime.fromisoformat(started_at_raw.replace("Z", "+00:00")).astimezone(timezone.utc)
            except ValueError:
                continue
            if started_at >= window_start:
                recent_runs.append(row)
        matched_total = sum(int(row.get("matched_count") or 0) for row in recent_runs)
        mismatched_total = sum(int(row.get("mismatched_count") or 0) for row in recent_runs)
        checked_total = matched_total + mismatched_total
        mismatch_rate = 0.0 if checked_total == 0 else round(mismatched_total / checked_total, 4)
        base["payout_reconciliation"] = {
            "runs_total": len(recent_runs),
            "matched_total": matched_total,
            "mismatched_total": mismatched_total,
            "mismatch_rate": mismatch_rate,
            "target_mismatch_rate": 0.01,
        }

        incidents = list(base.get("incidents") or [])
        if review_open_count > 40:
            incidents.append(
                {
                    "severity": "medium",
                    "code": "transition_review_backlog",
                    "message": "Transition review queue depth exceeded 40.",
                }
            )
        if mismatch_rate > 0.01:
            incidents.append(
                {
                    "severity": "medium",
                    "code": "payout_reconciliation_mismatch_rate",
                    "message": "Payout reconciliation mismatch rate exceeded 1.0% in the last 24h.",
                }
            )
        base["incidents"] = incidents
        return base

    def launch_readiness(self) -> dict:
        if not self.ids:
            return {
                "bootstrapped": False,
                "generated_at": _iso(),
                "overall_ready": False,
                "checklist": [],
                "blockers": ["workspace_not_bootstrapped"],
            }

        integration = self.integration_readiness()
        slo = self.composite_slo_snapshot()

        stage05_boundary_ok = True
        stage05_boundary_error = None
        try:
            self._enforce_stage05_runtime_boundary()
        except EnterpriseReadinessError as exc:
            stage05_boundary_ok = False
            stage05_boundary_error = f"{exc.code}:{exc.message}"

        webhook = slo.get("webhook") or {}
        connectors = slo.get("connectors") or {}
        transitions = slo.get("transition_reviews") or {}
        payout_recon = slo.get("payout_reconciliation") or {}

        checklist = [
            {
                "id": "stage05_runtime_boundary",
                "label": "Stage 0.5 runtime hardening boundary",
                "status": "pass" if stage05_boundary_ok else "fail",
                "detail": "runtime boundary enforced" if stage05_boundary_ok else stage05_boundary_error,
            },
            {
                "id": "integration_credentials_ready",
                "label": "External integration credentials readiness",
                "status": "pass" if integration.get("overall_ready") else "fail",
                "detail": "all required env and connector credentials present"
                if integration.get("overall_ready")
                else "missing integration blockers",
            },
            {
                "id": "webhook_success_slo",
                "label": "Webhook success SLO >= 99%",
                "status": "pass"
                if float(webhook.get("success_rate") or 0.0) >= float(webhook.get("target_success_rate") or 0.99)
                else "fail",
                "detail": f"actual={webhook.get('success_rate')} target={webhook.get('target_success_rate')}",
            },
            {
                "id": "connector_success_slo",
                "label": "Connector success SLO >= 98.5%",
                "status": "pass"
                if float(connectors.get("success_rate") or 0.0) >= float(connectors.get("target_success_rate") or 0.985)
                else "fail",
                "detail": f"actual={connectors.get('success_rate')} target={connectors.get('target_success_rate')}",
            },
            {
                "id": "transition_review_backlog",
                "label": "Transition review backlog within target",
                "status": "pass"
                if int(transitions.get("open_count") or 0) <= int(transitions.get("target_max_open") or 40)
                else "fail",
                "detail": f"actual={transitions.get('open_count')} target_max={transitions.get('target_max_open')}",
            },
            {
                "id": "payout_reconciliation_mismatch",
                "label": "Payout mismatch rate within target",
                "status": "pass"
                if float(payout_recon.get("mismatch_rate") or 0.0)
                <= float(payout_recon.get("target_mismatch_rate") or 0.01)
                else "fail",
                "detail": (
                    f"actual={payout_recon.get('mismatch_rate')} target_max={payout_recon.get('target_mismatch_rate')}"
                ),
            },
        ]

        blockers = []
        for item in checklist:
            if item["status"] == "fail":
                blockers.append(str(item["id"]))
        for blocker in integration.get("launch_blockers", []):
            blockers.append(str(blocker))
        blockers = sorted(set(blockers))

        return {
            "bootstrapped": True,
            "generated_at": _iso(),
            "overall_ready": len(blockers) == 0,
            "checklist": checklist,
            "blockers": blockers,
            "slo": slo,
            "integration_readiness": integration,
        }

    def _issue_session(self, *, role: str, user_id: str, now: datetime | None = None) -> dict:
        if not self.ids:
            raise RuntimeError("workspace not bootstrapped")
        if role not in ALL_SESSION_ROLES:
            raise RuntimeError("unsupported role for session")
        ts = now or datetime.now(timezone.utc)
        existing_token = self.session_token_by_role.get(role)
        if existing_token:
            existing = self.sessions_by_token.get(existing_token)
            if existing and existing.get("organization_id") == self.ids.organization_id and not _is_expired_session(existing, now=ts):
                return existing
            self.sessions_by_token.pop(existing_token, None)
            self.session_token_by_role.pop(role, None)
        token = uuid.uuid4().hex + uuid.uuid4().hex
        session = {
            "session_id": str(uuid.uuid4()),
            "token": token,
            "organization_id": self.ids.organization_id,
            "user_id": user_id,
            "role": role,
            "issued_at": _iso(ts),
            "expires_at": _iso(ts + timedelta(hours=24)),
            "is_active": True,
        }
        self.sessions_by_token[token] = session
        self.session_token_by_role[role] = token
        return session

    def _seed_sessions(self, *, now: datetime | None = None) -> None:
        if not self.ids:
            return
        self._issue_session(role="owner", user_id=self.ids.owner_user_id, now=now)
        self._issue_session(role="admin", user_id=self.ids.admin_user_id, now=now)
        self._issue_session(role="pm", user_id=self.ids.pm_user_id, now=now)
        self._issue_session(role="reviewer", user_id=self.ids.reviewer_user_id, now=now)
        self._issue_session(role="subcontractor", user_id=self.ids.subcontractor_user_id, now=now)

    def _session_payload(self) -> dict:
        now = datetime.now(timezone.utc)
        expired_tokens = [
            token
            for token, session in self.sessions_by_token.items()
            if _is_expired_session(session, now=now)
        ]
        for token in expired_tokens:
            role = str((self.sessions_by_token.get(token) or {}).get("role") or "")
            self.sessions_by_token.pop(token, None)
            if role:
                self.session_token_by_role.pop(role, None)
        owner_token = self.session_token_by_role.get("owner")
        owner_session = self.sessions_by_token.get(owner_token or "")
        sessions = sorted(self.sessions_by_token.values(), key=lambda row: str(row.get("role", "")))
        return {
            "session": None
            if not owner_session
            else {
                "token": owner_session["token"],
                "role": owner_session["role"],
                "expires_at": owner_session["expires_at"],
            },
            "sessions": [
                {
                    "token": row["token"],
                    "role": row["role"],
                    "expires_at": row["expires_at"],
                }
                for row in sessions
            ],
        }

    def sessions_payload(self) -> dict:
        if not self.ids:
            return {
                "bootstrapped": False,
                "sessions": [],
                "runtime": {
                    "deployment_tier": self.deployment_tier,
                    "demo_routes_enabled": self.demo_routes_enabled,
                },
            }
        payload = self._session_payload()
        return {
            "bootstrapped": True,
            "generated_at": _iso(),
            "sessions": payload.get("sessions", []),
            "runtime": {
                "deployment_tier": self.deployment_tier,
                "demo_routes_enabled": self.demo_routes_enabled,
            },
        }

    def reset_workspace(self, *, bootstrap: bool = True) -> dict:
        try:
            self.stage2_repo.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.stage3_store.repository.close()
        except Exception:  # noqa: BLE001
            pass

        for target in (self.stage2_db_path, self.stage3_db_path):
            if target.exists():
                try:
                    target.unlink()
                except Exception:  # noqa: BLE001
                    pass

        self.stage0_store = Stage0Store.empty()
        self.stage05_store = EnterpriseStore.empty()
        self.stage1a_store = Stage1AStore.empty()
        self.stage1a_ingestion_store = IngestionStore.empty()
        self.stage1b_repo = Stage1BInMemoryRepository()
        self.stage1b_service = Stage1BRuntimeService(self.stage1b_repo)
        self.stage2_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.stage2_repo = Stage2SQLiteRepository(db_path=str(self.stage2_db_path))
        self.stage3_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.stage3_store = Stage3RuntimeStore.bootstrap(db_path=str(self.stage3_db_path))
        self.stage3_api = Stage3RuntimeAPI(self.stage3_store)

        self.ids = None
        self.sessions_by_token = {}
        self.session_token_by_role = {}
        self.last_letter_id = None
        self.last_instruction_id = None
        self.last_webhook_subscription_id = None
        self.last_connector_run_id = None
        self.last_api_credential_id = None
        self.last_task_template_id = None
        self.last_audit_export_id = None
        self.last_stage1a_upload_job_id = None
        self.stage1a_quality_baseline = None
        self.feedback_entries = []
        self.telemetry_events = []
        if self.runtime_store is not None:
            self.runtime_store.delete(state_key="app_state")

        if bootstrap:
            payload = self.bootstrap()
            self.persist_if_configured()
            return payload
        payload = self.summary()
        self.persist_if_configured()
        return payload

    def record_feedback(
        self,
        *,
        message: str,
        rating: int,
        category: str,
        session: dict | None,
        context: dict | None = None,
    ) -> dict:
        if not self.ids:
            raise RuntimeError("workspace not bootstrapped")
        msg = str(message or "").strip()
        if len(msg) < 3:
            raise ValueError("feedback message must be at least 3 characters")
        if rating < 1 or rating > 5:
            raise ValueError("rating must be between 1 and 5")
        entry = {
            "id": str(uuid.uuid4()),
            "organization_id": self.ids.organization_id,
            "message": msg[:4000],
            "rating": int(rating),
            "category": str(category or "general")[:64],
            "session_role": None if not session else session.get("role"),
            "session_user_id": None if not session else session.get("user_id"),
            "context": dict(context or {}),
            "created_at": _iso(),
        }
        self.feedback_entries.append(entry)
        if len(self.feedback_entries) > 500:
            self.feedback_entries = self.feedback_entries[-500:]
        return entry

    def record_telemetry(
        self,
        *,
        event_type: str,
        level: str,
        payload: dict | None,
        session: dict | None,
    ) -> dict:
        if not self.ids:
            raise RuntimeError("workspace not bootstrapped")
        entry = {
            "id": str(uuid.uuid4()),
            "organization_id": self.ids.organization_id,
            "event_type": str(event_type or "unknown")[:120],
            "level": str(level or "info")[:24],
            "payload": dict(payload or {}),
            "session_role": None if not session else session.get("role"),
            "session_user_id": None if not session else session.get("user_id"),
            "created_at": _iso(),
        }
        self.telemetry_events.append(entry)
        if len(self.telemetry_events) > 2000:
            self.telemetry_events = self.telemetry_events[-2000:]
        return entry

    def require_session(self, *, token: str, allowed_roles: set[str] | None = None) -> dict:
        raw = token.strip()
        if not raw:
            raise SessionAuthError(401, "unauthorized", "missing bearer token")
        session = self.sessions_by_token.get(raw)
        if not session or not session.get("is_active"):
            raise SessionAuthError(401, "unauthorized", "invalid session token")
        expires_at = str(session.get("expires_at", ""))
        if _is_expired_session(session):
            raise SessionAuthError(401, "unauthorized", "session expired")
        if self.ids and session.get("organization_id") != self.ids.organization_id:
            raise SessionAuthError(403, "forbidden", "session organization mismatch")
        if allowed_roles and session.get("role") not in allowed_roles:
            raise SessionAuthError(403, "forbidden", "role not allowed for route")
        return session

    def allowed_roles_for_route(self, *, method: str, path: str) -> set[str] | None:
        if not path.startswith("/api/"):
            return None
        if path in {"/api/health", "/api/bootstrap"}:
            return None
        if path in {"/api/demo/reset", "/api/demo/run-scenario"}:
            return None if self.demo_routes_enabled else ENTERPRISE_WRITE_ROLES
        if path == "/api/summary":
            return None if self.ids is None else ALL_SESSION_ROLES

        if method == "GET":
            if path == "/api/sessions":
                return ALL_SESSION_ROLES
            if path in {
                "/api/portfolio",
                "/api/activity",
                "/api/permit-ops",
                "/api/finance-ops",
                "/api/stage1b/tasks",
                "/api/stage1b/routing-audit",
                "/api/stage1a/quality-report",
                "/api/stage2/timeline",
                "/api/stage2/connector-credentials",
                "/api/stage2/permit-bindings",
            }:
                return CONTROL_TOWER_READ_ROLES
            if path in {
                "/api/enterprise/overview",
                "/api/enterprise/webhook-events",
                "/api/enterprise/dashboard",
                "/api/enterprise/alerts",
                "/api/enterprise/slo",
                "/api/enterprise/integrations-readiness",
                "/api/enterprise/launch-readiness",
                "/api/telemetry",
            }:
                return ENTERPRISE_READ_ROLES
            if path == "/api/enterprise/audit-evidence":
                return ENTERPRISE_WRITE_ROLES
            if path == "/api/stage3/outbox":
                return FINANCE_OPS_WRITE_ROLES
            return ALL_SESSION_ROLES

        if method == "POST":
            if path in {"/api/feedback", "/api/telemetry"}:
                return ALL_SESSION_ROLES
            if path in {
                "/api/stage1a/upload",
                "/api/stage1a/process-upload",
                "/api/stage1a/parse",
                "/api/stage1a/approve-and-create-tasks",
                "/api/stage1b/escalation-tick",
            }:
                return COMMENT_OPS_WRITE_ROLES
            if path in {
                "/api/stage2/intake-complete",
                "/api/stage2/poll-status",
                "/api/stage2/poll-live",
                "/api/stage2/resolve-ahj",
                "/api/stage2/connector-credentials/rotate",
                "/api/stage2/permit-bindings",
                "/api/permit-ops/resolve-transition",
                "/api/permit-ops/resolve-drift",
            }:
                return PERMIT_OPS_WRITE_ROLES
            if path in {
                "/api/stage3/preflight",
                "/api/stage3/payout",
                "/api/stage3/provider-event",
                "/api/stage3/reconcile",
                "/api/stage3/publish-outbox",
            }:
                return FINANCE_OPS_WRITE_ROLES
            if path in {"/api/enterprise/overview", "/api/enterprise/webhook-events", "/api/enterprise/dashboard"}:
                return ENTERPRISE_READ_ROLES
            if path in {"/api/enterprise/connector-sync", "/api/enterprise/connector-error", "/api/enterprise/connector-complete"}:
                return ENTERPRISE_CONNECTOR_WRITE_ROLES
            if path in {"/api/enterprise/task-templates", "/api/enterprise/task-templates/archive"}:
                return ENTERPRISE_TEMPLATE_WRITE_ROLES
            if path.startswith("/api/enterprise/"):
                return ENTERPRISE_WRITE_ROLES
            return ALL_SESSION_ROLES
        return ALL_SESSION_ROLES

    def _stage0_owner_auth(self) -> Stage0AuthContext:
        if not self.ids:
            raise RuntimeError("workspace not bootstrapped")
        return Stage0AuthContext(
            organization_id=self.ids.organization_id,
            user_id=self.ids.owner_user_id,
            requester_role="owner",
        )

    def _stage0_pm_auth(self) -> Stage0AuthContext:
        if not self.ids:
            raise RuntimeError("workspace not bootstrapped")
        return Stage0AuthContext(
            organization_id=self.ids.organization_id,
            user_id=self.ids.pm_user_id,
            requester_role="pm",
        )

    def _stage1a_reviewer_auth(self) -> Stage1AAuthContext:
        if not self.ids:
            raise RuntimeError("workspace not bootstrapped")
        return Stage1AAuthContext(
            organization_id=self.ids.organization_id,
            requester_role="reviewer",
            user_id=self.ids.reviewer_user_id,
        )

    def _stage1b_pm_auth(self) -> Stage1BAuthContext:
        if not self.ids:
            raise RuntimeError("workspace not bootstrapped")
        return Stage1BAuthContext(
            organization_id=self.ids.organization_id,
            requester_role="pm",
            user_id=self.ids.pm_user_id,
        )

    def _stage2_intake_auth(self) -> Stage2IntakeAuthContext:
        if not self.ids:
            raise RuntimeError("workspace not bootstrapped")
        return Stage2IntakeAuthContext(
            organization_id=self.ids.organization_id,
            requester_role="pm",
            user_id=self.ids.pm_user_id,
        )

    def _stage2_sync_auth(self) -> Stage2SyncAuthContext:
        if not self.ids:
            raise RuntimeError("workspace not bootstrapped")
        return Stage2SyncAuthContext(
            organization_id=self.ids.organization_id,
            requester_role="pm",
        )

    def _stage3_auth(self) -> Stage3AuthContext:
        if not self.ids:
            raise RuntimeError("workspace not bootstrapped")
        return Stage3AuthContext(
            organization_id=self.ids.organization_id,
            requester_role="admin",
        )

    def _stage05_owner_auth(self) -> Stage05AuthContext:
        if not self.ids:
            raise RuntimeError("workspace not bootstrapped")
        return Stage05AuthContext(
            organization_id=self.ids.organization_id,
            requester_role="owner",
            user_id=self.ids.owner_user_id,
        )

    def _seed_stage1b_rules(self) -> None:
        if not self.ids:
            return
        ticket_store = self.stage1b_repo.load_ticket_store()
        if ticket_store.routing_rules_by_id:
            return

        now = _iso()
        rules = [
            {
                "id": str(uuid.uuid4()),
                "organization_id": self.ids.organization_id,
                "project_id": self.ids.project_id,
                "discipline": "electrical",
                "trade_partner_id": None,
                "project_role": None,
                "ahj_id": None,
                "assignee_user_id": self.ids.pm_user_id,
                "priority": 10,
                "confidence_base": 0.9,
                "is_active": True,
                "created_at": now,
            },
            {
                "id": str(uuid.uuid4()),
                "organization_id": self.ids.organization_id,
                "project_id": self.ids.project_id,
                "discipline": "mechanical",
                "trade_partner_id": None,
                "project_role": None,
                "ahj_id": None,
                "assignee_user_id": self.ids.pm_user_id,
                "priority": 20,
                "confidence_base": 0.88,
                "is_active": True,
                "created_at": now,
            },
            {
                "id": str(uuid.uuid4()),
                "organization_id": self.ids.organization_id,
                "project_id": self.ids.project_id,
                "discipline": None,
                "trade_partner_id": None,
                "project_role": None,
                "ahj_id": None,
                "assignee_user_id": self.ids.pm_user_id,
                "priority": 100,
                "confidence_base": 0.8,
                "is_active": True,
                "created_at": now,
            },
        ]
        for rule in rules:
            ticket_store.routing_rules_by_id[rule["id"]] = rule
        self.stage1b_repo.save_ticket_store(ticket_store)

    def _seed_stage05_defaults(self) -> None:
        if not self.ids:
            return
        auth = self._stage05_owner_auth()
        now = datetime.now(timezone.utc)
        if not self.stage05_store.dashboard_snapshots_by_org.get(self.ids.organization_id):
            upsert_dashboard_snapshot(
                metrics={
                    "permits_total": len(self.stage0_store.permits_by_id),
                    "permit_cycle_time_p50_days": 12.0,
                    "permit_cycle_time_p90_days": 28.0,
                    "corrections_rate": 0.25,
                    "approval_rate_30d": 0.62,
                    "task_sla_breach_rate": 0.08,
                    "connector_health_score": 88.0,
                    "webhook_delivery_success_rate": 0.99,
                },
                snapshot_at=now,
                source_max_event_at=now,
                auth_context=auth,
                store=self.stage05_store,
                now=now,
            )

    def bootstrap(self) -> dict:
        if self.ids:
            self._seed_sessions()
            payload = self.summary()
            payload.update(self._session_payload())
            return payload

        now = datetime.now(timezone.utc)
        if self.demo_routes_enabled:
            slug = f"atlasly-demo-{uuid.uuid4().hex[:6]}"
            org_name = "Atlasly Demo Builders"
            owner_name = "Demo Owner"
            admin_name = "Demo Admin"
            pm_name = "Demo PM"
            reviewer_name = "Demo Reviewer"
            subcontractor_name = "Demo Subcontractor"
            owner_email = f"owner+{slug}@atlasly.dev"
            admin_email = f"admin+{slug}@atlasly.dev"
            pm_email = f"pm+{slug}@atlasly.dev"
            reviewer_email = f"reviewer+{slug}@atlasly.dev"
            subcontractor_email = f"subcontractor+{slug}@atlasly.dev"
        else:
            slug = str(os.environ.get("ATLASLY_BOOTSTRAP_ORG_SLUG") or "atlasly-pilot").strip().lower()
            org_name = str(os.environ.get("ATLASLY_BOOTSTRAP_ORG_NAME") or "Atlasly Pilot Workspace").strip()
            owner_name = str(os.environ.get("ATLASLY_BOOTSTRAP_OWNER_NAME") or "Pilot Owner").strip()
            admin_name = str(os.environ.get("ATLASLY_BOOTSTRAP_ADMIN_NAME") or "Pilot Admin").strip()
            pm_name = str(os.environ.get("ATLASLY_BOOTSTRAP_PM_NAME") or "Pilot PM").strip()
            reviewer_name = str(os.environ.get("ATLASLY_BOOTSTRAP_REVIEWER_NAME") or "Pilot Reviewer").strip()
            subcontractor_name = str(
                os.environ.get("ATLASLY_BOOTSTRAP_SUBCONTRACTOR_NAME") or "Pilot Subcontractor"
            ).strip()
            owner_email = str(os.environ.get("ATLASLY_BOOTSTRAP_OWNER_EMAIL") or "owner@atlasly.local").strip()
            admin_email = str(os.environ.get("ATLASLY_BOOTSTRAP_ADMIN_EMAIL") or "admin@atlasly.local").strip()
            pm_email = str(os.environ.get("ATLASLY_BOOTSTRAP_PM_EMAIL") or "pm@atlasly.local").strip()
            reviewer_email = str(os.environ.get("ATLASLY_BOOTSTRAP_REVIEWER_EMAIL") or "reviewer@atlasly.local").strip()
            subcontractor_email = str(
                os.environ.get("ATLASLY_BOOTSTRAP_SUBCONTRACTOR_EMAIL") or "subcontractor@atlasly.local"
            ).strip()

        status_org, payload_org = post_orgs_api(
            request_body={
                "name": org_name,
                "slug": slug,
                "owner_user": {
                    "email": owner_email,
                    "full_name": owner_name,
                },
            },
            headers={"Idempotency-Key": f"idem-{slug}"},
            store=self.stage0_store,
            now=now,
        )
        if status_org not in {200, 201}:
            raise RuntimeError(f"failed bootstrap org: {payload_org}")

        org_id = payload_org["organization"]["id"]
        workspace_id = payload_org["default_workspace"]["id"]
        owner_membership_id = payload_org["owner_membership"]["id"]
        owner_user_id = self.stage0_store.memberships_by_id[owner_membership_id]["user_id"]
        owner_auth = Stage0AuthContext(organization_id=org_id, user_id=owner_user_id, requester_role="owner")

        status_pm, payload_pm = post_org_user_invite_api(
            org_id=org_id,
            request_body={
                "email": pm_email,
                "full_name": pm_name,
                "role": "pm",
                "workspace_id": None,
            },
            headers={"X-Request-Id": str(uuid.uuid4())},
            auth_context=owner_auth,
            store=self.stage0_store,
            now=now,
        )
        if status_pm != 201:
            raise RuntimeError(f"failed bootstrap PM: {payload_pm}")

        status_admin, payload_admin = post_org_user_invite_api(
            org_id=org_id,
            request_body={
                "email": admin_email,
                "full_name": admin_name,
                "role": "admin",
                "workspace_id": None,
            },
            headers={"X-Request-Id": str(uuid.uuid4())},
            auth_context=owner_auth,
            store=self.stage0_store,
            now=now,
        )
        if status_admin != 201:
            raise RuntimeError(f"failed bootstrap admin: {payload_admin}")

        status_rev, payload_rev = post_org_user_invite_api(
            org_id=org_id,
            request_body={
                "email": reviewer_email,
                "full_name": reviewer_name,
                "role": "reviewer",
                "workspace_id": None,
            },
            headers={"X-Request-Id": str(uuid.uuid4())},
            auth_context=owner_auth,
            store=self.stage0_store,
            now=now,
        )
        if status_rev != 201:
            raise RuntimeError(f"failed bootstrap reviewer: {payload_rev}")

        status_sub, payload_sub = post_org_user_invite_api(
            org_id=org_id,
            request_body={
                "email": subcontractor_email,
                "full_name": subcontractor_name,
                "role": "subcontractor",
                "workspace_id": None,
            },
            headers={"X-Request-Id": str(uuid.uuid4())},
            auth_context=owner_auth,
            store=self.stage0_store,
            now=now,
        )
        if status_sub != 201:
            raise RuntimeError(f"failed bootstrap subcontractor: {payload_sub}")

        pm_user_id = payload_pm["membership"]["user_id"]
        admin_user_id = payload_admin["membership"]["user_id"]
        reviewer_user_id = payload_rev["membership"]["user_id"]
        subcontractor_user_id = payload_sub["membership"]["user_id"]
        pm_auth = Stage0AuthContext(organization_id=org_id, user_id=pm_user_id, requester_role="pm")

        status_project, payload_project = post_projects_api(
            request_body={
                "organization_id": org_id,
                "workspace_id": workspace_id,
                "name": "Battery + Solar Retrofit",
                "project_code": f"DEMO-{uuid.uuid4().hex[:4].upper()}",
                "ahj_profile": {
                    "name": "City of San Jose",
                    "jurisdiction_type": "city",
                    "region": "CA",
                },
                "address": {
                    "line1": "200 Market St",
                    "city": "San Jose",
                    "state": "CA",
                    "postal_code": "95113",
                },
            },
            headers={"Idempotency-Key": str(uuid.uuid4())},
            auth_context=pm_auth,
            store=self.stage0_store,
            now=now,
        )
        if status_project not in {200, 201}:
            raise RuntimeError(f"failed bootstrap project: {payload_project}")
        project_id = payload_project["project"]["id"]

        status_permit, payload_permit = post_project_permits_api(
            project_id=project_id,
            request_body={"permit_type": "electrical_service_upgrade"},
            headers={"X-Request-Id": str(uuid.uuid4())},
            auth_context=pm_auth,
            store=self.stage0_store,
            now=now,
        )
        if status_permit != 201:
            raise RuntimeError(f"failed bootstrap permit: {payload_permit}")
        permit_id = payload_permit["permit"]["id"]

        milestone_id = str(uuid.uuid4())
        self.ids = DemoIds(
            organization_id=org_id,
            workspace_id=workspace_id,
            owner_user_id=owner_user_id,
            admin_user_id=admin_user_id,
            pm_user_id=pm_user_id,
            reviewer_user_id=reviewer_user_id,
            subcontractor_user_id=subcontractor_user_id,
            project_id=project_id,
            permit_id=permit_id,
            milestone_id=milestone_id,
        )

        self.stage3_api.register_project(
            {
                "project_id": project_id,
                "organization_id": org_id,
                "permit_id": permit_id,
                "created_at": now,
                "profile": {
                    "completeness_score": 0.74,
                    "complexity_score": 0.57,
                },
            }
        )
        self.stage3_api.register_milestone(
            {
                "id": milestone_id,
                "organization_id": org_id,
                "project_id": project_id,
                "permit_id": permit_id,
                "milestone_state": "payout_eligible",
            }
        )

        self._seed_stage1b_rules()
        self._seed_stage05_defaults()
        self._seed_sessions(now=now)
        payload = self.summary()
        payload.update(self._session_payload())
        return payload

    def summary(self) -> dict:
        ids = self.ids
        ticket_store = self.stage1b_repo.load_ticket_store()
        outbox = self.stage3_store.repository.list_outbox_events(publish_state=None, limit=1000)

        summary = {
            "bootstrapped": ids is not None,
            "runtime": {
                "deployment_tier": self.deployment_tier,
                "demo_routes_enabled": self.demo_routes_enabled,
                "runtime_backend": self.stage05_runtime_backend,
                "persistence_ready": self.stage05_persistence_ready,
                "runtime_state_path": None if self.runtime_store is None else str(self.runtime_state_db_path),
                "stage2_db_path": str(self.stage2_db_path),
                "stage3_db_path": str(self.stage3_db_path),
                "warnings": self._placeholder_env_warnings(),
            },
            "ids": None if ids is None else {
                "organization_id": ids.organization_id,
                "workspace_id": ids.workspace_id,
                "project_id": ids.project_id,
                "permit_id": ids.permit_id,
                "milestone_id": ids.milestone_id,
                "last_letter_id": self.last_letter_id,
                "last_instruction_id": self.last_instruction_id,
            },
            "counts": {
                "stage0_projects": len(self.stage0_store.projects_by_id),
                "stage0_permits": len(self.stage0_store.permits_by_id),
                "stage1a_letters": len(self.stage1a_store.letters_by_id),
                "stage1a_extractions": len(self.stage1a_store.extractions_by_id),
                "stage1a_upload_jobs": len(self.stage1a_ingestion_store.jobs_by_id),
                "stage1b_tasks": len(ticket_store.tasks_by_id),
                "stage1b_manual_queue": len(ticket_store.manual_queue_by_task_id),
                "stage1b_notifications": len(self.stage1b_repo.load_notification_store().sent_notifications),
                "stage05_webhooks": len(self.stage05_store.webhook_subscriptions_by_id),
                "stage05_connector_runs": len(self.stage05_store.connector_runs_by_id),
                "stage05_api_credentials": len(self.stage05_store.api_credentials_by_id),
                "stage05_task_templates": len(self.stage05_store.task_templates_by_id),
                "stage05_audit_exports": len(self.stage05_store.security_audit_exports_by_id),
                "feedback_entries": len(self.feedback_entries),
                "telemetry_events": len(self.telemetry_events),
                "active_sessions": len(self.sessions_by_token),
                "stage2_intake_sessions": self.stage2_repo.count_rows("intake_sessions"),
                "stage2_status_events": self.stage2_repo.count_rows("permit_status_events"),
                "stage3_preflight_scores": self.stage3_store.repository.count_rows("preflight_scores"),
                "stage3_payout_instructions": self.stage3_store.repository.count_rows("payout_instructions"),
                "stage3_reconciliation_runs": self.stage3_store.repository.count_rows("reconciliation_runs"),
                "stage3_outbox_events": len(outbox),
            },
        }
        return summary

    def portfolio(self) -> dict:
        if not self.ids:
            return {
                "bootstrapped": False,
                "projects": [],
                "kpis": {},
                "permit_status_breakdown": {},
            }

        ticket_store = self.stage1b_repo.load_ticket_store()
        org_id = self.ids.organization_id
        projects: list[dict] = []
        permit_status_breakdown: dict[str, int] = {}

        permits_by_project: dict[str, list[dict]] = {}
        for permit in self.stage0_store.permits_by_id.values():
            if permit.get("organization_id") != org_id:
                continue
            permits_by_project.setdefault(str(permit["project_id"]), []).append(permit)

        for project in sorted(
            [p for p in self.stage0_store.projects_by_id.values() if p.get("organization_id") == org_id],
            key=lambda row: str(row.get("created_at", "")),
            reverse=True,
        ):
            project_id = str(project["id"])
            permit_rows: list[dict] = []
            for permit in sorted(
                permits_by_project.get(project_id, []),
                key=lambda row: str(row.get("created_at", "")),
                reverse=True,
            ):
                permit_id = str(permit["id"])
                projection = self.stage2_repo.get_status_projection(permit_id)
                latest_sync = None
                latest_raw_status = None
                latest_event = self.stage2_repo.list_status_events_by_permit(organization_id=org_id, permit_id=permit_id)
                if latest_event:
                    latest_sync = latest_event[0].get("observed_at")
                    latest_raw_status = latest_event[0].get("raw_status")

                current_status = str(projection["current_status"]) if projection else str(permit.get("status", "draft"))
                permit_status_breakdown[current_status] = permit_status_breakdown.get(current_status, 0) + 1

                permit_rows.append(
                    {
                        "permit_id": permit_id,
                        "permit_type": permit.get("permit_type"),
                        "status": current_status,
                        "source_status": latest_raw_status,
                        "status_confidence": None if not projection else projection.get("confidence"),
                        "updated_at": projection.get("updated_at") if projection else permit.get("updated_at"),
                        "last_sync_at": latest_sync,
                    }
                )

            project_tasks = [task for task in ticket_store.tasks_by_id.values() if task.get("project_id") == project_id]
            open_task_count = sum(1 for task in project_tasks if task.get("status") != "done")
            blocked_task_count = sum(1 for task in project_tasks if task.get("status") == "blocked")
            late_task_count = sum(
                1
                for task in project_tasks
                if str(task.get("id")) in ticket_store.assignment_escalations_by_task_id
                and ticket_store.assignment_escalations_by_task_id[str(task.get("id"))].get("status") != "resolved"
            )

            projects.append(
                {
                    "project_id": project_id,
                    "name": project.get("name"),
                    "project_code": project.get("project_code"),
                    "address": project.get("address", {}),
                    "ahj_profile_id": project.get("ahj_profile_id"),
                    "created_at": project.get("created_at"),
                    "permit_count": len(permit_rows),
                    "permits": permit_rows,
                    "tasks": {
                        "total": len(project_tasks),
                        "open": open_task_count,
                        "blocked": blocked_task_count,
                        "escalated": late_task_count,
                    },
                    "risk_level": "high" if blocked_task_count > 0 else ("medium" if open_task_count > 0 else "low"),
                }
            )

        total_permits = sum(permit_status_breakdown.values())
        kpis = {
            "projects_total": len(projects),
            "permits_total": total_permits,
            "permits_issued": permit_status_breakdown.get("issued", 0),
            "permits_in_review": permit_status_breakdown.get("in_review", 0),
            "tasks_open": sum(project["tasks"]["open"] for project in projects),
            "tasks_blocked": sum(project["tasks"]["blocked"] for project in projects),
            "stage2_sync_events": self.stage2_repo.count_rows("permit_status_events"),
            "stage3_reconciliation_runs": self.stage3_store.repository.count_rows("reconciliation_runs"),
        }

        return {
            "bootstrapped": True,
            "generated_at": _iso(),
            "kpis": kpis,
            "permit_status_breakdown": permit_status_breakdown,
            "projects": projects,
        }

    def activity_feed(self, *, limit: int = 40) -> dict:
        if not self.ids:
            return {"bootstrapped": False, "events": []}

        org_id = self.ids.organization_id
        events: list[dict] = []

        for event in self.stage0_store.audit_events:
            if event.get("organization_id") != org_id:
                continue
            events.append(
                {
                    "stage": "stage0",
                    "event_type": event.get("action"),
                    "entity_type": event.get("entity_type"),
                    "entity_id": event.get("entity_id"),
                    "occurred_at": event.get("occurred_at"),
                    "summary": f"{event.get('entity_type')} {event.get('action')}",
                }
            )

        for event in self.stage1a_store.outbox_events:
            if event.get("organization_id") != org_id:
                continue
            payload = event.get("payload") or {}
            events.append(
                {
                    "stage": "stage1a",
                    "event_type": event.get("event_type"),
                    "entity_type": event.get("aggregate_type"),
                    "entity_id": event.get("aggregate_id"),
                    "occurred_at": event.get("occurred_at"),
                    "summary": f"Comment letter event: {event.get('event_type')}",
                    "payload_keys": sorted(payload.keys()),
                }
            )

        ticket_store = self.stage1b_repo.load_ticket_store()
        for event in ticket_store.outbox_events:
            if event.get("organization_id") != org_id:
                continue
            payload = event.get("payload") or {}
            events.append(
                {
                    "stage": "stage1b",
                    "event_type": event.get("event_type"),
                    "entity_type": event.get("aggregate_type"),
                    "entity_id": event.get("aggregate_id"),
                    "occurred_at": event.get("occurred_at"),
                    "summary": f"Task workflow event: {event.get('event_type')}",
                    "payload_keys": sorted(payload.keys()),
                }
            )

        for event in self.stage3_store.repository.list_outbox_events(publish_state=None, limit=200):
            if event.get("organization_id") != org_id:
                continue
            payload = event.get("payload") or {}
            events.append(
                {
                    "stage": "stage3",
                    "event_type": event.get("event_type"),
                    "entity_type": event.get("aggregate_type"),
                    "entity_id": event.get("aggregate_id"),
                    "occurred_at": event.get("occurred_at"),
                    "summary": f"Fintech event: {event.get('event_type')}",
                    "payload_keys": sorted(payload.keys()),
                }
            )

        events_sorted = sorted(events, key=lambda row: str(row.get("occurred_at", "")), reverse=True)
        return {
            "bootstrapped": True,
            "generated_at": _iso(),
            "events": events_sorted[:limit],
        }

    def stage1a_quality_report(self, *, target: str = "staging") -> dict:
        if not self.ids:
            return {
                "bootstrapped": False,
                "target": target,
                "metrics": {},
                "drift": {"detected": False, "reasons": []},
                "release_gate": {"pass": False, "reasons": ["workspace_not_bootstrapped"]},
            }

        rows = sorted(
            self.stage1a_store.extractions_by_id.values(),
            key=lambda row: (str(row.get("created_at", "")), str(row.get("id", ""))),
        )
        if not rows:
            return {
                "bootstrapped": True,
                "target": target,
                "metrics": {},
                "drift": {"detected": False, "reasons": []},
                "release_gate": {"pass": False, "reasons": ["no_stage1a_extractions"]},
            }

        predictions = [dict(row) for row in rows]
        gold = []
        for row in rows:
            approved_row = dict(row)
            approved_row["discipline"] = str(row.get("discipline") or "other")
            gold.append(approved_row)

        letter_created_by_id = {
            str(letter_id): str(letter.get("created_at") or "")
            for letter_id, letter in self.stage1a_store.letters_by_id.items()
            if letter.get("organization_id") == self.ids.organization_id
        }
        latencies_seconds: list[float] = []
        for row in rows:
            letter_id = str(row.get("letter_id") or "")
            created_at_raw = letter_created_by_id.get(letter_id)
            extraction_at_raw = str(row.get("created_at") or "")
            if not created_at_raw or not extraction_at_raw:
                continue
            try:
                start = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00")).astimezone(timezone.utc)
                end = datetime.fromisoformat(extraction_at_raw.replace("Z", "+00:00")).astimezone(timezone.utc)
            except ValueError:
                continue
            latency = max(0.0, (end - start).total_seconds())
            latencies_seconds.append(latency)

        benchmark = evaluate_benchmark(
            predictions=predictions,
            gold=gold,
            latency_seconds=latencies_seconds or [0.0],
        )
        gate_passed, gate_reasons = release_gate_decision(metrics=benchmark, target=target)

        metrics = {
            "discipline_precision": benchmark.discipline_precision,
            "comment_capture_recall": benchmark.comment_capture_recall,
            "hallucinated_code_reference_rate": benchmark.hallucinated_code_reference_rate,
            "median_latency_seconds": benchmark.median_latency_seconds,
            "p95_latency_seconds": benchmark.p95_latency_seconds,
            "review_queue_rate": benchmark.review_queue_rate,
            "reviewer_correction_rate": benchmark.reviewer_correction_rate,
            "extraction_count": len(rows),
        }

        if self.stage1a_quality_baseline is None:
            self.stage1a_quality_baseline = {k: float(v) for k, v in metrics.items() if isinstance(v, (int, float))}

        baseline = self.stage1a_quality_baseline or {}
        drift_reasons: list[str] = []
        for key in ("discipline_precision", "comment_capture_recall", "review_queue_rate"):
            if key not in baseline:
                continue
            delta = abs(float(metrics[key]) - float(baseline[key]))
            if delta > 0.1:
                drift_reasons.append(f"{key}_delta_gt_0.10")
        if metrics["hallucinated_code_reference_rate"] > max(0.08, float(baseline.get("hallucinated_code_reference_rate", 0.0)) + 0.05):
            drift_reasons.append("hallucinated_code_reference_rate_spike")

        return {
            "bootstrapped": True,
            "generated_at": _iso(),
            "target": target,
            "metrics": metrics,
            "baseline": baseline,
            "drift": {
                "detected": len(drift_reasons) > 0,
                "reasons": drift_reasons,
            },
            "release_gate": {
                "pass": gate_passed,
                "reasons": gate_reasons,
            },
        }

    def permit_ops(self, *, limit: int = 25) -> dict:
        if not self.ids:
            return {
                "bootstrapped": False,
                "connector_health": {},
                "transition_review_queue": {"open_count": 0, "items": []},
                "drift_alerts": {"open_count": 0, "items": []},
                "reconciliation": {"runs": []},
            }

        org_id = self.ids.organization_id
        recent_runs = self.stage2_repo.list_recent_poll_runs(organization_id=org_id, limit=200)
        succeeded = sum(1 for row in recent_runs if row.get("status") == "succeeded")
        failed = sum(1 for row in recent_runs if row.get("status") == "failed")
        partial = sum(1 for row in recent_runs if row.get("status") == "partial")
        total_runs = len(recent_runs)
        success_rate = 0.0 if total_runs == 0 else round(succeeded / total_runs, 4)
        latest = recent_runs[0] if recent_runs else None

        review_rows = self.stage2_repo.list_transition_reviews_by_org(
            organization_id=org_id,
            limit=max(1, int(limit)),
            resolution_state="open",
        )
        drift_rows = self.stage2_repo.list_drift_alerts_by_org(org_id)[: max(1, int(limit))]
        open_drift_rows = [row for row in drift_rows if row.get("status") == "open"]
        recon_rows = self.stage2_repo.list_recent_reconciliation_runs_by_org(
            organization_id=org_id,
            limit=max(1, int(limit)),
        )

        return {
            "bootstrapped": True,
            "generated_at": _iso(),
            "connector_health": {
                "runs_total": total_runs,
                "runs_succeeded": succeeded,
                "runs_partial": partial,
                "runs_failed": failed,
                "success_rate": success_rate,
                "latest_run_status": None if not latest else latest.get("status"),
                "latest_run_started_at": None if not latest else latest.get("run_started_at"),
                "latest_run_finished_at": None if not latest else latest.get("run_finished_at"),
            },
            "transition_review_queue": {
                "open_count": len(review_rows),
                "items": review_rows,
            },
            "drift_alerts": {
                "open_count": len(open_drift_rows),
                "total_count": len(drift_rows),
                "items": open_drift_rows,
            },
            "reconciliation": {
                "runs": recon_rows,
                "latest_status": None if not recon_rows else recon_rows[0].get("status"),
            },
        }

    def finance_ops(self, *, limit: int = 25) -> dict:
        if not self.ids:
            return {
                "bootstrapped": False,
                "payouts": {"total": 0, "state_breakdown": {}, "recent_instructions": []},
                "financial_events": [],
                "reconciliation": {"runs": []},
                "outbox": {"pending_count": 0, "failed_count": 0},
            }

        org_id = self.ids.organization_id
        instructions = self.stage3_store.repository.list_payout_instructions_by_org(
            organization_id=org_id,
            limit=max(1, int(limit)),
        )
        state_breakdown: dict[str, int] = {}
        for row in instructions:
            state = str(row.get("instruction_state") or "unknown")
            state_breakdown[state] = state_breakdown.get(state, 0) + 1

        events = self.stage3_store.repository.list_financial_events_by_org(org_id)
        recent_events = sorted(events, key=lambda row: str(row.get("occurred_at", "")), reverse=True)[: max(1, int(limit))]
        recon_runs = self.stage3_store.repository.list_reconciliation_runs_by_org(
            organization_id=org_id,
            limit=max(1, int(limit)),
        )
        outbox = self.stage3_store.repository.list_outbox_events(publish_state=None, limit=500)
        pending_count = sum(
            1 for row in outbox if row.get("organization_id") == org_id and row.get("publish_state") == "pending"
        )
        failed_count = sum(
            1 for row in outbox if row.get("organization_id") == org_id and row.get("publish_state") == "failed"
        )

        return {
            "bootstrapped": True,
            "generated_at": _iso(),
            "payouts": {
                "total": len(instructions),
                "state_breakdown": state_breakdown,
                "recent_instructions": instructions,
            },
            "financial_events": recent_events,
            "reconciliation": {
                "runs": recon_runs,
                "latest_status": None if not recon_runs else recon_runs[0].get("run_status"),
            },
            "outbox": {
                "pending_count": pending_count,
                "failed_count": failed_count,
            },
        }

    def enterprise_ops(self, *, limit: int = 25) -> dict:
        if not self.ids:
            return {
                "bootstrapped": False,
                "webhooks": {"total": 0, "active": 0, "recent": []},
                "connector_runs": {"total": 0, "recent": []},
                "api_credentials": {"total": 0, "active": 0, "recent": []},
                "task_templates": {"total": 0, "active": 0, "recent": []},
                "audit_exports": {"total": 0, "recent": []},
                "dashboard": None,
                "telemetry": {"total": 0, "recent": []},
                "integration_readiness": {
                    "bootstrapped": False,
                    "overall_ready": False,
                    "launch_blockers": ["workspace_not_bootstrapped"],
                },
                "slo": self.composite_slo_snapshot(),
                "launch_readiness": self.launch_readiness(),
            }
        self._enforce_stage05_runtime_boundary()

        org_id = self.ids.organization_id
        webhooks = [row for row in self.stage05_store.webhook_subscriptions_by_id.values() if row["organization_id"] == org_id]
        deliveries = [row for row in self.stage05_store.webhook_deliveries_by_id.values() if row["organization_id"] == org_id]
        dead_letters = [
            row for row in self.stage05_store.webhook_dead_letters_by_delivery.values() if row["organization_id"] == org_id
        ]
        connector_runs = [row for row in self.stage05_store.connector_runs_by_id.values() if row["organization_id"] == org_id]
        credentials = [row for row in self.stage05_store.api_credentials_by_id.values() if row["organization_id"] == org_id]
        templates = [row for row in self.stage05_store.task_templates_by_id.values() if row["organization_id"] == org_id]
        exports = [row for row in self.stage05_store.security_audit_exports_by_id.values() if row["organization_id"] == org_id]

        dashboard_status, dashboard_payload = get_dashboard_portfolio_api(
            auth_context=self._stage05_owner_auth(),
            store=self.stage05_store,
            **self._stage05_runtime_kwargs(),
        )
        dashboard = dashboard_payload if dashboard_status == 200 else None
        slo = self.composite_slo_snapshot()

        return {
            "bootstrapped": True,
            "generated_at": _iso(),
            "webhooks": {
                "total": len(webhooks),
                "active": sum(1 for row in webhooks if row.get("is_active")),
                "recent": sorted(webhooks, key=lambda row: str(row.get("created_at", "")), reverse=True)[: max(1, int(limit))],
                "deliveries_recent": sorted(
                    deliveries, key=lambda row: str(row.get("created_at", "")), reverse=True
                )[: max(1, int(limit))],
                "dead_letter_total": len(dead_letters),
            },
            "connector_runs": {
                "total": len(connector_runs),
                "recent": sorted(connector_runs, key=lambda row: str(row.get("started_at", "")), reverse=True)[
                    : max(1, int(limit))
                ],
            },
            "api_credentials": {
                "total": len(credentials),
                "active": sum(1 for row in credentials if not row.get("revoked_at")),
                "recent": sorted(credentials, key=lambda row: str(row.get("created_at", "")), reverse=True)[
                    : max(1, int(limit))
                ],
            },
            "task_templates": {
                "total": len(templates),
                "active": sum(1 for row in templates if row.get("is_active")),
                "recent": sorted(templates, key=lambda row: str(row.get("updated_at", "")), reverse=True)[
                    : max(1, int(limit))
                ],
            },
            "audit_exports": {
                "total": len(exports),
                "recent": sorted(exports, key=lambda row: str(row.get("updated_at", "")), reverse=True)[
                    : max(1, int(limit))
                ],
            },
            "dashboard": dashboard,
            "slo": slo,
            "telemetry": {
                "total": len(self.telemetry_events),
                "recent": list(reversed(self.telemetry_events))[: max(1, int(limit))],
            },
            "integration_readiness": self.integration_readiness(),
            "launch_readiness": self.launch_readiness(),
            "alerts": self.enterprise_alerts(),
        }


STATE = DemoAppState()


def _build_candidates_from_page_text(page_text_by_number: dict[int, str]) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for page_no in sorted(page_text_by_number.keys()):
        text = str(page_text_by_number[page_no]).strip()
        if len(text) < 24:
            text = f"{text} Please provide the required correction package."
        lower = text.lower()
        if "panel" in lower or "nec" in lower or "electrical" in lower:
            discipline = "electrical"
        elif "duct" in lower or "mechanical" in lower or "imc" in lower:
            discipline = "mechanical"
        elif "fire" in lower or "alarm" in lower or "ifc" in lower:
            discipline = "fire"
        elif "plumbing" in lower or "ipc" in lower:
            discipline = "plumbing"
        else:
            discipline = "architectural"

        code_match = re.search(r"\b(IBC|IRC|IECC|IFC|NEC|IPC|IMC|NFPA)\s*[0-9][0-9A-Za-z().-]*\b", text, re.IGNORECASE)
        code_ref = code_match.group(0).upper() if code_match else "NEC 110.3"
        quote = text[: min(90, len(text))]
        candidates.append(
            {
                "raw_text": text,
                "discipline": discipline,
                "severity": "major",
                "requested_action": f"Revise and resubmit: {text} Include supporting calculations and updated sheets.",
                "code_reference": code_ref,
                "page_number": int(page_no),
                "citation": {
                    "quote": quote,
                    "char_start": 0,
                    "char_end": max(1, len(quote)),
                },
                "model_prob_discipline": 0.95,
                "model_prob_severity": 0.92,
                "model_prob_code_reference": 0.94,
            }
        )
    return candidates


def _build_candidates(raw_text: str) -> tuple[list[dict[str, object]], dict[int, str]]:
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    if not lines:
        lines = [
            "Revise panel schedule per NEC 408.4 and provide updated load calculations.",
            "Provide duct sizing report per IMC 603.2 and include stamped calculations.",
            "Clarify fire alarm riser and add sequence of operations notes per IFC 907.4.",
        ]
    page_text = {idx: line for idx, line in enumerate(lines, start=1)}
    return _build_candidates_from_page_text(page_text), page_text


class WebHandler(BaseHTTPRequestHandler):
    server_version = "AtlaslyWeb/1.0"

    def _bearer_token(self) -> str:
        auth_header = self.headers.get("Authorization", "").strip()
        if auth_header.lower().startswith("bearer "):
            return auth_header[7:].strip()
        return self.headers.get("X-Session-Token", "").strip()

    def _authorize_request(self, *, method: str, path: str) -> dict | None:
        allowed_roles = STATE.allowed_roles_for_route(method=method, path=path)
        if allowed_roles is None:
            return None
        session = STATE.require_session(token=self._bearer_token(), allowed_roles=allowed_roles)
        if path.startswith("/api/enterprise/"):
            STATE._enforce_stage05_runtime_boundary()
        return session

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            self._authorize_request(method="GET", path=path)
            if path == "/api/health":
                self._json(HTTPStatus.OK, {"ok": True, "time": _iso()})
                return

            if path == "/api/summary":
                self._json(HTTPStatus.OK, STATE.summary())
                return

            if path == "/api/sessions":
                self._json(HTTPStatus.OK, STATE.sessions_payload())
                return

            if path == "/api/portfolio":
                self._json(HTTPStatus.OK, STATE.portfolio())
                return

            if path == "/api/activity":
                qp = parse_qs(parsed.query)
                limit_raw = qp.get("limit", ["40"])[0]
                try:
                    limit = max(1, min(200, int(limit_raw)))
                except ValueError:
                    limit = 40
                self._json(HTTPStatus.OK, STATE.activity_feed(limit=limit))
                return

            if path == "/api/permit-ops":
                qp = parse_qs(parsed.query)
                limit_raw = qp.get("limit", ["25"])[0]
                try:
                    limit = max(1, min(200, int(limit_raw)))
                except ValueError:
                    limit = 25
                self._json(HTTPStatus.OK, STATE.permit_ops(limit=limit))
                return

            if path == "/api/finance-ops":
                qp = parse_qs(parsed.query)
                limit_raw = qp.get("limit", ["25"])[0]
                try:
                    limit = max(1, min(200, int(limit_raw)))
                except ValueError:
                    limit = 25
                self._json(HTTPStatus.OK, STATE.finance_ops(limit=limit))
                return

            if path == "/api/enterprise/overview":
                qp = parse_qs(parsed.query)
                limit_raw = qp.get("limit", ["25"])[0]
                try:
                    limit = max(1, min(200, int(limit_raw)))
                except ValueError:
                    limit = 25
                self._json(HTTPStatus.OK, STATE.enterprise_ops(limit=limit))
                return

            if path == "/api/enterprise/webhook-events":
                if not STATE.ids:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bootstrap required"})
                    return
                qp = parse_qs(parsed.query)
                raw = {
                    "subscription_id": qp.get("subscription_id", [None])[0],
                    "status": qp.get("status", [None])[0],
                    "from": qp.get("from", [None])[0],
                    "to": qp.get("to", [None])[0],
                    "attempt_gte": qp.get("attempt_gte", [None])[0],
                    "limit": qp.get("limit", ["100"])[0],
                }
                query_params: dict[str, object] = {}
                try:
                    for key, value in raw.items():
                        if value in {None, ""}:
                            continue
                        if key in {"attempt_gte", "limit"}:
                            query_params[key] = int(str(value))
                        else:
                            query_params[key] = value
                except ValueError:
                    self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": "attempt_gte and limit must be integers"})
                    return
                status, payload = get_webhook_events_api(
                    query_params=query_params,
                    auth_context=STATE._stage05_owner_auth(),
                    store=STATE.stage05_store,
                    **STATE._stage05_runtime_kwargs(),
                )
                self._json(HTTPStatus(status), payload)
                return

            if path == "/api/enterprise/dashboard":
                if not STATE.ids:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bootstrap required"})
                    return
                status, payload = get_dashboard_portfolio_api(
                    auth_context=STATE._stage05_owner_auth(),
                    store=STATE.stage05_store,
                    **STATE._stage05_runtime_kwargs(),
                )
                self._json(HTTPStatus(status), payload)
                return

            if path == "/api/enterprise/alerts":
                self._json(HTTPStatus.OK, STATE.enterprise_alerts())
                return

            if path == "/api/enterprise/slo":
                if not STATE.ids:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bootstrap required"})
                    return
                payload = STATE.composite_slo_snapshot()
                self._json(HTTPStatus.OK, payload)
                return

            if path == "/api/enterprise/integrations-readiness":
                self._json(HTTPStatus.OK, STATE.integration_readiness())
                return

            if path == "/api/enterprise/launch-readiness":
                self._json(HTTPStatus.OK, STATE.launch_readiness())
                return

            if path == "/api/enterprise/audit-evidence":
                if not STATE.ids:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bootstrap required"})
                    return
                qp = parse_qs(parsed.query)
                export_id = str(qp.get("export_id", [STATE.last_audit_export_id or ""])[0]).strip()
                if not export_id:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "export_id is required"})
                    return
                payload = build_security_audit_evidence_pack(
                    export_id=export_id,
                    auth_context=STATE._stage05_owner_auth(),
                    store=STATE.stage05_store,
                    now=datetime.now(timezone.utc),
                )
                self._json(HTTPStatus.OK, payload)
                return

            if path == "/api/telemetry":
                qp = parse_qs(parsed.query)
                limit_raw = qp.get("limit", ["200"])[0]
                try:
                    limit = max(1, min(1000, int(limit_raw)))
                except ValueError:
                    limit = 200
                self._json(
                    HTTPStatus.OK,
                    {
                        "generated_at": _iso(),
                        "count": min(limit, len(STATE.telemetry_events)),
                        "items": list(reversed(STATE.telemetry_events))[:limit],
                    },
                )
                return

            if path == "/api/stage1a/quality-report":
                qp = parse_qs(parsed.query)
                target = str(qp.get("target", ["staging"])[0] or "staging").strip().lower()
                if target not in {"staging", "prod"}:
                    self._json(
                        HTTPStatus.UNPROCESSABLE_ENTITY,
                        {"error": {"code": "validation_error", "message": "target must be staging or prod"}},
                    )
                    return
                self._json(HTTPStatus.OK, STATE.stage1a_quality_report(target=target))
                return

            if path == "/api/stage1b/tasks":
                ticket_store = STATE.stage1b_repo.load_ticket_store()
                tasks = sorted(ticket_store.tasks_by_id.values(), key=lambda row: row["created_at"], reverse=True)
                self._json(
                    HTTPStatus.OK,
                    {
                        "tasks": tasks,
                        "manual_queue": list(ticket_store.manual_queue_by_task_id.values()),
                        "outbox_events": ticket_store.outbox_events,
                    },
                )
                return

            if path == "/api/stage1b/routing-audit":
                ticket_store = STATE.stage1b_repo.load_ticket_store()
                qp = parse_qs(parsed.query)
                limit_raw = qp.get("limit", ["50"])[0]
                try:
                    limit = max(1, min(200, int(limit_raw)))
                except ValueError:
                    limit = 50
                tasks = sorted(
                    ticket_store.tasks_by_id.values(),
                    key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""),
                    reverse=True,
                )
                feedback_summary: dict[str, int] = {}
                for feedback in ticket_store.task_feedback_by_id.values():
                    reason = str(feedback.get("feedback_reason_code") or "unspecified")
                    feedback_summary[reason] = feedback_summary.get(reason, 0) + 1
                manual_reason_summary: dict[str, int] = {}
                for manual in ticket_store.manual_queue_by_task_id.values():
                    reason = str(manual.get("reason") or "unknown")
                    manual_reason_summary[reason] = manual_reason_summary.get(reason, 0) + 1
                rows = []
                for task in tasks[:limit]:
                    task_id = str(task.get("id") or "")
                    manual = ticket_store.manual_queue_by_task_id.get(task_id)
                    rows.append(
                        {
                            "task_id": task_id,
                            "discipline": task.get("discipline"),
                            "auto_assigned": bool(task.get("auto_assigned")),
                            "assignee_user_id": task.get("assignee_user_id"),
                            "routing_decision": task.get("routing_decision"),
                            "routing_reason": task.get("routing_reason") or (manual or {}).get("reason"),
                            "routing_rule_id": task.get("routing_rule_id") or (manual or {}).get("rule_id"),
                            "routing_confidence": task.get("routing_confidence")
                            if task.get("routing_confidence") is not None
                            else task.get("assignment_confidence"),
                            "manual_queueed_at": None if not manual else manual.get("queued_at"),
                            "manual_queue_reason": None if not manual else manual.get("reason"),
                            "updated_at": task.get("updated_at"),
                        }
                    )
                self._json(
                    HTTPStatus.OK,
                    {
                        "generated_at": _iso(),
                        "summary": {
                            "tasks_total": len(tasks),
                            "manual_queue_total": len(ticket_store.manual_queue_by_task_id),
                            "auto_assigned_total": sum(1 for row in tasks if row.get("auto_assigned")),
                            "feedback_events_total": len(ticket_store.task_feedback_by_id),
                        },
                        "feedback_reason_breakdown": feedback_summary,
                        "manual_queue_reason_breakdown": manual_reason_summary,
                        "items": rows,
                    },
                )
                return

            if path == "/api/stage2/timeline":
                if not STATE.ids:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bootstrap required"})
                    return
                qp = parse_qs(parsed.query)
                permit_id = qp.get("permit_id", [STATE.ids.permit_id])[0]
                status, payload = get_status_timeline_persisted(
                    permit_id=permit_id,
                    query_params={"limit": 50},
                    auth_context=STATE._stage2_sync_auth(),
                    repository=STATE.stage2_repo,
                )
                self._json(HTTPStatus(status), payload)
                return

            if path == "/api/stage2/connector-credentials":
                if not STATE.ids:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bootstrap required"})
                    return
                qp = parse_qs(parsed.query)
                connector = qp.get("connector", [None])[0]
                rows = STATE.stage2_repo.list_connector_credentials(
                    organization_id=STATE.ids.organization_id,
                    connector=None if connector in {None, ""} else str(connector),
                    limit=50,
                )
                self._json(HTTPStatus.OK, {"items": rows, "count": len(rows)})
                return

            if path == "/api/stage2/permit-bindings":
                if not STATE.ids:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bootstrap required"})
                    return
                qp = parse_qs(parsed.query)
                connector = str(qp.get("connector", [""])[0]).strip().lower() or None
                ahj_id = str(qp.get("ahj_id", [""])[0]).strip().lower() or None
                permit_id = str(qp.get("permit_id", [""])[0]).strip() or None
                rows = STATE.stage2_repo.list_external_permit_bindings(
                    organization_id=STATE.ids.organization_id,
                    connector=connector,
                    ahj_id=ahj_id,
                    permit_id=permit_id,
                    limit=100,
                )
                self._json(HTTPStatus.OK, {"items": rows, "count": len(rows)})
                return

            if path == "/api/stage3/outbox":
                events = STATE.stage3_store.repository.list_outbox_events(publish_state=None, limit=200)
                self._json(HTTPStatus.OK, {"events": events})
                return

            if path == "/api/stage1a/letters":
                letters = sorted(
                    STATE.stage1a_store.letters_by_id.values(),
                    key=lambda l: str(l.get("created_at") or ""),
                    reverse=True,
                )
                self._json(HTTPStatus.OK, {"letters": list(letters), "count": len(letters)})
                return

            if path == "/api/stage1a/extractions":
                if not STATE.ids:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bootstrap required"})
                    return
                qp = parse_qs(parsed.query)
                letter_id = str(qp.get("letter_id", [""])[0]).strip()
                if not letter_id:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "letter_id is required"})
                    return
                status, payload = get_comment_letter_extractions(
                    letter_id=letter_id,
                    auth_context=STATE._stage1a_reviewer_auth(),
                    store=STATE.stage1a_store,
                )
                self._json(HTTPStatus(status), payload)
                return

            if path == "/api/enterprise/webhooks":
                if not STATE.ids:
                    self._json(HTTPStatus.OK, {"webhooks": [], "count": 0})
                    return
                org_id = STATE.ids.organization_id
                webhooks = sorted(
                    [row for row in STATE.stage05_store.webhook_subscriptions_by_id.values()
                     if row.get("organization_id") == org_id],
                    key=lambda w: str(w.get("created_at") or ""),
                    reverse=True,
                )
                self._json(HTTPStatus.OK, {"webhooks": webhooks, "count": len(webhooks)})
                return

            if path == "/api/enterprise/api-keys":
                if not STATE.ids:
                    self._json(HTTPStatus.OK, {"keys": [], "count": 0})
                    return
                org_id = STATE.ids.organization_id
                keys = sorted(
                    [row for row in STATE.stage05_store.api_credentials_by_id.values()
                     if row.get("organization_id") == org_id],
                    key=lambda k: str(k.get("created_at") or ""),
                    reverse=True,
                )
                self._json(HTTPStatus.OK, {"keys": keys, "count": len(keys)})
                return

            if path == "/api/enterprise/task-templates":
                if not STATE.ids:
                    self._json(HTTPStatus.OK, {"templates": [], "count": 0})
                    return
                org_id = STATE.ids.organization_id
                templates = sorted(
                    [
                        row for row in STATE.stage05_store.task_templates_by_id.values()
                        if row.get("organization_id") == org_id
                    ],
                    key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""),
                    reverse=True,
                )
                self._json(HTTPStatus.OK, {"templates": templates, "count": len(templates)})
                return

            self._serve_static(path)
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, SessionAuthError):
                self._json(HTTPStatus(exc.status), {"error": {"code": exc.code, "message": exc.message}})
                return
            if isinstance(exc, Stage1ARequestError):
                self._json(HTTPStatus(exc.status), {"error": {"code": exc.code, "message": exc.message}})
                return
            if isinstance(exc, AhjIntelligenceError):
                self._json(HTTPStatus(exc.status), {"error": {"code": exc.code, "message": exc.message}})
                return
            if isinstance(exc, ConnectorCredentialError):
                self._json(HTTPStatus(exc.status), {"error": {"code": exc.code, "message": exc.message}})
                return
            if isinstance(exc, EnterpriseReadinessError):
                self._json(HTTPStatus(exc.status), {"error": {"code": exc.code, "message": exc.message}})
                return
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._read_json_body()

        try:
            if path in {"/api/demo/reset", "/api/demo/run-scenario"} and not STATE.demo_routes_enabled:
                self._json(
                    HTTPStatus.FORBIDDEN,
                    {
                        "error": {
                            "code": "route_disabled_in_tier",
                            "message": f"{path} is disabled for deployment tier {STATE.deployment_tier}",
                        }
                    },
                )
                return
            session = self._authorize_request(method="POST", path=path)
            if path == "/api/bootstrap":
                payload = STATE.bootstrap()
                self._json(HTTPStatus.OK, payload)
                return

            if path == "/api/demo/reset":
                payload = STATE.reset_workspace(bootstrap=bool(body.get("bootstrap", True)))
                self._json(HTTPStatus.OK, payload)
                return

            if path == "/api/demo/run-scenario":
                payload = STATE.reset_workspace(bootstrap=True)
                demo_text = (
                    "Revise panel schedule per NEC 408.4 and provide updated load calculations.\n"
                    "Provide duct sizing report per IMC 603.2 and include stamped calculations.\n"
                    "Clarify fire alarm sequence of operations per IFC 907.4.\n"
                )
                parse_status, parse_payload = post_comment_letters(
                    request_body={
                        "project_id": STATE.ids.project_id,
                        "document_id": str(uuid.uuid4()),
                        "source_filename": "demo-comments.txt",
                    },
                    idempotency_key=f"demo-letter-{uuid.uuid4()}",
                    trace_id=str(uuid.uuid4()),
                    auth_context=STATE._stage1a_reviewer_auth(),
                    store=STATE.stage1a_store,
                )
                if parse_status not in {200, 202}:
                    self._json(HTTPStatus(parse_status), parse_payload)
                    return
                candidates, page_text = _build_candidates(demo_text)
                process_extraction_candidates(
                    letter_id=parse_payload["letter_id"],
                    candidates=candidates,
                    page_text_by_number=page_text,
                    ocr_quality_by_page={page: 0.92 for page in page_text},
                    trace_id=str(uuid.uuid4()),
                    auth_context=STATE._stage1a_reviewer_auth(),
                    store=STATE.stage1a_store,
                )
                STATE.last_letter_id = str(parse_payload["letter_id"])
                approve_status, approve_payload = post_comment_letter_approve(
                    letter_id=STATE.last_letter_id,
                    request_body={},
                    trace_id=str(uuid.uuid4()),
                    auth_context=STATE._stage1a_reviewer_auth(),
                    store=STATE.stage1a_store,
                )
                self._json(
                    HTTPStatus.OK if approve_status == 200 else HTTPStatus(approve_status),
                    {
                        "workspace": payload,
                        "letter_id": STATE.last_letter_id,
                        "approval": approve_payload,
                    },
                )
                return

            if path == "/api/feedback":
                if not STATE.ids:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bootstrap required"})
                    return
                try:
                    payload = STATE.record_feedback(
                        message=str(body.get("message") or ""),
                        rating=int(body.get("rating") or 5),
                        category=str(body.get("category") or "general"),
                        context=body.get("context") if isinstance(body.get("context"), dict) else {},
                        session=session,
                    )
                except ValueError as exc:
                    self._json(
                        HTTPStatus.UNPROCESSABLE_ENTITY,
                        {"error": {"code": "validation_error", "message": str(exc)}},
                    )
                    return
                self._json(HTTPStatus.CREATED, payload)
                return

            if path == "/api/telemetry":
                if not STATE.ids:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bootstrap required"})
                    return
                payload = STATE.record_telemetry(
                    event_type=str(body.get("event_type") or "ui.event"),
                    level=str(body.get("level") or "info"),
                    payload=body.get("payload") if isinstance(body.get("payload"), dict) else {},
                    session=session,
                )
                self._json(HTTPStatus.CREATED, payload)
                return

            if path == "/api/enterprise/webhooks":
                if not STATE.ids:
                    STATE.bootstrap()
                assert STATE.ids is not None
                status, payload = post_webhooks(
                    request_body={
                        "target_url": str(body.get("target_url") or "https://hooks.example.com/atlasly"),
                        "event_types": body.get("event_types")
                        or [
                            "permit.status_changed",
                            "task.created",
                            "integration.run_completed",
                        ],
                    },
                    headers={
                        "Idempotency-Key": str(body.get("idempotency_key") or f"ent-webhook-{uuid.uuid4()}"),
                        "X-Trace-Id": str(uuid.uuid4()),
                    },
                    auth_context=STATE._stage05_owner_auth(),
                    store=STATE.stage05_store,
                    **STATE._stage05_runtime_kwargs(),
                    now=datetime.now(timezone.utc),
                )
                if status in {200, 201} and payload.get("subscription_id"):
                    STATE.last_webhook_subscription_id = str(payload["subscription_id"])
                self._json(HTTPStatus(status), payload)
                return

            if path == "/api/enterprise/webhook-delivery":
                if not STATE.ids:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bootstrap required"})
                    return
                subscription_id = str(body.get("subscription_id") or STATE.last_webhook_subscription_id or "").strip()
                if not subscription_id:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "subscription_id is required"})
                    return
                try:
                    delivery = record_webhook_delivery_attempt(
                        subscription_id=subscription_id,
                        event_id=str(body.get("event_id") or f"evt-{uuid.uuid4().hex[:10]}"),
                        event_name=str(body.get("event_name") or "permit.status_changed"),
                        payload=body.get("payload") if isinstance(body.get("payload"), dict) else {"demo": True},
                        attempt=int(body.get("attempt") or 1),
                        response_code=(None if body.get("response_code") in {None, ""} else int(body["response_code"])),
                        error_code=(None if body.get("error_code") in {None, ""} else str(body.get("error_code"))),
                        error_detail=(None if body.get("error_detail") in {None, ""} else str(body.get("error_detail"))),
                        trace_id=str(uuid.uuid4()),
                        auth_context=STATE._stage05_owner_auth(),
                        store=STATE.stage05_store,
                        now=datetime.now(timezone.utc),
                    )
                except ValueError:
                    self._json(
                        HTTPStatus.UNPROCESSABLE_ENTITY,
                        {"error": "attempt and response_code must be integers when provided"},
                    )
                    return
                self._json(HTTPStatus.OK, delivery)
                return

            if path == "/api/enterprise/webhook-replay":
                if not STATE.ids:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bootstrap required"})
                    return
                delivery_id = str(body.get("delivery_id") or "").strip()
                if not delivery_id:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "delivery_id is required"})
                    return
                replay = request_webhook_replay(
                    delivery_id=delivery_id,
                    reason=str(body.get("reason") or "manual replay from control tower"),
                    auth_context=STATE._stage05_owner_auth(),
                    store=STATE.stage05_store,
                    now=datetime.now(timezone.utc),
                )
                self._json(HTTPStatus.OK, replay)
                return

            if path == "/api/enterprise/connector-sync":
                if not STATE.ids:
                    STATE.bootstrap()
                assert STATE.ids is not None
                connector_name = str(body.get("connector_name") or "accela_api")
                status, payload = post_connector_sync(
                    connector_name=connector_name,
                    request_body={"run_mode": str(body.get("run_mode") or "delta")},
                    headers={
                        "Idempotency-Key": str(body.get("idempotency_key") or f"ent-sync-{uuid.uuid4()}"),
                        "X-Trace-Id": str(uuid.uuid4()),
                    },
                    auth_context=STATE._stage05_owner_auth(),
                    store=STATE.stage05_store,
                    **STATE._stage05_runtime_kwargs(),
                    now=datetime.now(timezone.utc),
                )
                if status in {200, 202} and payload.get("run_id"):
                    STATE.last_connector_run_id = str(payload["run_id"])
                self._json(HTTPStatus(status), payload)
                return

            if path == "/api/enterprise/connector-error":
                if not STATE.ids:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bootstrap required"})
                    return
                run_id = str(body.get("run_id") or STATE.last_connector_run_id or "").strip()
                if not run_id:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "run_id is required"})
                    return
                payload = record_connector_error(
                    run_id=run_id,
                    classification=str(body.get("classification") or "internal.transient"),
                    message=str(body.get("message") or "connector retryable failure"),
                    auth_context=STATE._stage05_owner_auth(),
                    store=STATE.stage05_store,
                    external_code=(None if body.get("external_code") in {None, ""} else str(body.get("external_code"))),
                    external_record_id=(
                        None if body.get("external_record_id") in {None, ""} else str(body.get("external_record_id"))
                    ),
                    payload_excerpt_redacted=(
                        body.get("payload_excerpt_redacted")
                        if isinstance(body.get("payload_excerpt_redacted"), dict)
                        else {}
                    ),
                    is_retryable=(
                        None
                        if body.get("is_retryable") in {None, ""}
                        else bool(body.get("is_retryable"))
                    ),
                    now=datetime.now(timezone.utc),
                )
                self._json(HTTPStatus.OK, payload)
                return

            if path == "/api/enterprise/connector-complete":
                if not STATE.ids:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bootstrap required"})
                    return
                run_id = str(body.get("run_id") or STATE.last_connector_run_id or "").strip()
                if not run_id:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "run_id is required"})
                    return
                try:
                    payload = complete_connector_sync(
                        run_id=run_id,
                        final_status=str(body.get("final_status") or "succeeded"),
                        records_fetched=int(body.get("records_fetched") or 12),
                        records_synced=int(body.get("records_synced") or 12),
                        records_failed=int(body.get("records_failed") or 0),
                        trace_id=str(uuid.uuid4()),
                        auth_context=STATE._stage05_owner_auth(),
                        store=STATE.stage05_store,
                        now=datetime.now(timezone.utc),
                    )
                except ValueError:
                    self._json(
                        HTTPStatus.UNPROCESSABLE_ENTITY,
                        {"error": "records_fetched, records_synced, and records_failed must be integers"},
                    )
                    return
                self._json(HTTPStatus.OK, payload)
                return

            if path == "/api/enterprise/api-keys":
                if not STATE.ids:
                    STATE.bootstrap()
                assert STATE.ids is not None
                status, payload = post_org_api_keys(
                    org_id=STATE.ids.organization_id,
                    request_body={
                        "name": str(body.get("name") or "demo service key"),
                        "scopes": body.get("scopes") or ["dashboard:read", "webhooks:read"],
                        "expires_at": body.get("expires_at"),
                    },
                    headers={
                        "Idempotency-Key": str(body.get("idempotency_key") or f"ent-key-{uuid.uuid4()}"),
                        "X-Trace-Id": str(uuid.uuid4()),
                    },
                    auth_context=STATE._stage05_owner_auth(),
                    store=STATE.stage05_store,
                    **STATE._stage05_runtime_kwargs(),
                    now=datetime.now(timezone.utc),
                )
                if status in {200, 201} and payload.get("credential_id"):
                    STATE.last_api_credential_id = str(payload["credential_id"])
                self._json(HTTPStatus(status), payload)
                return

            if path == "/api/enterprise/api-keys/mark-used":
                if not STATE.ids:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bootstrap required"})
                    return
                credential_id = str(body.get("credential_id") or STATE.last_api_credential_id or "").strip()
                if not credential_id:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "credential_id is required"})
                    return
                payload = mark_api_key_used(
                    credential_id=credential_id,
                    usage_source=str(body.get("usage_source") or "control_tower_demo"),
                    auth_context=STATE._stage05_owner_auth(),
                    store=STATE.stage05_store,
                    now=datetime.now(timezone.utc),
                )
                self._json(HTTPStatus.OK, payload)
                return

            if path == "/api/enterprise/api-keys/policy-scan":
                if not STATE.ids:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bootstrap required"})
                    return
                try:
                    max_age_days = int(body.get("max_age_days") or 90)
                    warning_days = int(body.get("warning_days") or 14)
                except ValueError:
                    self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": "max_age_days and warning_days must be integers"})
                    return
                payload = scan_api_key_rotation_policy(
                    auth_context=STATE._stage05_owner_auth(),
                    store=STATE.stage05_store,
                    max_age_days=max_age_days,
                    warning_days=warning_days,
                    auto_revoke_overdue=bool(body.get("auto_revoke_overdue", False)),
                    now=datetime.now(timezone.utc),
                )
                self._json(HTTPStatus.OK, payload)
                return

            if path == "/api/enterprise/api-keys/revoke":
                if not STATE.ids:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bootstrap required"})
                    return
                credential_id = str(body.get("credential_id") or STATE.last_api_credential_id or "").strip()
                if not credential_id:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "credential_id is required"})
                    return
                payload = revoke_api_key(
                    credential_id=credential_id,
                    reason=str(body.get("reason") or "revoked in control tower"),
                    auth_context=STATE._stage05_owner_auth(),
                    store=STATE.stage05_store,
                    now=datetime.now(timezone.utc),
                )
                self._json(HTTPStatus.OK, payload)
                return

            if path == "/api/enterprise/api-keys/rotate":
                if not STATE.ids:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bootstrap required"})
                    return
                credential_id = str(body.get("credential_id") or STATE.last_api_credential_id or "").strip()
                if not credential_id:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "credential_id is required"})
                    return
                status, payload = rotate_api_key(
                    credential_id=credential_id,
                    new_name=str(body.get("name") or "rotated service key"),
                    new_scopes=body.get("scopes") or ["dashboard:read"],
                    idempotency_key=str(body.get("idempotency_key") or f"ent-key-rotate-{uuid.uuid4()}"),
                    auth_context=STATE._stage05_owner_auth(),
                    store=STATE.stage05_store,
                    now=datetime.now(timezone.utc),
                )
                if status in {200, 201} and payload.get("credential_id"):
                    STATE.last_api_credential_id = str(payload["credential_id"])
                self._json(HTTPStatus(status), payload)
                return

            if path == "/api/enterprise/task-templates":
                if not STATE.ids:
                    STATE.bootstrap()
                assert STATE.ids is not None
                payload = create_task_template(
                    name=str(body.get("name") or "Default Permit Checklist"),
                    description=str(body.get("description") or "System default template"),
                    template=(
                        body.get("template")
                        if isinstance(body.get("template"), dict)
                        else {
                            "steps": ["collect plans", "submit packet", "track reviewer comments"],
                        }
                    ),
                    auth_context=STATE._stage05_owner_auth(),
                    store=STATE.stage05_store,
                    now=datetime.now(timezone.utc),
                )
                STATE.last_task_template_id = str(payload["template_id"])
                self._json(HTTPStatus.CREATED, payload)
                return

            if path == "/api/enterprise/task-templates/archive":
                if not STATE.ids:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bootstrap required"})
                    return
                template_id = str(body.get("template_id") or STATE.last_task_template_id or "").strip()
                if not template_id:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "template_id is required"})
                    return
                payload = archive_task_template(
                    template_id=template_id,
                    auth_context=STATE._stage05_owner_auth(),
                    store=STATE.stage05_store,
                    now=datetime.now(timezone.utc),
                )
                self._json(HTTPStatus.OK, payload)
                return

            if path == "/api/enterprise/audit-exports/request":
                if not STATE.ids:
                    STATE.bootstrap()
                assert STATE.ids is not None
                now = datetime.now(timezone.utc)
                range_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                range_end = now
                payload = request_security_audit_export(
                    time_range_start=range_start,
                    time_range_end=range_end,
                    export_type=str(body.get("export_type") or "audit_timeline"),
                    auth_context=STATE._stage05_owner_auth(),
                    store=STATE.stage05_store,
                    now=now,
                )
                STATE.last_audit_export_id = str(payload["export_id"])
                self._json(HTTPStatus.CREATED, payload)
                return

            if path == "/api/enterprise/audit-exports/run":
                if not STATE.ids:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bootstrap required"})
                    return
                export_id = str(body.get("export_id") or STATE.last_audit_export_id or "").strip()
                if not export_id:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "export_id is required"})
                    return
                payload = mark_security_audit_export_running(
                    export_id=export_id,
                    generated_by=STATE.ids.owner_user_id,
                    auth_context=STATE._stage05_owner_auth(),
                    store=STATE.stage05_store,
                    now=datetime.now(timezone.utc),
                )
                self._json(HTTPStatus.OK, payload)
                return

            if path == "/api/enterprise/audit-exports/complete":
                if not STATE.ids:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bootstrap required"})
                    return
                export_id = str(body.get("export_id") or STATE.last_audit_export_id or "").strip()
                if not export_id:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "export_id is required"})
                    return
                payload = mark_security_audit_export_completed(
                    export_id=export_id,
                    checksum=str(body.get("checksum") or "sha256:demo"),
                    storage_uri=str(body.get("storage_uri") or "s3://atlasly-audit/demo.json"),
                    access_log_ref=str(body.get("access_log_ref") or "audit-log-demo"),
                    generated_by=STATE.ids.owner_user_id,
                    auth_context=STATE._stage05_owner_auth(),
                    store=STATE.stage05_store,
                    now=datetime.now(timezone.utc),
                )
                self._json(HTTPStatus.OK, payload)
                return

            if path == "/api/enterprise/dashboard-snapshot":
                if not STATE.ids:
                    STATE.bootstrap()
                assert STATE.ids is not None
                now = datetime.now(timezone.utc)
                metrics = {
                    "permits_total": len(STATE.stage0_store.permits_by_id),
                    "permit_cycle_time_p50_days": float(body.get("permit_cycle_time_p50_days") or 11.0),
                    "permit_cycle_time_p90_days": float(body.get("permit_cycle_time_p90_days") or 27.0),
                    "corrections_rate": float(body.get("corrections_rate") or 0.22),
                    "approval_rate_30d": float(body.get("approval_rate_30d") or 0.66),
                    "task_sla_breach_rate": float(body.get("task_sla_breach_rate") or 0.07),
                    "connector_health_score": float(body.get("connector_health_score") or 90.0),
                    "webhook_delivery_success_rate": float(body.get("webhook_delivery_success_rate") or 0.995),
                }
                payload = upsert_dashboard_snapshot(
                    metrics=metrics,
                    snapshot_at=now,
                    source_max_event_at=now,
                    auth_context=STATE._stage05_owner_auth(),
                    store=STATE.stage05_store,
                    now=now,
                )
                self._json(HTTPStatus.OK, payload)
                return

            if path == "/api/stage1a/upload":
                if not STATE.ids:
                    STATE.bootstrap()
                assert STATE.ids is not None
                status, payload = enqueue_upload_job(
                    organization_id=STATE.ids.organization_id,
                    project_id=STATE.ids.project_id,
                    filename=str(body.get("filename") or "municipal-comments.pdf"),
                    mime_type=str(body.get("mime_type") or "application/pdf"),
                    document_base64=str(body.get("document_base64") or ""),
                    idempotency_key=str(body.get("idempotency_key") or f"stage1a-upload-{uuid.uuid4()}"),
                    trace_id=str(body.get("trace_id") or str(uuid.uuid4())),
                    store=STATE.stage1a_ingestion_store,
                    now=datetime.now(timezone.utc),
                )
                if payload.get("job_id"):
                    STATE.last_stage1a_upload_job_id = str(payload["job_id"])

                if bool(body.get("auto_process")) and payload.get("job_id"):
                    _, processed = process_upload_job(
                        organization_id=STATE.ids.organization_id,
                        job_id=str(payload["job_id"]),
                        store=STATE.stage1a_ingestion_store,
                        now=datetime.now(timezone.utc),
                    )
                    payload["processed"] = processed

                self._json(HTTPStatus(status), payload)
                return

            if path == "/api/stage1a/process-upload":
                if not STATE.ids:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bootstrap required"})
                    return
                job_id = str(body.get("job_id") or STATE.last_stage1a_upload_job_id or "").strip()
                if job_id:
                    status, payload = process_upload_job(
                        organization_id=STATE.ids.organization_id,
                        job_id=job_id,
                        store=STATE.stage1a_ingestion_store,
                        now=datetime.now(timezone.utc),
                    )
                else:
                    status, payload = process_next_upload_job(
                        organization_id=STATE.ids.organization_id,
                        store=STATE.stage1a_ingestion_store,
                        now=datetime.now(timezone.utc),
                    )
                self._json(HTTPStatus(status), payload)
                return

            if path == "/api/stage1a/parse":
                if not STATE.ids:
                    STATE.bootstrap()
                assert STATE.ids is not None

                parse_text = str(body.get("text") or "")
                page_text: dict[int, str] | None = None
                ocr_quality: dict[int, float] | None = None

                if body.get("job_id") not in {None, ""}:
                    job_id = str(body.get("job_id") or "")
                    _, process_payload = process_upload_job(
                        organization_id=STATE.ids.organization_id,
                        job_id=job_id,
                        store=STATE.stage1a_ingestion_store,
                        now=datetime.now(timezone.utc),
                    )
                    page_text = {
                        int(k): str(v)
                        for k, v in (process_payload.get("page_text_by_number") or {}).items()
                    }
                    ocr_quality = {
                        int(k): float(v)
                        for k, v in (process_payload.get("ocr_quality_by_page") or {}).items()
                    }
                elif body.get("document_base64") not in {None, ""}:
                    upload_status, upload_payload = enqueue_upload_job(
                        organization_id=STATE.ids.organization_id,
                        project_id=STATE.ids.project_id,
                        filename=str(body.get("filename") or "municipal-comments.pdf"),
                        mime_type=str(body.get("mime_type") or "application/pdf"),
                        document_base64=str(body.get("document_base64") or ""),
                        idempotency_key=str(body.get("idempotency_key") or f"stage1a-parse-upload-{uuid.uuid4()}"),
                        trace_id=str(body.get("trace_id") or str(uuid.uuid4())),
                        store=STATE.stage1a_ingestion_store,
                        now=datetime.now(timezone.utc),
                    )
                    if upload_status not in {200, 202}:
                        self._json(HTTPStatus(upload_status), upload_payload)
                        return
                    STATE.last_stage1a_upload_job_id = str(upload_payload["job_id"])
                    _, process_payload = process_upload_job(
                        organization_id=STATE.ids.organization_id,
                        job_id=str(upload_payload["job_id"]),
                        store=STATE.stage1a_ingestion_store,
                        now=datetime.now(timezone.utc),
                    )
                    page_text = {
                        int(k): str(v)
                        for k, v in (process_payload.get("page_text_by_number") or {}).items()
                    }
                    ocr_quality = {
                        int(k): float(v)
                        for k, v in (process_payload.get("ocr_quality_by_page") or {}).items()
                    }

                status, payload = post_comment_letters(
                    request_body={
                        "project_id": STATE.ids.project_id,
                        "document_id": str(uuid.uuid4()),
                        "source_filename": "municipal-comments.pdf",
                    },
                    idempotency_key=f"letter-{uuid.uuid4()}",
                    trace_id=str(uuid.uuid4()),
                    auth_context=STATE._stage1a_reviewer_auth(),
                    store=STATE.stage1a_store,
                )
                if status not in {200, 202}:
                    self._json(HTTPStatus(status), payload)
                    return
                letter_id = payload["letter_id"]

                if page_text:
                    candidates = _build_candidates_from_page_text(page_text)
                else:
                    candidates, page_text = _build_candidates(parse_text)
                normalized_ocr_quality = ocr_quality or {k: 0.92 for k in page_text}
                extraction_status, extraction_payload = process_extraction_candidates(
                    letter_id=letter_id,
                    candidates=candidates,
                    page_text_by_number=page_text,
                    ocr_quality_by_page=normalized_ocr_quality,
                    trace_id=str(uuid.uuid4()),
                    auth_context=STATE._stage1a_reviewer_auth(),
                    store=STATE.stage1a_store,
                )
                _, extraction_rows = get_comment_letter_extractions(
                    letter_id=letter_id,
                    auth_context=STATE._stage1a_reviewer_auth(),
                    store=STATE.stage1a_store,
                )

                STATE.last_letter_id = letter_id
                self._json(
                    HTTPStatus(extraction_status),
                    {
                        "letter_id": letter_id,
                        "summary": extraction_payload,
                        "extractions": extraction_rows["extractions"],
                    },
                )
                return

            if path == "/api/stage1a/approve-and-create-tasks":
                if not STATE.ids or not STATE.last_letter_id:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "parse a comment letter first"})
                    return

                letter_id = STATE.last_letter_id
                _, extraction_payload = get_comment_letter_extractions(
                    letter_id=letter_id,
                    auth_context=STATE._stage1a_reviewer_auth(),
                    store=STATE.stage1a_store,
                )

                for row in extraction_payload["extractions"]:
                    if row["status"] != "needs_review":
                        continue
                    review_extraction(
                        letter_id=letter_id,
                        extraction_id=row["id"],
                        decision="corrected",
                        correction_payload={"code_reference": "NEC 110.3"},
                        rationale="Auto-corrected in demo workflow before approval.",
                        auth_context=STATE._stage1a_reviewer_auth(),
                        store=STATE.stage1a_store,
                    )

                approve_status, approve_payload = post_comment_letter_approve(
                    letter_id=letter_id,
                    request_body={},
                    trace_id=str(uuid.uuid4()),
                    auth_context=STATE._stage1a_reviewer_auth(),
                    store=STATE.stage1a_store,
                )
                if approve_status != 200:
                    self._json(HTTPStatus(approve_status), approve_payload)
                    return

                # Mirror approved extraction set into Stage 1B store.
                ticket_store = STATE.stage1b_repo.load_ticket_store()
                ticket_store.letters_by_id[letter_id] = {
                    "id": letter_id,
                    "organization_id": STATE.ids.organization_id,
                    "project_id": STATE.ids.project_id,
                    "version_hash": "approved-v1",
                }
                approved_ids = []
                for row in extraction_payload["extractions"]:
                    ticket_store.extractions_by_id[row["id"]] = dict(row)
                    approved_ids.append(row["id"])
                STATE.stage1b_repo.save_ticket_store(ticket_store)

                task_status, task_payload = STATE.stage1b_service.post_create_tasks(
                    letter_id=letter_id,
                    request_body={"approved_extraction_ids": approved_ids, "dry_run": False},
                    headers={"Idempotency-Key": f"tasks-{letter_id}", "X-Trace-Id": str(uuid.uuid4())},
                    auth_context=STATE._stage1b_pm_auth(),
                    confidence_threshold=0.75,
                    escalation_policy={
                        "id": "default-policy",
                        "ack_minutes_l1": 60,
                        "max_levels": 3,
                    },
                )
                self._json(
                    HTTPStatus(task_status),
                    {
                        "approval": approve_payload,
                        "task_result": task_payload,
                    },
                )
                return

            if path == "/api/stage1a/review":
                if not STATE.ids:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bootstrap required"})
                    return
                letter_id = str(body.get("letter_id") or "").strip()
                extraction_id = str(body.get("extraction_id") or "").strip()
                action = str(body.get("action") or "accept").strip().lower()
                if not letter_id or not extraction_id:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "letter_id and extraction_id are required"})
                    return
                decision = {"accept": "accepted", "reject": "rejected", "correct": "corrected"}.get(action, action)
                correction_payload = body.get("correction_payload") if isinstance(body.get("correction_payload"), dict) else None
                status, payload = review_extraction(
                    letter_id=letter_id,
                    extraction_id=extraction_id,
                    decision=decision,
                    correction_payload=correction_payload,
                    rationale=str(body.get("note") or body.get("rationale") or "Reviewed in control tower."),
                    auth_context=STATE._stage1a_reviewer_auth(),
                    store=STATE.stage1a_store,
                )
                self._json(HTTPStatus(status), payload)
                return

            if path == "/api/stage1b/escalation-tick":
                tick_key = str(body.get("tick_key") or f"tick-{datetime.now(timezone.utc).replace(second=0, microsecond=0).isoformat()}").strip()
                user_mode = str(body.get("user_mode") or "immediate").strip().lower()
                if user_mode not in {"immediate", "digest"}:
                    self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": "user_mode must be immediate or digest"})
                    return
                payload = STATE.stage1b_service.run_assignment_overdue_worker(
                    user_mode=user_mode,
                    tick_key=tick_key,
                    now=datetime.now(timezone.utc),
                )
                self._json(HTTPStatus.OK, payload)
                return

            if path == "/api/stage1b/assign":
                if not STATE.ids:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bootstrap required"})
                    return
                task_id = str(body.get("task_id") or "").strip()
                assignee_id = str(body.get("assignee_id") or "").strip()
                if not task_id or not assignee_id:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "task_id and assignee_id are required"})
                    return
                ticket_store = STATE.stage1b_repo.load_ticket_store()
                task = ticket_store.tasks_by_id.get(task_id)
                if not task:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "task not found"})
                    return
                task["assignee_user_id"] = assignee_id
                task["updated_at"] = _iso()
                task["status"] = "in_progress" if task.get("status") in {None, "", "open"} else task.get("status")
                ticket_store.outbox_events.append(
                    {
                        "event_id": str(uuid.uuid4()),
                        "organization_id": STATE.ids.organization_id,
                        "event_type": "task.manually_assigned",
                        "aggregate_type": "task",
                        "aggregate_id": task_id,
                        "trace_id": str(uuid.uuid4()),
                        "occurred_at": _iso(),
                        "payload": {"task_id": task_id, "assignee_user_id": assignee_id},
                    }
                )
                STATE.stage1b_repo.save_ticket_store(ticket_store)
                self._json(HTTPStatus.OK, {"task": task})
                return

            if path == "/api/stage2/resolve-ahj":
                address = body.get("address") if isinstance(body.get("address"), dict) else {}
                if not isinstance(address, dict):
                    self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": "address must be an object"})
                    return
                result = STATE._resolve_ahj_with_shovels(address=address)
                if result is None:
                    self._json(
                        HTTPStatus.OK,
                        {
                            "resolved": False,
                            "reason": "shovels_not_configured_or_insufficient_address",
                        },
                    )
                    return
                self._json(HTTPStatus.OK, {"resolved": True, "result": result})
                return

            if path == "/api/stage2/connector-credentials/rotate":
                if not STATE.ids:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bootstrap required"})
                    return
                connector = str(body.get("connector") or "accela_api").strip().lower()
                ahj_id = body.get("ahj_id")
                credential_ref = str(body.get("credential_ref") or "").strip()
                if not credential_ref:
                    self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": "credential_ref is required"})
                    return
                vault = ConnectorCredentialVault(repository=STATE.stage2_repo, env=os.environ)
                record = vault.rotate_reference(
                    organization_id=STATE.ids.organization_id,
                    connector=connector,
                    ahj_id=None if ahj_id in {None, ""} else str(ahj_id),
                    credential_ref=credential_ref,
                    created_by=STATE.ids.owner_user_id,
                    scopes=body.get("scopes") if isinstance(body.get("scopes"), list) else [],
                    auth_scheme=str(body.get("auth_scheme") or "bearer"),
                    expires_at=(None if body.get("expires_at") in {None, ""} else str(body.get("expires_at"))),
                    rotation_due_at=(
                        None if body.get("rotation_due_at") in {None, ""} else str(body.get("rotation_due_at"))
                    ),
                )
                self._json(HTTPStatus.OK, {"credential": record})
                return

            if path == "/api/stage2/permit-bindings":
                if not STATE.ids:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bootstrap required"})
                    return
                connector = str(body.get("connector") or "accela_api").strip().lower()
                ahj_id = str(body.get("ahj_id") or "").strip().lower()
                permit_id = str(body.get("permit_id") or "").strip()
                external_permit_id = str(body.get("external_permit_id") or "").strip()
                if not ahj_id:
                    self._json(
                        HTTPStatus.UNPROCESSABLE_ENTITY,
                        {"error": {"code": "validation_error", "message": "ahj_id is required"}},
                    )
                    return
                if not permit_id:
                    self._json(
                        HTTPStatus.UNPROCESSABLE_ENTITY,
                        {"error": {"code": "validation_error", "message": "permit_id is required"}},
                    )
                    return
                if not external_permit_id:
                    self._json(
                        HTTPStatus.UNPROCESSABLE_ENTITY,
                        {"error": {"code": "validation_error", "message": "external_permit_id is required"}},
                    )
                    return
                if permit_id not in STATE.stage0_store.permits_by_id:
                    self._json(
                        HTTPStatus.NOT_FOUND,
                        {"error": {"code": "not_found", "message": "internal permit not found"}},
                    )
                    return
                binding = STATE.stage2_repo.upsert_external_permit_binding(
                    organization_id=STATE.ids.organization_id,
                    connector=connector,
                    ahj_id=ahj_id,
                    permit_id=permit_id,
                    external_permit_id=external_permit_id,
                    external_record_ref=(
                        None if body.get("external_record_ref") in {None, ""} else str(body.get("external_record_ref"))
                    ),
                    metadata_json=body.get("metadata") if isinstance(body.get("metadata"), dict) else {},
                    created_by=STATE.ids.owner_user_id,
                )
                self._json(HTTPStatus.OK, {"binding": binding})
                return

            if path == "/api/stage2/intake-complete":
                if not STATE.ids:
                    STATE.bootstrap()
                assert STATE.ids is not None

                permit_type = str(body.get("permit_type") or "commercial_ti")
                address = {
                    "line1": str(body.get("line1") or "200 Market St"),
                    "city": str(body.get("city") or "San Jose"),
                    "state": str(body.get("state") or "CA"),
                    "postal_code": str(body.get("postal_code") or "95113"),
                }
                ahj_hint = None
                try:
                    ahj_hint = STATE._resolve_ahj_with_shovels(address=address)
                except AhjIntelligenceError as exc:
                    ahj_hint = {"error": {"code": exc.code, "message": exc.message}}
                now = datetime.now(timezone.utc)
                status_session, session = create_intake_session_persisted(
                    project_id=STATE.ids.project_id,
                    permit_type=permit_type,
                    ahj_id=str(body.get("ahj_id") or (ahj_hint or {}).get("ahj_id") or "ca.san_jose.building"),
                    seed_answers={},
                    idempotency_key=f"intake-{uuid.uuid4()}",
                    trace_id=str(uuid.uuid4()),
                    auth_context=STATE._stage2_intake_auth(),
                    repository=STATE.stage2_repo,
                    now=now,
                )
                if status_session not in {200, 201}:
                    self._json(HTTPStatus(status_session), session)
                    return

                answers_patch = {
                    "project_name": "Battery + Solar Retrofit",
                    "project_address_line1": "200 Market St",
                    "city": "San Jose",
                    "state": "CA",
                    "postal_code": "95113",
                    "scope_summary": "Electrical service upgrade and rooftop solar retrofit.",
                    "valuation_usd": 250000,
                    "owner_legal_name": "Atlasly Holdings LLC",
                    "applicant_email": "pm@atlasly.dev",
                    "contractor_company_name": "Atlasly Electric",
                    "building_area_sqft": 18000,
                    "sprinklered_flag": True,
                    "solar_kw_dc": 250,
                    "solar_inverter_count": 8,
                    "contractor_license_number": "C10-445566",
                    "electrical_panel_amps_existing": 400,
                    "electrical_panel_amps_proposed": 800,
                }

                required_fields = set(BASE_REQUIRED_FIELDS) | set(PERMIT_SPECIFIC_REQUIRED_FIELDS[permit_type])

                status_update, updated = update_intake_session_persisted(
                    session_id=session["session_id"],
                    if_match_version=int(session["version"]),
                    payload={"answers_patch": answers_patch, "status": "completed"},
                    trace_id=str(uuid.uuid4()),
                    auth_context=STATE._stage2_intake_auth(),
                    repository=STATE.stage2_repo,
                    now=now,
                )
                if status_update != 200:
                    self._json(HTTPStatus(status_update), updated)
                    return

                status_app, app_payload = generate_permit_application_persisted(
                    permit_id=STATE.ids.permit_id,
                    intake_session_id=session["session_id"],
                    form_template_id="sj-building-form-v1",
                    mapping_version=1,
                    required_mapped_fields=required_fields,
                    idempotency_key=f"app-{uuid.uuid4()}",
                    trace_id=str(uuid.uuid4()),
                    auth_context=STATE._stage2_intake_auth(),
                    repository=STATE.stage2_repo,
                    now=now,
                )

                self._json(
                    HTTPStatus(status_app),
                    {
                        "session": updated,
                        "application": app_payload,
                        "ahj_intelligence": ahj_hint,
                    },
                )
                return

            if path == "/api/stage2/poll-status":
                if not STATE.ids:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bootstrap required"})
                    return

                raw_status = str(body.get("raw_status") or "Under review")
                observed_at = datetime.now(timezone.utc)
                projection = STATE.stage2_repo.get_status_projection(STATE.ids.permit_id)
                old_status = projection["current_status"] if projection else None

                def _client_callable(*, ahj_id: str) -> list[ConnectorObservation]:
                    return [
                        ConnectorObservation(
                            permit_id=STATE.ids.permit_id,
                            raw_status=raw_status,
                            source="accela_api",
                            observed_at=observed_at,
                            parser_version="v1",
                            source_ref=f"accela:{ahj_id}",
                            old_status=old_status,
                        )
                    ]

                adapter = AccelaApiAdapter(client_callable=_client_callable)
                result = run_connector_poll_with_retries(
                    ahj_id="ca.san_jose.building",
                    idempotency_key=f"poll-{uuid.uuid4()}",
                    trace_id=str(uuid.uuid4()),
                    auth_context=STATE._stage2_sync_auth(),
                    adapter=adapter,
                    repository=STATE.stage2_repo,
                    rules=None,
                    max_attempts=2,
                )

                timeline_status, timeline = get_status_timeline_persisted(
                    permit_id=STATE.ids.permit_id,
                    query_params={"limit": 50},
                    auth_context=STATE._stage2_sync_auth(),
                    repository=STATE.stage2_repo,
                )

                self._json(
                    HTTPStatus.OK,
                    {
                        "poll_result": result,
                        "timeline_status": timeline_status,
                        "timeline": timeline,
                    },
                )
                return

            if path == "/api/stage2/poll-live":
                if not STATE.ids:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bootstrap required"})
                    return
                connector = str(body.get("connector") or "accela_api").strip().lower()
                ahj_id = str(body.get("ahj_id") or "ca.san_jose.building").strip().lower()
                live_credential_ref = str(body.get("credential_ref") or "").strip()
                try:
                    adapter = build_live_connector_adapter(
                        organization_id=STATE.ids.organization_id,
                        connector=connector,
                        ahj_id=ahj_id,
                        repository=STATE.stage2_repo,
                        env=os.environ,
                    )
                except Exception as exc:  # noqa: BLE001
                    if isinstance(exc, ConnectorPollError):
                        status = HTTPStatus.SERVICE_UNAVAILABLE if exc.retryable else HTTPStatus.UNPROCESSABLE_ENTITY
                        self._json(status, {"error": str(exc), "retryable": exc.retryable})
                        return
                    raise

                result = run_connector_poll_with_retries(
                    ahj_id=ahj_id,
                    idempotency_key=f"poll-live-{uuid.uuid4()}",
                    trace_id=str(uuid.uuid4()),
                    auth_context=STATE._stage2_sync_auth(),
                    adapter=adapter,
                    repository=STATE.stage2_repo,
                    rules=None,
                    max_attempts=2,
                    permit_id_resolver=lambda obs: STATE.resolve_internal_permit_id(
                        connector=connector,
                        ahj_id=ahj_id,
                        external_permit_id=obs.permit_id,
                    ),
                )
                timeline_status, timeline = get_status_timeline_persisted(
                    permit_id=STATE.ids.permit_id,
                    query_params={"limit": 50},
                    auth_context=STATE._stage2_sync_auth(),
                    repository=STATE.stage2_repo,
                )
                operator_messages = list(result.get("errors") or [])
                unmapped = list(result.get("unmapped_observations") or [])
                if unmapped:
                    operator_messages.append(
                        f"{len(unmapped)} external permit records are unmapped; create Atlasly permit bindings before rerunning."
                    )
                if live_credential_ref:
                    operator_messages.append(
                        f"validated connector credential ref: {live_credential_ref}"
                    )
                self._json(
                    HTTPStatus.OK,
                    {
                        "poll_result": result,
                        "timeline_status": timeline_status,
                        "timeline": timeline,
                        "operator_messages": operator_messages,
                    },
                )
                return

            if path == "/api/permit-ops/resolve-transition":
                if not STATE.ids:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bootstrap required"})
                    return
                review_id = str(body.get("review_id") or "").strip()
                resolution_state = str(body.get("resolution_state") or "resolved").strip().lower()
                if not review_id:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "review_id is required"})
                    return
                if resolution_state not in {"open", "resolved", "dismissed"}:
                    self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": "invalid resolution_state"})
                    return
                try:
                    updated = STATE.stage2_repo.update_transition_review_resolution(
                        organization_id=STATE.ids.organization_id,
                        review_id=review_id,
                        resolution_state=resolution_state,
                    )
                except KeyError:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "transition review not found"})
                    return
                self._json(HTTPStatus.OK, {"review": updated, "permit_ops": STATE.permit_ops()})
                return

            if path == "/api/permit-ops/resolve-drift":
                if not STATE.ids:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bootstrap required"})
                    return
                alert_id = str(body.get("alert_id") or "").strip()
                status_value = str(body.get("status") or "resolved").strip().lower()
                if not alert_id:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "alert_id is required"})
                    return
                if status_value not in {"open", "resolved", "dismissed"}:
                    self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": "invalid status"})
                    return
                try:
                    updated = STATE.stage2_repo.update_drift_alert_status(
                        organization_id=STATE.ids.organization_id,
                        alert_id=alert_id,
                        status=status_value,
                    )
                except KeyError:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "drift alert not found"})
                    return
                self._json(HTTPStatus.OK, {"alert": updated, "permit_ops": STATE.permit_ops()})
                return

            if path == "/api/stage3/preflight":
                if not STATE.ids:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bootstrap required"})
                    return

                status, payload = STATE.stage3_api.get_project_preflight_risk(
                    project_id=STATE.ids.project_id,
                    query_params={
                        "permit_type": "commercial_ti",
                        "ahj_id": "ca.san_jose.building",
                        "include_recommendations": True,
                        "include_explainability": True,
                    },
                    headers={"X-Trace-Id": str(uuid.uuid4())},
                    auth_context=STATE._stage3_auth(),
                )
                self._json(HTTPStatus(status), payload)
                return

            if path == "/api/stage3/payout":
                if not STATE.ids:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "bootstrap required"})
                    return

                amount = float(body.get("amount") or 1200.0)
                provider = str(body.get("provider") or "provider_sandbox").strip().lower()
                if provider not in {
                    "provider_sandbox",
                    "demo_sandbox",
                    "stripe",
                    "stripe_connect",
                    "stripe_sandbox",
                    "stripe_connect_sandbox",
                }:
                    self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": "unsupported provider"})
                    return
                status, payload = STATE.stage3_api.post_milestone_financial_actions(
                    milestone_id=STATE.ids.milestone_id,
                    request_body={
                        "amount": amount,
                        "currency": str(body.get("currency") or "USD").strip().upper(),
                        "beneficiary_id": str(body.get("beneficiary_id") or "beneficiary-demo").strip(),
                        "provider": provider,
                        "step_up_authenticated": bool(body.get("step_up_authenticated", True)),
                    },
                    headers={
                        "Idempotency-Key": f"payout-{uuid.uuid4()}",
                        "X-Trace-Id": str(uuid.uuid4()),
                    },
                    auth_context=STATE._stage3_auth(),
                )
                if status in {200, 201}:
                    STATE.last_instruction_id = payload.get("instruction_id")
                self._json(HTTPStatus(status), payload)
                return

            if path == "/api/stage3/provider-event":
                if not STATE.ids or not STATE.last_instruction_id:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "create payout instruction first"})
                    return

                event_type = str(body.get("provider_event_type") or "instruction.submitted")
                instruction = STATE.stage3_store.repository.get_payout_instruction(
                    organization_id=STATE.ids.organization_id,
                    instruction_id=STATE.last_instruction_id,
                )
                amount = float(body.get("amount") or (instruction["amount"] if instruction else 0))
                currency = str(body.get("currency") or (instruction["currency"] if instruction else "USD"))

                status, payload = STATE.stage3_api.post_provider_webhook(
                    request_body={
                        "instruction_id": STATE.last_instruction_id,
                        "provider_event_type": event_type,
                        "provider_reference": f"evt-{uuid.uuid4().hex[:8]}",
                        "amount": amount,
                        "currency": currency,
                    },
                    headers={"X-Trace-Id": str(uuid.uuid4())},
                    auth_context=STATE._stage3_auth(),
                )
                self._json(HTTPStatus(status), payload)
                return

            if path == "/api/stage3/reconcile":
                if not STATE.ids or not STATE.last_instruction_id:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "create payout instruction first"})
                    return

                instruction = STATE.stage3_store.repository.get_payout_instruction(
                    organization_id=STATE.ids.organization_id,
                    instruction_id=STATE.last_instruction_id,
                )
                if not instruction:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "instruction not found"})
                    return

                status, payload = STATE.stage3_api.post_financial_reconciliation_runs(
                    request_body={
                        "provider": "provider_sandbox",
                        "settlements": [
                            {
                                "instruction_id": STATE.last_instruction_id,
                                "amount": instruction["amount"],
                                "currency": instruction["currency"],
                                "provider_reference": f"settle-{uuid.uuid4().hex[:8]}",
                            }
                        ],
                    },
                    headers={"X-Trace-Id": str(uuid.uuid4())},
                    auth_context=STATE._stage3_auth(),
                )
                self._json(HTTPStatus(status), payload)
                return

            if path == "/api/stage3/publish-outbox":
                max_events = int(body.get("max_events") or 100)
                max_events = max(1, min(500, max_events))
                payload = STATE.stage3_api.run_outbox_publisher(max_events=max_events)
                self._json(HTTPStatus.OK, payload)
                return

            self._json(HTTPStatus.NOT_FOUND, {"error": "route not found"})
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, SessionAuthError):
                self._json(HTTPStatus(exc.status), {"error": {"code": exc.code, "message": exc.message}})
                return
            if isinstance(exc, Stage1ARequestError):
                self._json(HTTPStatus(exc.status), {"error": {"code": exc.code, "message": exc.message}})
                return
            if isinstance(exc, AhjIntelligenceError):
                self._json(HTTPStatus(exc.status), {"error": {"code": exc.code, "message": exc.message}})
                return
            if isinstance(exc, ConnectorCredentialError):
                self._json(HTTPStatus(exc.status), {"error": {"code": exc.code, "message": exc.message}})
                return
            if isinstance(exc, EnterpriseReadinessError):
                self._json(HTTPStatus(exc.status), {"error": {"code": exc.code, "message": exc.message}})
                return
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    def do_PATCH(self) -> None:
        self._json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "PATCH not supported in demo"})

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        # Keep console clean for local runs.
        return

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _json(self, status: HTTPStatus, payload: dict) -> None:
        if self.command != "GET":
            try:
                STATE.persist_if_configured()
            except Exception:  # noqa: BLE001
                pass
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, path: str) -> None:
        safe_path = path.strip() or "/"
        if safe_path == "/":
            rel = pathlib.Path("index.html")
        else:
            rel = pathlib.Path(safe_path.lstrip("/"))

        target = (STATIC_DIR / rel).resolve()
        # Security check: must be inside STATIC_DIR
        if not str(target).startswith(str(STATIC_DIR.resolve())):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        # SPA fallback: serve index.html for any path that doesn't exist as a file
        if not target.exists() or target.is_dir():
            target = (STATIC_DIR / "index.html").resolve()
            if not target.exists():
                self.send_error(HTTPStatus.NOT_FOUND)
                return

        if target.suffix == ".html":
            ctype = "text/html; charset=utf-8"
        elif target.suffix == ".css":
            ctype = "text/css; charset=utf-8"
        elif target.suffix == ".js":
            ctype = "application/javascript; charset=utf-8"
        else:
            ctype = "application/octet-stream"

        content = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def run(host: str | None = None, port: int | None = None) -> None:
    bind_host = host or os.environ.get("ATLASLY_HOST", "127.0.0.1")
    bind_port = port or int(os.environ.get("ATLASLY_PORT", "8080"))
    server = HTTPServer((bind_host, bind_port), WebHandler)
    print(
        f"Atlasly webapp running at http://{bind_host}:{bind_port} "
        f"(tier={STATE.deployment_tier}, demo_routes_enabled={STATE.demo_routes_enabled})",
        flush=True,
    )
    warnings = STATE._placeholder_env_warnings()
    if warnings and STATE._has_prod_like_tier():
        print(f"Runtime warnings: {', '.join(warnings)}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    run()
