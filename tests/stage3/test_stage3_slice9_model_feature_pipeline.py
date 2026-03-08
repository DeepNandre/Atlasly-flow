from datetime import datetime, timezone
import unittest

from scripts.stage3.feature_store import FeatureStore
from scripts.stage3.feature_store import FeatureStoreData
from scripts.stage3.model_registry import ModelRegistry
from scripts.stage3.model_registry import ModelRegistryStore


class Stage3Slice9ModelFeaturePipelineTests(unittest.TestCase):
    def setUp(self):
        self.registry = ModelRegistry(ModelRegistryStore.empty())
        self.feature_store = FeatureStore(FeatureStoreData.empty())
        self.ts = datetime(2026, 3, 3, 21, 0, tzinfo=timezone.utc)

    def test_model_registry_lifecycle_and_rollback(self):
        m1 = self.registry.register_candidate(metrics={"a": 1.0}, feature_schema_hash="hash_v1")
        self.registry.set_state(model_version=m1["model_version"], new_state="validated")
        self.registry.set_state(model_version=m1["model_version"], new_state="approved")
        self.registry.deploy(model_version=m1["model_version"])

        m2 = self.registry.register_candidate(metrics={"a": 2.0}, feature_schema_hash="hash_v2")
        self.registry.set_state(model_version=m2["model_version"], new_state="validated")
        self.registry.set_state(model_version=m2["model_version"], new_state="approved")
        self.registry.deploy(model_version=m2["model_version"])

        deployed_before = self.registry.get_deployed_model()
        self.assertEqual(deployed_before["model_version"], m2["model_version"])

        rolled_back = self.registry.rollback()
        self.assertEqual(rolled_back["model_version"], m1["model_version"])

    def test_feature_store_online_compute_and_snapshot(self):
        features, snapshot_ref = self.feature_store.compute_online_features(
            project_id="7a6dc13a-34a6-4fce-9f01-8d97f36d3d35",
            permit_type="commercial_ti",
            ahj_id="ca.san_jose.building",
            as_of=self.ts,
            project_profile={"completeness_score": 0.8, "complexity_score": 0.6},
        )
        self.assertIn("submission_completeness", features)
        self.assertIn("permit_complexity", features)
        self.assertIn("ahj_cycle_variance", features)
        self.assertTrue(snapshot_ref.startswith("feat_"))
        self.assertIn(snapshot_ref, self.feature_store.data.offline_snapshots)


if __name__ == "__main__":
    unittest.main()
