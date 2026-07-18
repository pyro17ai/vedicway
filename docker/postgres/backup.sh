#!/bin/sh
set -eu
umask 077

password_file="${POSTGRES_PASSWORD_FILE:-/run/secrets/postgres_password}"
if [ ! -s "$password_file" ]; then
  echo "PostgreSQL password secret is missing" >&2
  exit 78
fi

export PGPASSWORD="$(cat "$password_file")"
host="${POSTGRES_HOST:-postgres}"
port="${POSTGRES_PORT:-5432}"
database="${POSTGRES_DB:-vedicway}"
user="${POSTGRES_USER:-vedicway}"
backup_dir="${BACKUP_DIR:-/backups}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="$backup_dir/${database}-${timestamp}.dump"

mkdir -p "$backup_dir"
pg_dump -h "$host" -p "$port" -U "$user" -d "$database" --format=custom --compress=9 --no-owner --no-privileges --file="$target"
sha256sum "$target" > "$target.sha256"
chmod 0600 "$target" "$target.sha256"
unset PGPASSWORD
echo "$target"
