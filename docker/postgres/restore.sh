#!/bin/sh
set -eu
umask 077

password_file="${POSTGRES_PASSWORD_FILE:-/run/secrets/postgres_password}"
backup_dir="${BACKUP_DIR:-/backups}"
database="${POSTGRES_DB:-vedicway}"
restore_file="${RESTORE_FILE:-}"
pair_id="${RESTORE_SET_ID:-}"
phase="${RESTORE_PHASE:-prepare}"

if [ ! -s "$password_file" ]; then echo "PostgreSQL password secret is missing" >&2; exit 78; fi
case "$pair_id" in *[!A-Za-z0-9._-]*|"") echo "RESTORE_SET_ID is invalid" >&2; exit 64 ;; esac
if [ "${CONFIRM_RESTORE:-}" != "restore-$database" ]; then
  echo "Set CONFIRM_RESTORE=restore-$database" >&2
  exit 64
fi

export PGPASSWORD="$(cat "$password_file")"
host="${POSTGRES_HOST:-postgres}"
port="${POSTGRES_PORT:-5432}"
user="${POSTGRES_USER:-vedicway}"
suffix="$(printf '%s' "$pair_id" | sha256sum | cut -c1-12)"
staging="${database}_restore_${suffix}"
previous="${database}_previous_${suffix}"

db_exists() {
  psql -h "$host" -p "$port" -U "$user" -d postgres -Atqc \
    "SELECT 1 FROM pg_database WHERE datname = '$1'" | grep -q 1
}

terminate_database() {
  psql -h "$host" -p "$port" -U "$user" -d postgres -v ON_ERROR_STOP=1 -v name="$1" <<'SQL'
SELECT pg_terminate_backend(pid) FROM pg_stat_activity
WHERE datname = :'name' AND pid <> pg_backend_pid();
SQL
}

case "$phase" in
  prepare)
    if [ -z "$restore_file" ] || [ "$(basename "$restore_file")" != "$restore_file" ]; then
      echo "RESTORE_FILE must be a plain file name" >&2; exit 64
    fi
    target="$backup_dir/$restore_file"
    if [ ! -s "$target" ]; then echo "Dump is missing: $target" >&2; exit 66; fi
    if db_exists "$staging" || db_exists "$previous"; then
      echo "Restore staging already exists; run rollback before retry" >&2; exit 65
    fi
    psql -h "$host" -p "$port" -U "$user" -d postgres -v ON_ERROR_STOP=1 -v staging="$staging" <<'SQL'
CREATE DATABASE :"staging";
SQL
    if ! pg_restore -h "$host" -p "$port" -U "$user" -d "$staging" --exit-on-error --no-owner --no-privileges "$target"; then
      terminate_database "$staging"
      psql -h "$host" -p "$port" -U "$user" -d postgres -v ON_ERROR_STOP=1 -v staging="$staging" -c 'DROP DATABASE :"staging"'
      exit 1
    fi
    ;;
  commit)
    db_exists "$staging" || { echo "Prepared database is missing" >&2; exit 66; }
    ! db_exists "$previous" || { echo "Previous database slot is occupied" >&2; exit 65; }
    terminate_database "$database"
    psql -h "$host" -p "$port" -U "$user" -d postgres -v ON_ERROR_STOP=1 -v live="$database" -v previous="$previous" -c 'ALTER DATABASE :"live" RENAME TO :"previous"'
    if ! psql -h "$host" -p "$port" -U "$user" -d postgres -v ON_ERROR_STOP=1 -v staging="$staging" -v live="$database" -c 'ALTER DATABASE :"staging" RENAME TO :"live"'; then
      psql -h "$host" -p "$port" -U "$user" -d postgres -v ON_ERROR_STOP=1 -v previous="$previous" -v live="$database" -c 'ALTER DATABASE :"previous" RENAME TO :"live"'
      exit 1
    fi
    ;;
  rollback)
    if db_exists "$previous"; then
      if db_exists "$database"; then
        terminate_database "$database"
        psql -h "$host" -p "$port" -U "$user" -d postgres -v ON_ERROR_STOP=1 -v live="$database" -c 'DROP DATABASE :"live"'
      fi
      psql -h "$host" -p "$port" -U "$user" -d postgres -v ON_ERROR_STOP=1 -v previous="$previous" -v live="$database" -c 'ALTER DATABASE :"previous" RENAME TO :"live"'
    fi
    if db_exists "$staging"; then
      terminate_database "$staging"
      psql -h "$host" -p "$port" -U "$user" -d postgres -v ON_ERROR_STOP=1 -v staging="$staging" -c 'DROP DATABASE :"staging"'
    fi
    ;;
  finalize)
    if db_exists "$previous"; then
      terminate_database "$previous"
      psql -h "$host" -p "$port" -U "$user" -d postgres -v ON_ERROR_STOP=1 -v previous="$previous" -c 'DROP DATABASE :"previous"'
    fi
    if db_exists "$staging"; then
      terminate_database "$staging"
      psql -h "$host" -p "$port" -U "$user" -d postgres -v ON_ERROR_STOP=1 -v staging="$staging" -c 'DROP DATABASE :"staging"'
    fi
    ;;
  *) echo "RESTORE_PHASE must be prepare, commit, rollback, or finalize" >&2; exit 64 ;;
esac

unset PGPASSWORD
echo "PostgreSQL restore phase completed: $phase ($pair_id)"
