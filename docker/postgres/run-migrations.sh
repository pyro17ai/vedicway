#!/bin/sh
set -eu

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
migration_dir="${MIGRATIONS_DIR:-/migrations}"

psql -h "$host" -p "$port" -U "$user" -d "$database" -v ON_ERROR_STOP=1 <<'SQL'
CREATE TABLE IF NOT EXISTS schema_migrations (
  version text PRIMARY KEY,
  checksum text NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now()
);
SQL

for migration in "$migration_dir"/*.sql; do
  [ -f "$migration" ] || continue
  version="$(basename "$migration")"
  checksum="$(sha256sum "$migration" | awk '{print $1}')"
  recorded="$(
    printf "SELECT checksum FROM schema_migrations WHERE version = :'version';\n" |
      psql -h "$host" -p "$port" -U "$user" -d "$database" -At -v ON_ERROR_STOP=1 -v version="$version"
  )"

  if [ -n "$recorded" ]; then
    if [ "$recorded" != "$checksum" ]; then
      echo "Migration checksum changed after apply: $version" >&2
      exit 65
    fi
    echo "Already applied: $version"
    continue
  fi

  echo "Applying: $version"
  {
    printf 'BEGIN;\n'
    cat "$migration"
    printf '\nINSERT INTO schema_migrations(version, checksum) VALUES (:\047version\047, :\047checksum\047);\nCOMMIT;\n'
  } | psql -h "$host" -p "$port" -U "$user" -d "$database" -v ON_ERROR_STOP=1 -v version="$version" -v checksum="$checksum"
done

unset PGPASSWORD
