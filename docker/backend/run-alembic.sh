#!/bin/sh
set -eu

password_file="${POSTGRES_PASSWORD_FILE:-/run/secrets/postgres_password}"
if [ ! -s "$password_file" ]; then
  echo "PostgreSQL password secret is missing" >&2
  exit 78
fi
if [ ! -s /opt/vedicway/backend/alembic.ini ]; then
  echo "Alembic configuration is missing from the backend image" >&2
  exit 66
fi

database_url="$(python - "$password_file" <<'PY'
import os
import sys
from pathlib import Path
from urllib.parse import quote

password = Path(sys.argv[1]).read_text(encoding="utf-8").strip()
user = quote(os.environ.get("POSTGRES_USER", "vedicway"), safe="")
database = quote(os.environ.get("POSTGRES_DB", "vedicway"), safe="")
host = os.environ.get("POSTGRES_HOST", "postgres")
port = os.environ.get("POSTGRES_PORT", "5432")
print(f"postgresql+psycopg://{user}:{quote(password, safe='')}@{host}:{port}/{database}")
PY
)"
export VEDICWAY_DATABASE_URL="$database_url"
unset database_url

cd /opt/vedicway/backend
exec /opt/venv/bin/alembic -c alembic.ini upgrade head
