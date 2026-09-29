#!/usr/bin/env bash
# Restore to a NEW lab_restore_* database. Never overwrite the source DB.
set -euo pipefail
package=${1:?Usage: lab-restore PACKAGE_DIRECTORY lab_restore_NAME}
target=${2:?Usage: lab-restore PACKAGE_DIRECTORY lab_restore_NAME}
[[ "$target" =~ ^lab_restore_[a-z0-9_]{1,30}$ ]] || { echo 'Target must start with lab_restore_' >&2; exit 2; }
script_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
validator=${LAB_BACKUP_VALIDATOR:-$script_root/validate_backup.py}
python3 "$validator" "$package" > /dev/null
pg_restore --list "$package/database.dump" > /dev/null
exists=$(runuser -u postgres -- psql -X -tAc "SELECT 1 FROM pg_database WHERE datname='$target'")
[[ "${exists//[[:space:]]/}" != 1 ]] || { echo 'Target database already exists; refusing overwrite' >&2; exit 2; }
# createdb is atomic: if a concurrent process creates the same name, we fail
# before installing the cleanup trap and cannot drop its database.
runuser -u postgres -- createdb -T template0 "$target"
cleanup() {
  local result=$?
  if ((result != 0)); then
    runuser -u postgres -- dropdb --if-exists "$target" || true
    logger -t network-lab-restore "Restore failed for $target (exit $result)" || true
  fi
}
trap cleanup EXIT
runuser -u postgres -- pg_restore --exit-on-error --single-transaction --no-owner --no-acl --dbname="$target" < "$package/database.dump"
runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -d "$target" -c ANALYZE > /dev/null
logger -t network-lab-restore "Restore completed: $target" || true
echo "Restored to $target"
