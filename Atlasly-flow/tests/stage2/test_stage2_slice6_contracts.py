import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class Stage2Slice6ContractTests(unittest.TestCase):
    def test_stage2_slice6_projection_migration_exists_and_has_constraints(self):
        migration_path = ROOT / "db/migrations/000028_stage2_status_projection_cache.sql"
        self.assertTrue(migration_path.exists(), f"missing {migration_path}")
        migration = migration_path.read_text()
        lower = migration.lower()

        self.assertIn("create table if not exists permit_status_projections", lower)
        self.assertIn("current_status in ('submitted', 'in_review', 'corrections_required', 'approved', 'issued', 'expired')", migration)
        self.assertIn("idx_permit_status_projections_org_status_updated", migration)

    def test_stage2_slice6_projection_rollback_exists(self):
        rollback_path = (
            ROOT / "db/migrations/rollback/000028_stage2_status_projection_cache_rollback.sql"
        )
        self.assertTrue(rollback_path.exists(), f"missing {rollback_path}")
        rollback = rollback_path.read_text().lower()
        self.assertIn("drop table if exists permit_status_projections", rollback)


if __name__ == "__main__":
    unittest.main()
