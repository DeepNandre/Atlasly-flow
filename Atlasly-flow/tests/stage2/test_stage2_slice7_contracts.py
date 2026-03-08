import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class Stage2Slice7ContractTests(unittest.TestCase):
    def test_stage2_slice7_generation_runs_migration(self):
        migration_path = (
            ROOT / "db/migrations/000029_stage2_application_generation_runs.sql"
        )
        self.assertTrue(migration_path.exists(), f"missing {migration_path}")
        migration = migration_path.read_text()
        lower = migration.lower()
        self.assertIn("create table if not exists permit_application_generation_runs", lower)
        self.assertIn("unique (organization_id, idempotency_key)", migration)
        self.assertIn("idx_permit_app_generation_runs_permit_created", migration)

    def test_stage2_slice7_generation_runs_rollback(self):
        rollback_path = (
            ROOT
            / "db/migrations/rollback/000029_stage2_application_generation_runs_rollback.sql"
        )
        self.assertTrue(rollback_path.exists(), f"missing {rollback_path}")
        rollback = rollback_path.read_text().lower()
        self.assertIn("drop table if exists permit_application_generation_runs", rollback)


if __name__ == "__main__":
    unittest.main()
