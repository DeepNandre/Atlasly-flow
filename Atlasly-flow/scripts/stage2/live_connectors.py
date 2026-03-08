from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import os
from typing import Any
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request
from urllib.request import urlopen

from scripts.stage2.connector_credentials import ConnectorCredentialError
from scripts.stage2.connector_credentials import ConnectorCredentialVault
from scripts.stage2.connector_runtime import BaseConnectorAdapter
from scripts.stage2.connector_runtime import ConnectorObservation
from scripts.stage2.connector_runtime import ConnectorPollError


def _iso_to_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    value = raw.strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        try:
            return parsedate_to_datetime(value).astimezone(timezone.utc)
        except Exception:  # noqa: BLE001
            return None


def _payload_hash(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _http_get_json(*, url: str, headers: dict[str, str], timeout_seconds: int = 20) -> dict[str, Any]:
    request = Request(url=url, method="GET", headers=headers)
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
        body = response.read()
    if not body:
        return {}
    return json.loads(body.decode("utf-8"))


def _http_error_to_poll_error(exc: Exception) -> ConnectorPollError:
    if isinstance(exc, HTTPError):
        retryable = int(exc.code) >= 500 or int(exc.code) in {408, 429}
        return ConnectorPollError(f"connector HTTP error {exc.code}", retryable=retryable)
    if isinstance(exc, URLError):
        return ConnectorPollError(f"connector network error: {exc.reason}", retryable=True)
    return ConnectorPollError(f"connector failure: {exc}", retryable=True)


class AccelaLiveAdapter(BaseConnectorAdapter):
    connector_name = "accela_api"

    def __init__(self, *, base_url: str, headers: dict[str, str], module_name: str = "Building"):
        self._base_url = base_url.rstrip("/")
        self._headers = dict(headers)
        self._module_name = module_name

    @staticmethod
    def _extract_status(row: dict[str, Any]) -> str | None:
        status = row.get("status")
        if isinstance(status, dict):
            value = status.get("value") or status.get("text") or status.get("status")
            return None if value is None else str(value).strip()
        if status is None:
            return None
        return str(status).strip()

    @staticmethod
    def _extract_permit_id(row: dict[str, Any]) -> str | None:
        for key in ("id", "recordId", "record_id", "customId", "altId"):
            value = row.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return None

    @staticmethod
    def _extract_observed_at(row: dict[str, Any]) -> datetime:
        for key in ("lastModifiedDate", "statusDate", "updatedDate", "createdDate"):
            dt = _iso_to_dt(str(row.get(key) or ""))
            if dt:
                return dt
        return datetime.now(timezone.utc)

    def poll(self, *, ahj_id: str) -> list[ConnectorObservation]:
        query = urlencode({"module": self._module_name, "limit": 100, "lang": "en-US"})
        url = f"{self._base_url}/v4/records?{query}"
        try:
            payload = _http_get_json(url=url, headers=self._headers)
        except Exception as exc:  # noqa: BLE001
            raise _http_error_to_poll_error(exc) from exc

        rows = payload.get("result") or payload.get("records") or payload.get("items") or []
        if not isinstance(rows, list):
            raise ConnectorPollError("accela payload shape invalid", retryable=False)

        observations: list[ConnectorObservation] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            permit_id = self._extract_permit_id(row)
            raw_status = self._extract_status(row)
            if not permit_id or not raw_status:
                continue
            observations.append(
                ConnectorObservation(
                    permit_id=permit_id,
                    raw_status=raw_status,
                    source="accela_api",
                    observed_at=self._extract_observed_at(row),
                    parser_version="accela-live-v1",
                    source_ref=f"accela:{ahj_id}:{permit_id}",
                    source_payload_hash=_payload_hash(row),
                    old_status=None,
                )
            )
        return observations


class OpenGovLiveAdapter(BaseConnectorAdapter):
    connector_name = "opengov_api"

    def __init__(self, *, base_url: str, headers: dict[str, str], status_path: str):
        self._base_url = base_url.rstrip("/")
        self._headers = dict(headers)
        self._status_path = status_path if status_path.startswith("/") else f"/{status_path}"

    def poll(self, *, ahj_id: str) -> list[ConnectorObservation]:
        query = urlencode({"ahj_id": ahj_id, "limit": 100})
        url = f"{self._base_url}{self._status_path}?{query}"
        try:
            payload = _http_get_json(url=url, headers=self._headers)
        except Exception as exc:  # noqa: BLE001
            raise _http_error_to_poll_error(exc) from exc

        rows = payload.get("result") or payload.get("permits") or payload.get("items") or []
        if not isinstance(rows, list):
            raise ConnectorPollError("opengov payload shape invalid", retryable=False)

        observations: list[ConnectorObservation] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            permit_id = str(row.get("permit_id") or row.get("id") or "").strip()
            raw_status = str(row.get("status") or row.get("raw_status") or "").strip()
            if not permit_id or not raw_status:
                continue
            observed_at = _iso_to_dt(str(row.get("updated_at") or row.get("observed_at") or "")) or datetime.now(
                timezone.utc
            )
            observations.append(
                ConnectorObservation(
                    permit_id=permit_id,
                    raw_status=raw_status,
                    source="opengov_api",
                    observed_at=observed_at,
                    parser_version="opengov-live-v1",
                    source_ref=f"opengov:{ahj_id}:{permit_id}",
                    source_payload_hash=_payload_hash(row),
                    old_status=None,
                )
            )
        return observations


def build_live_connector_adapter(
    *,
    organization_id: str,
    connector: str,
    ahj_id: str | None,
    repository: Any,
    env: dict[str, str] | None = None,
) -> BaseConnectorAdapter:
    env_map = env or os.environ
    vault = ConnectorCredentialVault(repository=repository, env=env_map)
    try:
        auth = vault.resolve_auth(organization_id=organization_id, connector=connector, ahj_id=ahj_id)
    except ConnectorCredentialError as exc:
        raise ConnectorPollError(f"{exc.code}: {exc.message}", retryable=False) from exc

    if connector == "accela_api":
        base_url = str(env_map.get("ATLASLY_ACCELA_BASE_URL") or "https://apis.accela.com").strip()
        headers = {"Accept": "application/json"}
        headers.update(auth.headers())
        app_id = str(env_map.get("ATLASLY_ACCELA_APP_ID") or "").strip()
        if app_id:
            headers["x-accela-appid"] = app_id
        return AccelaLiveAdapter(base_url=base_url, headers=headers)

    if connector == "opengov_api":
        base_url = str(env_map.get("ATLASLY_OPENGOV_BASE_URL") or "").strip()
        if not base_url:
            raise ConnectorPollError("opengov base url missing", retryable=False)
        status_path = str(env_map.get("ATLASLY_OPENGOV_STATUS_PATH") or "/permits/status").strip()
        headers = {"Accept": "application/json"}
        headers.update(auth.headers())
        return OpenGovLiveAdapter(base_url=base_url, headers=headers, status_path=status_path)

    raise ConnectorPollError("live connector unsupported", retryable=False)
