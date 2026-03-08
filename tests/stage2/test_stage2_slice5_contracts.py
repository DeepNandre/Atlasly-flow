import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class Stage2Slice5ContractTests(unittest.TestCase):
    def test_stage2_slice5_migration_contains_required_tables_and_checks(self):
        migration_path = (
            ROOT / "db/migrations/000027_stage2_normalization_and_drift_rules.sql"
        )
        self.assertTrue(migration_path.exists(), f"missing {migration_path}")
        migration = migration_path.read_text()
        lower = migration.lower()

        self.assertIn("create table if not exists status_normalization_rules", lower)
        self.assertIn("create table if not exists status_drift_alerts", lower)
        self.assertIn("check (match_type in ('exact', 'regex', 'lexical'))", migration)
        self.assertIn(
            "check (normalized_status in ('submitted', 'in_review', 'corrections_required', 'approved', 'issued', 'expired'))",
            migration,
        )
        self.assertIn("check (drift_type in ('mapping_drift', 'source_drift', 'timeline_gap'))", migration)

    def test_stage2_slice5_rollback_exists(self):
        rollback_path = (
            ROOT
            / "db/migrations/rollback/000027_stage2_normalization_and_drift_rules_rollback.sql"
        )
        self.assertTrue(rollback_path.exists(), f"missing {rollback_path}")
        rollback = rollback_path.read_text().lower()
        self.assertIn("drop table if exists status_drift_alerts", rollback)
        self.assertIn("drop table if exists status_normalization_rules", rollback)


if __name__ == "__main__":
    unittest.main()
