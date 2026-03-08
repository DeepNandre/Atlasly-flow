import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class Stage2Slice8And9ContractTests(unittest.TestCase):
    def test_slice8_connector_poll_attempts_migration_and_rollback(self):
        migration = ROOT / "db/migrations/000030_stage2_connector_poll_attempts.sql"
        rollback = (
            ROOT / "db/migrations/rollback/000030_stage2_connector_poll_attempts_rollback.sql"
        )
        self.assertTrue(migration.exists(), f"missing {migration}")
        self.assertTrue(rollback.exists(), f"missing {rollback}")
        body = migration.read_text()
        self.assertIn("create table if not exists connector_poll_attempts", body.lower())
        self.assertIn("uq_connector_poll_attempts_run_attempt", body)
        self.assertIn("idx_connector_poll_attempts_run_attempted", body)

    def test_slice9_stage2_outbox_migration_and_rollback(self):
        migration = ROOT / "db/migrations/000031_stage2_event_outbox.sql"
        rollback = ROOT / "db/migrations/rollback/000031_stage2_event_outbox_rollback.sql"
        self.assertTrue(migration.exists(), f"missing {migration}")
        self.assertTrue(rollback.exists(), f"missing {rollback}")
        body = migration.read_text()
        self.assertIn("create table if not exists stage2_event_outbox", body.lower())
        self.assertIn("unique (organization_id, idempotency_key, event_type)", body.lower())
        self.assertIn("idx_stage2_outbox_publish_state_created", body)


if __name__ == "__main__":
    unittest.main()
