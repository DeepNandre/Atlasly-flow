from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request
from urllib.request import urlopen


class AhjIntelligenceError(ValueError):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def _http_get_json(*, url: str, headers: dict[str, str], timeout_seconds: int = 20) -> dict[str, Any]:
    request = Request(url=url, method="GET", headers=headers)
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
        body = response.read()
    if not body:
        return {}
    return json.loads(body.decode("utf-8"))


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AddressInput:
    line1: str
    city: str
    state: str
    postal_code: str


class ShovelsClient:
    def __init__(self, *, api_key: str, base_url: str = "https://api.shovels.ai"):
        self._api_key = api_key.strip()
        self._base_url = base_url.rstrip("/")
        if not self._api_key:
            raise AhjIntelligenceError(422, "validation_error", "shovels api key is required")

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }

    def _search_addresses(self, *, address: AddressInput) -> list[dict[str, Any]]:
        query = f"{address.line1}, {address.city}, {address.state} {address.postal_code}"
        params = urlencode({"q": query, "limit": 3})
        url = f"{self._base_url}/v2/addresses/search?{params}"
        try:
            payload = _http_get_json(url=url, headers=self._headers())
        except HTTPError as exc:
            retryable = int(exc.code) >= 500
            code = "upstream_error" if retryable else "upstream_rejected"
            raise AhjIntelligenceError(503 if retryable else 424, code, f"shovels address search failed ({exc.code})") from exc
        except URLError as exc:
            raise AhjIntelligenceError(503, "network_error", f"shovels network error: {exc.reason}") from exc

        results = payload.get("results") or payload.get("items") or []
        if not isinstance(results, list):
            return []
        return [row for row in results if isinstance(row, dict)]

    def _search_permits(self, *, geo_id: str, limit: int = 50) -> list[dict[str, Any]]:
        params = urlencode({"geo_id": geo_id, "limit": max(1, min(200, int(limit)))})
        url = f"{self._base_url}/v2/permits/search?{params}"
        try:
            payload = _http_get_json(url=url, headers=self._headers())
        except Exception:
            return []
        rows = payload.get("results") or payload.get("items") or []
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)]

    def resolve_ahj(self, *, address: AddressInput) -> dict[str, Any]:
        candidates = self._search_addresses(address=address)
        if not candidates:
            raise AhjIntelligenceError(404, "not_found", "no shovels address match")

        top = candidates[0]
        geo_id = str(top.get("geo_id") or top.get("id") or "").strip()
        permits = self._search_permits(geo_id=geo_id) if geo_id else []

        jurisdictions: Counter[str] = Counter()
        status_counter: Counter[str] = Counter()
        for permit in permits:
            jurisdiction = str(permit.get("jurisdiction") or permit.get("ahj_name") or "").strip()
            if jurisdiction:
                jurisdictions[jurisdiction] += 1
            status = str(permit.get("status") or permit.get("permit_status") or "").strip().lower()
            if status:
                status_counter[status] += 1

        top_jurisdiction = jurisdictions.most_common(1)[0][0] if jurisdictions else None
        top_status = status_counter.most_common(1)[0][0] if status_counter else None
        inferred_ahj_id = (
            str(top.get("ahj_id") or "").strip()
            or str(top.get("jurisdiction_id") or "").strip()
            or (
                None
                if not top_jurisdiction
                else top_jurisdiction.lower().replace(" ", "_").replace(",", "").replace("/", "_")
            )
        )

        return {
            "resolved_at": _iso_now(),
            "geo_id": geo_id or None,
            "address_candidate": top,
            "ahj_id": inferred_ahj_id,
            "jurisdiction_name": top_jurisdiction,
            "sample_permit_count": len(permits),
            "sample_top_status": top_status,
        }
