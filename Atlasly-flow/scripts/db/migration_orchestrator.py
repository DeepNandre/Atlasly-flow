from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import argparse
import hashlib
import pathlib
import re
import sqlite3
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_MIGRATION_DIR = ROOT / "db" / "migrations"
DEFAULT_ROLLBACK_DIR = DEFAULT_MIGRATION_DIR / "rollback"
DEFAULT_MANIFEST = DEFAULT_MIGRATION_DIR / "checksums.sha256"

VERSION_RE = re.compile(r"^(?P<version>\d{6})_.+\.sql$")


@dataclass(frozen=True)
class MigrationUnit:
    version: int
    up_path: pathlib.Path
    down_path: pathlib.Path | None


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def discover_migrations(
    *,
    migration_dir: pathlib.Path = DEFAULT_MIGRATION_DIR,
    rollback_dir: pathlib.Path = DEFAULT_ROLLBACK_DIR,
) -> list[MigrationUnit]:
    up_by_version: dict[int, pathlib.Path] = {}
    down_by_version: dict[int, pathlib.Path] = {}

    for path in sorted(migration_dir.glob("*.sql")):
        match = VERSION_RE.match(path.name)
        if not match:
            continue
        version = int(match.group("version"))
        if path.name.endswith(".down.sql"):
            down_by_version[version] = path
            continue
        if path.name.endswith(".up.sql"):
            up_by_version[version] = path
            continue
        up_by_version[version] = path

    for path in sorted(rollback_dir.glob("*.sql")):
        match = VERSION_RE.match(path.name)
        if not match:
            continue
        version = int(match.group("version"))
        down_by_version.setdefault(version, path)

    units: list[MigrationUnit] = []
    for version in sorted(up_by_version):
        units.append(
            MigrationUnit(
                version=version,
                up_path=up_by_version[version],
                down_path=down_by_version.get(version),
            )
        )
    return units


def migration_checksum_entries(units: list[MigrationUnit]) -> dict[str, str]:
    entries: dict[str, str] = {}
    for unit in units:
        up_rel = str(unit.up_path.relative_to(ROOT))
        entries[up_rel] = _sha256(unit.up_path)
        if unit.down_path:
            down_rel = str(unit.down_path.relative_to(ROOT))
            entries[down_rel] = _sha256(unit.down_path)
    return dict(sorted(entries.items()))


def parse_manifest(manifest_path: pathlib.Path) -> dict[str, str]:
    if not manifest_path.exists():
        return {}
    entries: dict[str, str] = {}
    for line in manifest_path.read_text().splitlines():
        row = line.strip()
        if not row:
            continue
        parts = row.split("  ", maxsplit=1)
        if len(parts) != 2:
            raise ValueError(f"invalid manifest row: {row}")
        checksum, rel_path = parts
        entries[rel_path] = checksum
    return entries


def write_manifest(manifest_path: pathlib.Path, entries: dict[str, str]) -> None:
    lines = [f"{checksum}  {rel_path}" for rel_path, checksum in sorted(entries.items())]
    manifest_path.write_text("\n".join(lines) + "\n")


def verify_manifest(manifest_path: pathlib.Path, entries: dict[str, str]) -> tuple[bool, list[str]]:
    recorded = parse_manifest(manifest_path)
    mismatches: list[str] = []
    for rel_path, checksum in entries.items():
        actual = recorded.get(rel_path)
        if actual != checksum:
            mismatches.append(rel_path)
    for rel_path in sorted(set(recorded) - set(entries)):
        mismatches.append(rel_path)
    return len(mismatches) == 0, sorted(mismatches)


def _ensure_migration_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def _applied_versions(conn: sqlite3.Connection) -> set[int]:
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {int(row[0]) for row in rows}


def _execute_script(conn: sqlite3.Connection, sql_path: pathlib.Path) -> None:
    conn.executescript(sql_path.read_text())


def apply_sqlite_migrations(
    *,
    db_path: pathlib.Path,
    units: list[MigrationUnit],
    direction: str,
    steps: int | None,
    target_version: int | None,
    dry_run: bool,
) -> list[int]:
    conn = sqlite3.connect(str(db_path))
    try:
        _ensure_migration_table(conn)
        applied = _applied_versions(conn)
        selected: list[MigrationUnit] = []

        if direction == "up":
            for unit in units:
                if unit.version in applied:
                    continue
                if target_version is not None and unit.version > target_version:
                    continue
                selected.append(unit)
            if steps is not None:
                selected = selected[: max(0, steps)]
        else:
            for unit in reversed(units):
                if unit.version not in applied:
                    continue
                if target_version is not None and unit.version <= target_version:
                    continue
                selected.append(unit)
            if steps is not None:
                selected = selected[: max(0, steps)]

        if dry_run:
            return [unit.version for unit in selected]

        for unit in selected:
            with conn:
                if direction == "up":
                    _execute_script(conn, unit.up_path)
                    conn.execute(
                        "INSERT OR REPLACE INTO schema_migrations(version, checksum, applied_at) VALUES(?,?,?)",
                        (unit.version, _sha256(unit.up_path), datetime.now(timezone.utc).isoformat()),
                    )
                else:
                    if not unit.down_path:
                        raise RuntimeError(f"missing rollback for migration {unit.version:06d}")
                    _execute_script(conn, unit.down_path)
                    conn.execute("DELETE FROM schema_migrations WHERE version = ?", (unit.version,))
        return [unit.version for unit in selected]
    finally:
        conn.close()


def _plan_units(
    *,
    units: list[MigrationUnit],
    direction: str,
    steps: int | None,
    target_version: int | None,
) -> list[MigrationUnit]:
    selected = list(units) if direction == "up" else list(reversed(units))
    if target_version is not None:
        if direction == "up":
            selected = [unit for unit in selected if unit.version <= target_version]
        else:
            selected = [unit for unit in selected if unit.version > target_version]
    if steps is not None:
        selected = selected[: max(0, steps)]
    return selected


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Atlasly SQL migration orchestration helper")
    parser.add_argument("--action", choices={"plan", "verify", "write-manifest", "apply"}, required=True)
    parser.add_argument("--direction", choices={"up", "down"}, default="up")
    parser.add_argument("--steps", type=int, default=None)
    parser.add_argument("--target-version", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--db-path", default=str(ROOT / "atlasly_stage2_demo.sqlite3"))
    parser.add_argument("--migration-dir", default=str(DEFAULT_MIGRATION_DIR))
    parser.add_argument("--rollback-dir", default=str(DEFAULT_ROLLBACK_DIR))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    migration_dir = pathlib.Path(args.migration_dir).resolve()
    rollback_dir = pathlib.Path(args.rollback_dir).resolve()
    manifest_path = pathlib.Path(args.manifest).resolve()
    units = discover_migrations(migration_dir=migration_dir, rollback_dir=rollback_dir)
    entries = migration_checksum_entries(units)

    if args.action == "verify":
        ok, mismatches = verify_manifest(manifest_path, entries)
        if ok:
            print("manifest verified")
            return 0
        print("manifest mismatch")
        for rel_path in mismatches:
            print(rel_path)
        return 1

    if args.action == "write-manifest":
        write_manifest(manifest_path, entries)
        print(f"manifest written: {manifest_path}")
        return 0

    if args.action == "plan":
        planned = _plan_units(
            units=units,
            direction=args.direction,
            steps=args.steps,
            target_version=args.target_version,
        )
        for unit in planned:
            down_ref = "-" if unit.down_path is None else str(unit.down_path.relative_to(ROOT))
            print(f"{unit.version:06d} up={unit.up_path.relative_to(ROOT)} down={down_ref}")
        return 0

    applied = apply_sqlite_migrations(
        db_path=pathlib.Path(args.db_path).resolve(),
        units=units,
        direction=args.direction,
        steps=args.steps,
        target_version=args.target_version,
        dry_run=bool(args.dry_run),
    )
    if args.dry_run:
        print("dry-run versions:", ",".join(str(v) for v in applied))
    else:
        print("applied versions:", ",".join(str(v) for v in applied))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
