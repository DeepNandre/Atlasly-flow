from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib


@dataclass
class FeatureStoreData:
    offline_snapshots: dict[str, dict]

    @classmethod
    def empty(cls) -> "FeatureStoreData":
        return cls({})


class FeatureStore:
    def __init__(self, data: FeatureStoreData):
        self.data = data

    @staticmethod
    def _snapshot_key(*, project_id: str, permit_type: str, ahj_id: str, as_of: datetime) -> str:
        return f"{project_id}|{permit_type}|{ahj_id}|{as_of.astimezone(timezone.utc).isoformat()}"

    def compute_online_features(
        self,
        *,
        project_id: str,
        permit_type: str,
        ahj_id: str,
        as_of: datetime,
        project_profile: dict,
    ) -> tuple[dict, str]:
        seed = self._snapshot_key(
            project_id=project_id,
            permit_type=permit_type,
            ahj_id=ahj_id,
            as_of=as_of,
        )
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()

        completeness = float(project_profile.get("completeness_score", 0.75))
        complexity = float(project_profile.get("complexity_score", 0.5))
        ahj_variance = (int(digest[:4], 16) % 1000) / 1000.0

        features = {
            "submission_completeness": max(0.0, min(1.0, completeness)),
            "permit_complexity": max(0.0, min(1.0, complexity)),
            "ahj_cycle_variance": ahj_variance,
        }

        snapshot_ref = f"feat_{digest[:16]}"
        self.data.offline_snapshots[snapshot_ref] = {
            "project_id": project_id,
            "permit_type": permit_type,
            "ahj_id": ahj_id,
            "as_of": as_of.astimezone(timezone.utc).isoformat(),
            "features": features,
        }
        return features, snapshot_ref
