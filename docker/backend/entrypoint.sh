#!/bin/sh
set -eu

read_secret() {
  variable="$1"
  path="$2"

  if [ ! -s "$path" ]; then
    echo "Required secret is missing: $path" >&2
    exit 78
  fi

  value="$(cat "$path")"
  if [ -z "$value" ]; then
    echo "Required secret is empty: $path" >&2
    exit 78
  fi
  export "$variable=$value"
}

if [ "${VEDICWAY_ENV:-development}" = "production" ]; then
  profile="${VEDICWAY_SECRET_PROFILE:-api}"
  read_secret VEDICWAY_DATA_KEY "${VEDICWAY_DATA_KEY_FILE:-/run/secrets/vedicway_data_key}"
  read_secret VEDICWAY_SIGNING_KEY "${VEDICWAY_SIGNING_KEY_FILE:-/run/secrets/vedicway_signing_key}"

  if [ "$profile" = "lifecycle" ]; then
    exec "$@"
  fi

  if [ "$profile" = "email" ]; then
    read_secret VEDICWAY_SMTP_PASSWORD "${VEDICWAY_SMTP_PASSWORD_FILE:-/run/secrets/smtp_password}"
    exec "$@"
  fi

  if [ "$profile" = "api" ]; then
    read_secret VEDICWAY_OPERATIONS_TOKEN "${VEDICWAY_OPERATIONS_TOKEN_FILE:-/run/secrets/vedicway_operations_token}"
    read_secret VEDICWAY_METRICS_TOKEN "${VEDICWAY_METRICS_TOKEN_FILE:-/run/secrets/vedicway_metrics_token}"
    read_secret YOOKASSA_SHOP_ID "${YOOKASSA_SHOP_ID_FILE:-/run/secrets/yookassa_shop_id}"
    read_secret YOOKASSA_SECRET_KEY "${YOOKASSA_SECRET_KEY_FILE:-/run/secrets/yookassa_secret_key}"
  elif [ "$profile" = "worker" ]; then
    read_secret OPENAI_API_KEY "${OPENAI_API_KEY_FILE:-/run/secrets/codex_api_key}"
  else
    echo "Unknown VEDICWAY_SECRET_PROFILE: $profile" >&2
    exit 78
  fi

  read_secret postgres_password "${POSTGRES_PASSWORD_FILE:-/run/secrets/postgres_password}"

  encoded_password="$(python -c 'import os, urllib.parse; print(urllib.parse.quote(os.environ["postgres_password"], safe=""))')"
  encoded_user="$(python -c 'import os, urllib.parse; print(urllib.parse.quote(os.environ.get("POSTGRES_USER", "vedicway"), safe=""))')"
  encoded_database="$(python -c 'import os, urllib.parse; print(urllib.parse.quote(os.environ.get("POSTGRES_DB", "vedicway"), safe=""))')"
  database_url="postgresql+psycopg://${encoded_user}:${encoded_password}@${POSTGRES_HOST:-postgres}:${POSTGRES_PORT:-5432}/${encoded_database}"
  export DATABASE_URL="${DATABASE_URL:-$database_url}"
  export VEDICWAY_DATABASE_URL="${VEDICWAY_DATABASE_URL:-$database_url}"
  unset postgres_password encoded_password encoded_user encoded_database database_url
fi

exec "$@"
