from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
import sqlite3
import uuid

from scripts.stage3.feature_store import FeatureStore
from scripts.stage3.feature_store import FeatureStoreData
from scripts.stage3.finance_api import create_reconciliation_run_persisted
from scripts.stage3.finance_api import get_reconciliation_run_persisted
from scripts.stage3.finance_api import record_financial_event_persisted
from scripts.stage3.model_registry import ModelRegistry
from scripts.stage3.model_registry import ModelRegistryStore
from scripts.stage3.outbox_dispatcher import dispatch_pending_outbox_events
from scripts.stage3.payout_api import AuthContext
from scripts.stage3.payout_api import PayoutRequestError
from scripts.stage3.payout_api import create_payout_instruction_persisted
from scripts.stage3.payout_api import transition_instruction_state_persisted
from scripts.stage3.preflight_api import PreflightRequestError
from scripts.stage3.preflight_api import parse_preflight_request
from scripts.stage3.provider_adapter import normalize_provider_status
from scripts.stage3.provider_adapter import normalize_settlement_row
from scripts.stage3.provider_adapter import verify_provider_signature
from scripts.stage3.provider_submission import submit_provider_instruction
from scripts.stage3.sqlite_repository import Stage3SQLiteRepository


READ_ROLES = {"owner", "admin", "pm"}
FINANCE_ROLES = {"owner", "admin"}


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat()


def _trace_id(headers: dict[str, str] | None) -> str:
    if headers and headers.get("X-Trace-Id", "").strip():
        return headers["X-Trace-Id"].strip()
    return str(uuid.uuid4())


def _idempotency_key(headers: dict[str, str] | None, fallback: str) -> str:
    if headers and headers.get("Idempotency-Key", "").strip():
        return headers["Idempotency-Key"].strip()
    return fallback


def _risk_band(score: float) -> str:
    if score < 0.25:
        return "low"
    if score < 0.5:
        return "medium"
    if score < 0.75:
        return "high"
    return "critical"


def _error_response(exc: Exception) -> tuple[int, dict]:
    if isinstance(exc, (PreflightRequestError, PayoutRequestError)):
        return exc.status, {"error": {"code": exc.code, "message": exc.message}}
    return 500, {"error": {"code": "internal_error", "message": str(exc)}}


@dataclass
class Stage3RuntimeStore:
    repository: Stage3SQLiteRepository
    feature_store: FeatureStore
    model_registry: ModelRegistry
    projects_by_id: dict[str, dict]
    milestones_by_id: dict[str, dict]

    @classmethod
    def bootstrap(cls) -> "Stage3RuntimeStore":
        repo = Stage3SQLiteRepository()
        feature_store = FeatureStore(FeatureStoreData.empty())
        registry = ModelRegistry(ModelRegistryStore.empty())
        model = registry.register_candidate(
            metrics={
                "w_ahj_cycle_variance": 0.45,
                "w_submission_incompleteness": 0.35,
                "w_permit_complexity": 0.20,
                "confidence_score": 0.82,
            },
            feature_schema_hash="stage3-feature-schema-v1",
        )
        registry.set_state(model_version=model["model_version"], new_state="validated")
        registry.set_state(model_version=model["model_version"], new_state="approved")
        registry.deploy(model_version=model["model_version"])
        return cls(repo, feature_store, registry, {}, {})


class Stage3RuntimeAPI:
    def __init__(self, store: Stage3RuntimeStore):
        self.store = store
        self.webhook_signature_secret = os.environ.get("ATLASLY_STAGE3_PROVIDER_WEBHOOK_SECRET", "").strip()
        self.enforce_webhook_signatures = (
            os.environ.get("ATLASLY_STAGE3_ENFORCE_SIGNATURES", "false").strip().lower() in {"1", "true", "yes", "on"}
        )

    def register_project(self, project: dict) -> None:
        self.store.projects_by_id[project["project_id"]] = dict(project)

    def register_milestone(self, milestone: dict) -> None:
        self.store.milestones_by_id[milestone["id"]] = dict(milestone)

    def _safe_insert_outbox_event(self, event: dict) -> None:
        # Avoid duplicate emission by (org, event_type, idempotency_key).
        existing = self.store.repository.list_outbox_events(publish_state=None, limit=10000)
        for row in existing:
            if (
                row["organization_id"] == event["organization_id"]
                and row["event_type"] == event["event_type"]
                and row["idempotency_key"] == event["idempotency_key"]
            ):
                return
        try:
            self.store.repository.insert_outbox_event(event)
        except sqlite3.IntegrityError:
            return

    def get_project_preflight_risk(
        self,
        *,
        project_id: str,
        query_params: dict[str, object],
        headers: dict[str, str] | None,
        auth_context: AuthContext,
        now: datetime | None = None,
    ) -> tuple[int, dict]:
        try:
            if auth_context.requester_role not in READ_ROLES:
                raise PayoutRequestError(403, "forbidden", "role cannot access preflight risk")

            project = self.store.projects_by_id.get(project_id)
            if not project:
                raise PreflightRequestError(404, "not_found", "project not found")
            if project["organization_id"] != auth_context.organization_id:
                raise PreflightRequestError(403, "forbidden", "project does not belong to caller organization")

            ts = now or datetime.now(timezone.utc)
            req = parse_preflight_request(
                project_id,
                query_params,
                server_now=ts,
                project_created_at=project["created_at"],
            )

            model = self.store.model_registry.get_deployed_model()
            features, feature_snapshot_ref = self.store.feature_store.compute_online_features(
                project_id=project_id,
                permit_type=req.permit_type,
                ahj_id=req.ahj_id,
                as_of=req.as_of,
                project_profile=project.get("profile", {}),
            )

            weights = model.get("metrics", {})
            risk_score = max(
                0.0,
                min(
                    1.0,
                    weights.get("w_ahj_cycle_variance", 0.45) * features["ahj_cycle_variance"]
                    + weights.get("w_submission_incompleteness", 0.35)
                    * (1.0 - features["submission_completeness"])
                    + weights.get("w_permit_complexity", 0.20) * features["permit_complexity"],
                ),
            )
            risk_band = _risk_band(risk_score)
            confidence_score = float(weights.get("confidence_score", 0.82))

            top_factors = [
                {
                    "factor_code": "ahj_cycle_variance",
                    "factor_label": "AHJ correction-cycle variance",
                    "contribution": round(features["ahj_cycle_variance"] * 0.45, 4),
                    "evidence_ref_ids": [f"{feature_snapshot_ref}:ahj_cycle_variance"],
                },
                {
                    "factor_code": "submission_completeness",
                    "factor_label": "Submission completeness",
                    "contribution": round((1 - features["submission_completeness"]) * 0.35, 4),
                    "evidence_ref_ids": [f"{feature_snapshot_ref}:submission_completeness"],
                },
                {
                    "factor_code": "permit_complexity",
                    "factor_label": "Permit complexity",
                    "contribution": round(features["permit_complexity"] * 0.20, 4),
                    "evidence_ref_ids": [f"{feature_snapshot_ref}:permit_complexity"],
                },
            ]

            response = {
                "project_id": project_id,
                "permit_type": req.permit_type,
                "ahj_id": req.ahj_id,
                "risk_score": round(risk_score, 4),
                "risk_band": risk_band,
                "confidence_score": round(confidence_score, 4),
                "model_version": model["model_version"],
                "scored_at": _iso(req.as_of),
            }

            if req.include_explainability:
                response["top_risk_factors"] = top_factors
            if req.include_recommendations:
                response["recommended_actions"] = [
                    {
                        "action_id": "act_preflight_review",
                        "action_text": "Run pre-submit completeness review for AHJ-specific requirements.",
                        "expected_impact": "Lower first-cycle corrections probability.",
                        "priority": "high",
                        "owner_role": "pm",
                    }
                ]

            self.store.repository.insert_preflight_score(
                {
                    "organization_id": auth_context.organization_id,
                    "project_id": project_id,
                    "permit_id": project.get("permit_id"),
                    "ahj_id": req.ahj_id,
                    "permit_type": req.permit_type,
                    "score": round(risk_score, 4),
                    "band": risk_band,
                    "confidence_score": round(confidence_score, 4),
                    "model_version": model["model_version"],
                    "scored_at": _iso(req.as_of),
                }
            )

            idem = f"preflight:{project_id}:{req.permit_type}:{req.ahj_id}:{_iso(req.as_of)}"
            trace_id = _trace_id(headers)

            preflight_event = {
                "event_id": str(uuid.uuid4()),
                "event_type": "permit.preflight_scored",
                "event_version": 1,
                "organization_id": auth_context.organization_id,
                "aggregate_type": "permit",
                "aggregate_id": str(project.get("permit_id") or project_id),
                "occurred_at": _iso(req.as_of),
                "produced_by": "intelligence-service",
                "idempotency_key": idem,
                "trace_id": trace_id,
                "payload": {
                    "project_id": project_id,
                    "permit_id": project.get("permit_id"),
                    "permit_type": req.permit_type,
                    "ahj_id": req.ahj_id,
                    "risk_score": round(risk_score, 4),
                    "risk_band": risk_band,
                    "confidence_score": round(confidence_score, 4),
                    "model_version": model["model_version"],
                    "calibration_version": "cal-v1",
                    "feature_snapshot_ref": feature_snapshot_ref,
                    "scored_at": _iso(req.as_of),
                },
            }
            self._safe_insert_outbox_event(preflight_event)

            if req.include_recommendations:
                rec_event = {
                    "event_id": str(uuid.uuid4()),
                    "event_type": "permit.recommendations_generated",
                    "event_version": 1,
                    "organization_id": auth_context.organization_id,
                    "aggregate_type": "permit",
                    "aggregate_id": str(project.get("permit_id") or project_id),
                    "occurred_at": _iso(req.as_of),
                    "produced_by": "intelligence-service",
                    "idempotency_key": f"{idem}:recommendations",
                    "trace_id": trace_id,
                    "payload": {
                        "project_id": project_id,
                        "permit_id": project.get("permit_id"),
                        "permit_type": req.permit_type,
                        "ahj_id": req.ahj_id,
                        "recommendations": response.get("recommended_actions", []),
                        "top_risk_factors": response.get("top_risk_factors", []),
                        "generated_at": _iso(req.as_of),
                        "source_score_event_id": preflight_event["event_id"],
                    },
                }
                self._safe_insert_outbox_event(rec_event)

            return 200, response
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    def post_project_preflight_recommendations(
        self,
        *,
        project_id: str,
        request_body: dict[str, object],
        headers: dict[str, str] | None,
        auth_context: AuthContext,
        now: datetime | None = None,
    ) -> tuple[int, dict]:
        query = {
            "permit_type": request_body.get("permit_type"),
            "ahj_id": request_body.get("ahj_id"),
            "as_of": request_body.get("as_of"),
            "include_recommendations": True,
            "include_explainability": True,
        }
        status, payload = self.get_project_preflight_risk(
            project_id=project_id,
            query_params=query,
            headers=headers,
            auth_context=auth_context,
            now=now,
        )
        if status != 200:
            return status, payload
        return 200, {
            "project_id": payload["project_id"],
            "permit_type": payload["permit_type"],
            "ahj_id": payload["ahj_id"],
            "recommended_actions": payload.get("recommended_actions", []),
            "top_risk_factors": payload.get("top_risk_factors", []),
            "generated_at": payload["scored_at"],
        }

    def post_milestone_financial_actions(
        self,
        *,
        milestone_id: str,
        request_body: dict[str, object],
        headers: dict[str, str] | None,
        auth_context: AuthContext,
        now: datetime | None = None,
    ) -> tuple[int, dict]:
        try:
            if auth_context.requester_role not in FINANCE_ROLES:
                raise PayoutRequestError(403, "forbidden", "role cannot initiate financial actions")

            milestone = self.store.milestones_by_id.get(milestone_id)
            if not milestone:
                raise PayoutRequestError(404, "not_found", "milestone not found")

            idem = _idempotency_key(headers, f"milestone:{milestone_id}:financial-actions")
            trace = _trace_id(headers)
            status, instruction = create_payout_instruction_persisted(
                milestone=milestone,
                amount=float(request_body.get("amount", 0)),
                currency=str(request_body.get("currency", "")),
                beneficiary_id=str(request_body.get("beneficiary_id", "")),
                provider=str(request_body.get("provider", "provider_sandbox")),
                idempotency_key=idem,
                trace_id=trace,
                step_up_authenticated=bool(request_body.get("step_up_authenticated", False)),
                auth_context=auth_context,
                repository=self.store.repository,
                now=now,
            )

            if status == 201:
                record_financial_event_persisted(
                    organization_id=auth_context.organization_id,
                    instruction_id=instruction["instruction_id"],
                    milestone_id=instruction["milestone_id"],
                    event_type="instruction_created",
                    amount=float(instruction["amount"]),
                    currency=str(instruction["currency"]),
                    trace_id=trace,
                    source_service="payout-service",
                    payload={"provider": instruction["provider"]},
                    occurred_at=now or datetime.now(timezone.utc),
                    repository=self.store.repository,
                )

                provider = str(instruction.get("provider") or "").strip().lower()
                if provider in {"stripe", "stripe_connect", "stripe_sandbox", "stripe_connect_sandbox"}:
                    submission = submit_provider_instruction(
                        instruction=instruction,
                        stripe_secret_key=os.environ.get("ATLASLY_STRIPE_SECRET_KEY"),
                        stripe_base_url=os.environ.get("ATLASLY_STRIPE_BASE_URL", "https://api.stripe.com"),
                    )
                    if submission.get("accepted"):
                        instruction = transition_instruction_state_persisted(
                            organization_id=auth_context.organization_id,
                            instruction_id=instruction["instruction_id"],
                            new_state="submitted",
                            repository=self.store.repository,
                            now=now,
                        )
                        record_financial_event_persisted(
                            organization_id=auth_context.organization_id,
                            instruction_id=instruction["instruction_id"],
                            milestone_id=instruction["milestone_id"],
                            event_type="instruction_submitted",
                            amount=float(instruction["amount"]),
                            currency=str(instruction["currency"]),
                            trace_id=trace,
                            source_service="provider-submit",
                            payload={
                                "provider": instruction["provider"],
                                "provider_reference": submission.get("provider_reference"),
                            },
                            occurred_at=now or datetime.now(timezone.utc),
                            repository=self.store.repository,
                        )
                        instruction["provider_reference"] = submission.get("provider_reference")

            return status, instruction
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    def post_provider_webhook(
        self,
        *,
        request_body: dict[str, object],
        headers: dict[str, str] | None,
        auth_context: AuthContext,
        now: datetime | None = None,
    ) -> tuple[int, dict]:
        try:
            if auth_context.requester_role not in FINANCE_ROLES:
                raise PayoutRequestError(403, "forbidden", "role cannot process provider webhook")

            verify_provider_signature(
                request_body=request_body,
                headers=headers,
                secret=self.webhook_signature_secret,
                required=self.enforce_webhook_signatures,
            )

            instruction_id = str(request_body.get("instruction_id", ""))
            provider_event_type = str(request_body.get("provider_event_type", ""))
            new_state = normalize_provider_status(provider_event_type=provider_event_type)

            updated = transition_instruction_state_persisted(
                organization_id=auth_context.organization_id,
                instruction_id=instruction_id,
                new_state=new_state,
                repository=self.store.repository,
                now=now,
            )

            event_type_map = {
                "submitted": "instruction_submitted",
                "settled": "provider_settled",
                "failed_transient": "provider_failed",
                "failed_terminal": "provider_failed",
                "reversed": "reversal_posted",
            }
            event_type = event_type_map[new_state]
            record_financial_event_persisted(
                organization_id=auth_context.organization_id,
                instruction_id=updated["instruction_id"],
                milestone_id=updated["milestone_id"],
                event_type=event_type,
                amount=float(request_body.get("amount", updated["amount"])),
                currency=str(request_body.get("currency", updated["currency"])),
                trace_id=_trace_id(headers),
                source_service="provider-webhook",
                payload={"provider_reference": request_body.get("provider_reference")},
                occurred_at=now or datetime.now(timezone.utc),
                repository=self.store.repository,
            )

            return 200, {
                "instruction_id": updated["instruction_id"],
                "instruction_state": updated["instruction_state"],
                "provider_reference": request_body.get("provider_reference"),
            }
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    def post_financial_reconciliation_runs(
        self,
        *,
        request_body: dict[str, object],
        headers: dict[str, str] | None,
        auth_context: AuthContext,
        now: datetime | None = None,
    ) -> tuple[int, dict]:
        try:
            if auth_context.requester_role not in FINANCE_ROLES:
                raise PayoutRequestError(403, "forbidden", "role cannot run reconciliation")
            provider = str(request_body.get("provider", ""))
            if not provider:
                raise PayoutRequestError(422, "validation_error", "provider is required")
            raw_rows = request_body.get("settlements", [])
            if not isinstance(raw_rows, list):
                raise PayoutRequestError(422, "validation_error", "settlements must be an array")
            settlements = [normalize_settlement_row(row) for row in raw_rows]
            run = create_reconciliation_run_persisted(
                organization_id=auth_context.organization_id,
                provider=provider,
                provider_settlements=settlements,
                repository=self.store.repository,
                run_started_at=now or datetime.now(timezone.utc),
            )
            return 201, run
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    def get_financial_reconciliation_run(
        self,
        *,
        run_id: str,
        auth_context: AuthContext,
    ) -> tuple[int, dict]:
        try:
            return get_reconciliation_run_persisted(
                run_id=run_id,
                organization_id=auth_context.organization_id,
                repository=self.store.repository,
            )
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    def run_outbox_publisher(self, *, max_events: int = 100) -> dict:
        return dispatch_pending_outbox_events(repository=self.store.repository, max_events=max_events)
