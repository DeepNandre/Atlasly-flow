#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

DB_PATH="${1:-atlasly_stage2_demo.sqlite3}"
if [[ ! -f "${DB_PATH}" ]]; then
  echo "database file not found: ${DB_PATH}"
  exit 1
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="${TMPDIR:-/tmp}/atlasly-backup-${STAMP}"
mkdir -p "${BACKUP_DIR}"

BACKUP_PATH="${BACKUP_DIR}/atlasly.sqlite3.backup"
RESTORE_PATH="${BACKUP_DIR}/atlasly.sqlite3.restore"

cp "${DB_PATH}" "${BACKUP_PATH}"
cp "${BACKUP_PATH}" "${RESTORE_PATH}"

python3 - "$BACKUP_PATH" "$RESTORE_PATH" <<'PY'
import sqlite3
import sys

backup = sqlite3.connect(sys.argv[1])
restore = sqlite3.connect(sys.argv[2])
try:
    backup_count = backup.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0]
    restore_count = restore.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0]
    if backup_count != restore_count:
        raise SystemExit(f"schema mismatch after restore: backup={backup_count} restore={restore_count}")
    print(f"backup/restore rehearsal passed (schema objects={backup_count})")
finally:
    backup.close()
    restore.close()
PY

echo "backup artifact: ${BACKUP_PATH}"
echo "restore artifact: ${RESTORE_PATH}"
