from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from typing import Callable

from scripts.stage2.repositories import Stage2Repository
from scripts.stage2.status_sync import AuthContext
from scripts.stage2.status_sync import record_status_observation_persisted
from scripts.stage2.sync_api import post_connector_poll_persisted


class ConnectorPollError(Exception):
    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class ConnectorObservation:
    permit_id: str
    raw_status: str
    source: str
    observed_at: datetime
    parser_version: str = "v1"
    source_ref: str | None = None
    source_payload_hash: str | None = None
    old_status: str | None = None


class BaseConnectorAdapter:
    connector_name: str

    def poll(self, *, ahj_id: str) -> list[ConnectorObservation]:
        raise NotImplementedError


class AccelaApiAdapter(BaseConnectorAdapter):
    connector_name = "accela_api"

    def __init__(self, client_callable):
        self._client = client_callable

    def poll(self, *, ahj_id: str) -> list[ConnectorObservation]:
        return self._client(ahj_id=ahj_id)


class OpenGovApiAdapter(BaseConnectorAdapter):
    connector_name = "opengov_api"

    def __init__(self, client_callable):
        self._client = client_callable

    def poll(self, *, ahj_id: str) -> list[ConnectorObservation]:
        return self._client(ahj_id=ahj_id)


class CloudpermitPortalRunnerAdapter(BaseConnectorAdapter):
    connector_name = "cloudpermit_portal_runner"

    def __init__(self, runner_callable):
        self._runner = runner_callable

    def poll(self, *, ahj_id: str) -> list[ConnectorObservation]:
        return self._runner(ahj_id=ahj_id)


def _event_hash(*, permit_id: str, raw_status: str, observed_at: datetime, source: str) -> str:
    seed = f"{permit_id}|{raw_status}|{source}|{observed_at.astimezone(timezone.utc).isoformat()}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def run_connector_poll_with_retries(
    *,
    ahj_id: str,
    idempotency_key: str,
    trace_id: str,
    auth_context: AuthContext,
    adapter: BaseConnectorAdapter,
    repository: Stage2Repository,
    rules: list[dict] | None = None,
    max_attempts: int = 3,
    now: datetime | None = None,
    permit_id_resolver: Callable[[ConnectorObservation], str | None] | None = None,
) -> dict:
    ts = now or datetime.now(timezone.utc)
    _, run = post_connector_poll_persisted(
        ahj=ahj_id,
        request_body={"connector": adapter.connector_name, "dry_run": False, "force": False},
        idempotency_key=idempotency_key,
        auth_context=auth_context,
        repository=repository,
        now=ts,
    )

    attempts = 0
    errors: list[str] = []
    observations_processed = 0
    observations_applied = 0
    observations_reviewed = 0
    unmapped_observations: list[dict] = []
    while attempts < max_attempts:
        attempts += 1
        try:
            observations = adapter.poll(ahj_id=ahj_id)
            if not observations:
                errors.append("no status observations returned for current connector query")
            for idx, obs in enumerate(observations):
                resolved_permit_id = permit_id_resolver(obs) if permit_id_resolver is not None else obs.permit_id
                if not resolved_permit_id:
                    unmapped_observations.append(
                        {
                            "external_permit_id": obs.permit_id,
                            "source": obs.source,
                            "raw_status": obs.raw_status,
                            "observed_at": obs.observed_at.astimezone(timezone.utc).isoformat(),
                            "source_ref": obs.source_ref,
                        }
                    )
                    continue
                event_hash = _event_hash(
                    permit_id=resolved_permit_id,
                    raw_status=obs.raw_status,
                    observed_at=obs.observed_at,
                    source=obs.source,
                )
                result = record_status_observation_persisted(
                    permit_id=resolved_permit_id,
                    source=obs.source,
                    raw_status=obs.raw_status,
                    old_status=obs.old_status,
                    organization_id=auth_context.organization_id,
                    connector=adapter.connector_name,
                    ahj_id=ahj_id,
                    observed_at=obs.observed_at,
                    parser_version=obs.parser_version,
                    event_hash=event_hash,
                    trace_id=trace_id,
                    idempotency_key=f"{idempotency_key}:obs:{idx}",
                    rules=rules,
                    provenance_source_type="api" if adapter.connector_name != "cloudpermit_portal_runner" else "portal",
                    provenance_source_ref=obs.source_ref,
                    source_payload_hash=obs.source_payload_hash,
                    repository=repository,
                )
                if result["status_event"]:
                    observations_processed += 1
                if result["applied"]:
                    observations_applied += 1
                if result["review"] is not None:
                    observations_reviewed += 1

            if unmapped_observations or not observations:
                run["status"] = "partial"
            else:
                run["status"] = "succeeded"
            run["run_finished_at"] = datetime.now(timezone.utc).isoformat()
            repository.save_poll_run(run)
            return {
                "run": run,
                "attempts": attempts,
                "observations_processed": observations_processed,
                "observations_applied": observations_applied,
                "observations_reviewed": observations_reviewed,
                "errors": errors,
                "unmapped_observations": unmapped_observations,
            }
        except ConnectorPollError as exc:
            errors.append(str(exc))
            if not exc.retryable:
                break

    run["status"] = "failed"
    run["run_finished_at"] = datetime.now(timezone.utc).isoformat()
    run["error_summary"] = {"attempts": attempts, "errors": errors}
    repository.save_poll_run(run)
    return {
        "run": run,
        "attempts": attempts,
        "observations_processed": observations_processed,
        "observations_applied": observations_applied,
        "observations_reviewed": observations_reviewed,
        "errors": errors,
        "unmapped_observations": unmapped_observations,
    }
