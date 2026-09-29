#!/usr/bin/env bash
# Local PostgreSQL backup. Install as /usr/local/sbin/lab-backup.
set -euo pipefail
umask 077
database=${LAB_DB:-labapp}
backup_root=${LAB_BACKUP_DIR:-/var/backups/network-lab}
retention=${LAB_RETENTION_DAYS:-7}
[[ "$database" =~ ^[a-z][a-z0-9_]{0,40}$ ]] || { echo 'Invalid database name' >&2; exit 2; }
if [[ ! "$retention" =~ ^[0-9]+$ ]] || ((retention < 1 || retention > 365)); then
  echo 'Invalid retention' >&2; exit 2
fi
[[ "$backup_root" == /* && "$backup_root" != / && ! -L "$backup_root" ]] || { echo 'Unsafe backup directory' >&2; exit 2; }
backup_root=$(realpath -m -- "$backup_root")
[[ "$backup_root" != / ]] || { echo 'Unsafe backup directory' >&2; exit 2; }
mkdir -p -- "$backup_root"
exec 9>"$backup_root/.backup.lock"
flock -n 9 || { echo 'A backup is already running' >&2; exit 75; }
stage=$(mktemp -d "$backup_root/.staging.XXXXXXXX")
cleanup() {
  local result=$?
  if [[ -n "${stage:-}" && -d "$stage" ]]; then rm -rf -- "$stage"; fi
  if ((result != 0)); then logger -t network-lab-backup "Backup failed for $database (exit $result)" || true; fi
}
trap cleanup EXIT
runuser -u postgres -- pg_dump --format=custom --no-owner --no-acl --dbname="$database" > "$stage/database.dump"
[[ -s "$stage/database.dump" ]] || { echo 'Empty dump' >&2; exit 1; }
pg_restore --list "$stage/database.dump" > /dev/null
python3 - "$stage" "$database" <<'PY'
import hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path
directory = Path(sys.argv[1])
checksum = hashlib.sha256()
with directory.joinpath('database.dump').open('rb') as handle:
    for block in iter(lambda: handle.read(1024 * 1024), b''):
        checksum.update(block)
digest = checksum.hexdigest()
directory.joinpath('manifest.json').write_text(json.dumps({
    'schema_version': 1, 'database': sys.argv[2],
    'created_at': datetime.now(timezone.utc).isoformat(),
    'sha256': digest, 'size_bytes': directory.joinpath('database.dump').stat().st_size,
}, indent=2) + '\n')
PY
final="$backup_root/${database}_$(date -u +%Y%m%dT%H%M%SZ)_${stage##*.staging.}"
mv -- "$stage" "$final"
stage=''
# Retention runs only after a complete, validated backup is committed.
find "$backup_root" -mindepth 1 -maxdepth 1 -type d -name "${database}_20*" -mmin "+$((retention * 1440))" -exec rm -rf -- {} +
logger -t network-lab-backup "Backup completed: $final" || true
printf '%s\n' "$final"
