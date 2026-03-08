from __future__ import annotations

import pathlib
import sqlite3
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.db.migration_orchestrator import apply_sqlite_migrations
from scripts.db.migration_orchestrator import discover_migrations
from scripts.db.migration_orchestrator import migration_checksum_entries
from scripts.db.migration_orchestrator import verify_manifest
from scripts.db.migration_orchestrator import write_manifest


class MigrationOrchestratorTests(unittest.TestCase):
    def test_discover_and_checksum_manifest_roundtrip(self):
        with tempfile.TemporaryDirectory(dir=str(ROOT)) as tmpdir:
            base = pathlib.Path(tmpdir)
            migrations = base / "migrations"
            rollback = migrations / "rollback"
            rollback.mkdir(parents=True, exist_ok=True)

            (migrations / "000001_alpha.up.sql").write_text("CREATE TABLE alpha(id INTEGER PRIMARY KEY);")
            (migrations / "000001_alpha.down.sql").write_text("DROP TABLE alpha;")
            (migrations / "000002_beta.sql").write_text("CREATE TABLE beta(id INTEGER PRIMARY KEY);")
            (rollback / "000002_beta_rollback.sql").write_text("DROP TABLE beta;")

            units = discover_migrations(migration_dir=migrations, rollback_dir=rollback)
            self.assertEqual([unit.version for unit in units], [1, 2])
            self.assertIsNotNone(units[0].down_path)
            self.assertIsNotNone(units[1].down_path)

            entries = migration_checksum_entries(units)
            manifest = base / "checksums.sha256"
            write_manifest(manifest, entries)
            ok, mismatches = verify_manifest(manifest, entries)
            self.assertTrue(ok)
            self.assertEqual(mismatches, [])

    def test_apply_up_and_down_sqlite(self):
        with tempfile.TemporaryDirectory(dir=str(ROOT)) as tmpdir:
            base = pathlib.Path(tmpdir)
            migrations = base / "migrations"
            rollback = migrations / "rollback"
            rollback.mkdir(parents=True, exist_ok=True)

            (migrations / "000001_alpha.up.sql").write_text("CREATE TABLE alpha(id INTEGER PRIMARY KEY);")
            (migrations / "000001_alpha.down.sql").write_text("DROP TABLE alpha;")
            (migrations / "000002_beta.sql").write_text("CREATE TABLE beta(id INTEGER PRIMARY KEY);")
            (rollback / "000002_beta_rollback.sql").write_text("DROP TABLE beta;")

            units = discover_migrations(migration_dir=migrations, rollback_dir=rollback)
            db_path = base / "test.sqlite3"

            applied_up = apply_sqlite_migrations(
                db_path=db_path,
                units=units,
                direction="up",
                steps=None,
                target_version=None,
                dry_run=False,
            )
            self.assertEqual(applied_up, [1, 2])

            conn = sqlite3.connect(str(db_path))
            try:
                names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
                self.assertIn("alpha", names)
                self.assertIn("beta", names)
            finally:
                conn.close()

            applied_down = apply_sqlite_migrations(
                db_path=db_path,
                units=units,
                direction="down",
                steps=1,
                target_version=None,
                dry_run=False,
            )
            self.assertEqual(applied_down, [2])

            conn = sqlite3.connect(str(db_path))
            try:
                names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
                self.assertIn("alpha", names)
                self.assertNotIn("beta", names)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
