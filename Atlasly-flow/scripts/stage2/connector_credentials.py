from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any


CONNECTOR_NAMES = {"accela_api", "opengov_api", "cloudpermit_portal_runner"}
ALLOWED_AUTH_SCHEMES = {"bearer", "api_key_header"}


class ConnectorCredentialError(ValueError):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_env_fragment(value: str) -> str:
    return re.sub(r"[^A-Z0-9_]", "_", value.upper())


def default_secret_env_var(credential_ref: str) -> str:
    return f"ATLASLY_CONNECTOR_SECRET_{_sanitize_env_fragment(credential_ref)}"


@dataclass(frozen=True)
class ConnectorAuthMaterial:
    connector: str
    credential_ref: str
    auth_scheme: str
    token_or_secret: str
    metadata: dict[str, Any]

    def headers(self) -> dict[str, str]:
        if self.auth_scheme == "bearer":
            return {"Authorization": f"Bearer {self.token_or_secret}"}
        if self.auth_scheme == "api_key_header":
            header_name = str(self.metadata.get("api_key_header_name") or "x-api-key")
            return {header_name: self.token_or_secret}
        return {}


class ConnectorCredentialVault:
    def __init__(self, *, repository: Any, env: dict[str, str]):
        self._repository = repository
        self._env = env

    def rotate_reference(
        self,
        *,
        organization_id: str,
        connector: str,
        ahj_id: str | None,
        credential_ref: str,
        created_by: str | None,
        scopes: list[str] | None = None,
        auth_scheme: str = "bearer",
        expires_at: str | None = None,
        rotation_due_at: str | None = None,
    ) -> dict:
        normalized_connector = connector.strip().lower()
        if normalized_connector not in CONNECTOR_NAMES:
            raise ConnectorCredentialError(422, "validation_error", "unsupported connector")
        if not credential_ref.strip():
            raise ConnectorCredentialError(422, "validation_error", "credential_ref is required")
        scheme = auth_scheme.strip().lower()
        if scheme not in ALLOWED_AUTH_SCHEMES:
            raise ConnectorCredentialError(422, "validation_error", "unsupported auth_scheme")

        record = self._repository.upsert_connector_credential(
            organization_id=organization_id,
            connector=normalized_connector,
            ahj_id=ahj_id,
            credential={
                "credential_ref": credential_ref.strip(),
                "scopes_json": list(scopes or []),
                "status": "active",
                "created_by": created_by,
                "last_validated_at": None,
                "expires_at": expires_at,
                "rotation_due_at": rotation_due_at,
                "auth_scheme": scheme,
                "updated_at": _utc_iso(),
            },
        )
        return record

    def resolve_auth(
        self,
        *,
        organization_id: str,
        connector: str,
        ahj_id: str | None,
    ) -> ConnectorAuthMaterial:
        normalized_connector = connector.strip().lower()
        if normalized_connector not in CONNECTOR_NAMES:
            raise ConnectorCredentialError(422, "validation_error", "unsupported connector")

        row = self._repository.get_connector_credential(
            organization_id=organization_id,
            connector=normalized_connector,
            ahj_id=ahj_id,
        )
        if not row:
            raise ConnectorCredentialError(404, "not_found", "connector credential not configured")
        if str(row.get("status") or "").lower() != "active":
            raise ConnectorCredentialError(409, "invalid_state", "connector credential is not active")

        credential_ref = str(row.get("credential_ref") or "").strip()
        if not credential_ref:
            raise ConnectorCredentialError(500, "credential_invalid", "connector credential_ref missing")
        secret_env = default_secret_env_var(credential_ref)
        secret = self._env.get(secret_env, "").strip()
        if not secret:
            raise ConnectorCredentialError(
                503,
                "secret_unavailable",
                f"missing connector secret env var {secret_env}",
            )

        scheme = str(row.get("auth_scheme") or "bearer").strip().lower()
        if scheme not in ALLOWED_AUTH_SCHEMES:
            scheme = "bearer"
        return ConnectorAuthMaterial(
            connector=normalized_connector,
            credential_ref=credential_ref,
            auth_scheme=scheme,
            token_or_secret=secret,
            metadata={"credential_id": row.get("id"), "ahj_id": row.get("ahj_id")},
        )
