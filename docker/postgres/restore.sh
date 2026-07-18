#!/bin/sh
set -eu

password_file="${POSTGRES_PASSWORD_FILE:-/run/secrets/postgres_password}"
backup_dir="${BACKUP_DIR:-/backups}"
database="${POSTGRES_DB:-vedicway}"
restore_file="${RESTORE_FILE:-}"

if [ ! -s "$password_file" ]; then
  echo "PostgreSQL password secret is missing" >&2
  exit 78
fi
if [ -z "$restore_file" ]; then
  echo "RESTORE_FILE must name a dump inside $backup_dir" >&2
  exit 64
fi
case "$restore_file" in
  /*|*..*) echo "RESTORE_FILE must be a plain file name" >&2; exit 64 ;;
esac
if [ "${CONFIRM_RESTORE:-}" != "restore-$database" ]; then
  echo "Set CONFIRM_RESTORE=restore-$database to authorize destructive restore" >&2
  exit 64
fi

target="$backup_dir/$restore_file"
if [ ! -s "$target" ] || [ ! -s "$target.sha256" ]; then
  echo "Dump or checksum is missing: $target" >&2
  exit 66
fi
(cd "$backup_dir" && sha256sum -c "$restore_file.sha256")

export PGPASSWORD="$(cat "$password_file")"
host="${POSTGRES_HOST:-postgres}"
port="${POSTGRES_PORT:-5432}"
user="${POSTGRES_USER:-vedicway}"

psql -h "$host" -p "$port" -U "$user" -d postgres -v ON_ERROR_STOP=1 -v database="$database" <<'SQL'
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = :'database' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS :"database";
CREATE DATABASE :"database";
SQL
pg_restore -h "$host" -p "$port" -U "$user" -d "$database" --exit-on-error --no-owner --no-privileges "$target"
unset PGPASSWORD
echo "Restore completed: $restore_file -> $database"
