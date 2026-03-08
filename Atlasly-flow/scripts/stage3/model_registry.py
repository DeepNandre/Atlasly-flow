from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import uuid


ALLOWED_MODEL_STATES = {"draft", "validated", "approved", "deployed", "retired"}


@dataclass
class ModelRegistryStore:
    models_by_version: dict[str, dict]
    deployed_version: str | None
    deploy_history: list[str]

    @classmethod
    def empty(cls) -> "ModelRegistryStore":
        return cls({}, None, [])


class ModelRegistry:
    def __init__(self, store: ModelRegistryStore):
        self.store = store

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def register_candidate(self, *, metrics: dict[str, float], feature_schema_hash: str) -> dict:
        version = f"model-{uuid.uuid4()}"
        record = {
            "model_version": version,
            "state": "draft",
            "metrics": dict(metrics),
            "feature_schema_hash": feature_schema_hash,
            "created_at": self._now_iso(),
        }
        self.store.models_by_version[version] = record
        return record

    def set_state(self, *, model_version: str, new_state: str) -> dict:
        if new_state not in ALLOWED_MODEL_STATES:
            raise ValueError("invalid model state")
        record = self.store.models_by_version.get(model_version)
        if not record:
            raise KeyError("model version not found")
        record["state"] = new_state
        record["updated_at"] = self._now_iso()
        return record

    def deploy(self, *, model_version: str) -> dict:
        record = self.store.models_by_version.get(model_version)
        if not record:
            raise KeyError("model version not found")
        if record["state"] not in {"approved", "deployed"}:
            raise ValueError("model must be approved before deploy")

        if self.store.deployed_version and self.store.deployed_version != model_version:
            previous = self.store.models_by_version.get(self.store.deployed_version)
            if previous and previous["state"] == "deployed":
                previous["state"] = "approved"

        record["state"] = "deployed"
        record["deployed_at"] = self._now_iso()
        self.store.deployed_version = model_version
        self.store.deploy_history.append(model_version)
        return record

    def rollback(self) -> dict:
        if len(self.store.deploy_history) < 2:
            raise ValueError("no previous deployed model available for rollback")
        # Remove current from history and redeploy previous.
        self.store.deploy_history.pop()
        previous_version = self.store.deploy_history[-1]
        return self.deploy(model_version=previous_version)

    def get_deployed_model(self) -> dict:
        if not self.store.deployed_version:
            raise ValueError("no deployed model")
        record = self.store.models_by_version.get(self.store.deployed_version)
        if not record:
            raise ValueError("deployed model record missing")
        return record
