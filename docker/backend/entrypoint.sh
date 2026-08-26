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

install_codex_auth() {
  path="$1"
  codex_home="${VEDICWAY_CODEX_HOME:-/var/lib/vedicway/codex-home}"

  if [ ! -s "$path" ]; then
    echo "Required Codex auth is missing: $path" >&2
    exit 78
  fi

  mkdir -p "$codex_home"
  cp "$path" "$codex_home/auth.json"
  chmod 0600 "$codex_home/auth.json"
  unset path codex_home
}

if [ "${VEDICWAY_ENV:-development}" = "production" ]; then
  profile="${VEDICWAY_SECRET_PROFILE:-api}"

  case "$profile" in
    seo-agent)
      if [ -n "${CODEX_AUTH_FILE:-}" ]; then
        install_codex_auth "$CODEX_AUTH_FILE"
      fi
      read_secret VEDICWAY_SEO_AGENT_TOKEN "${VEDICWAY_SEO_AGENT_TOKEN_FILE:-/run/secrets/vedicway_seo_agent_token}"
      read_secret VEDICWAY_YANDEX_SEARCH_API_KEY "${VEDICWAY_YANDEX_SEARCH_API_KEY_FILE:-/run/secrets/yandex_search_api_key}"
      read_secret VEDICWAY_YANDEX_FOLDER_ID "${VEDICWAY_YANDEX_FOLDER_ID_FILE:-/run/secrets/yandex_folder_id}"
      read_secret VEDICWAY_YANDEX_WEBMASTER_TOKEN "${VEDICWAY_YANDEX_WEBMASTER_TOKEN_FILE:-/run/secrets/yandex_webmaster_token}"
      read_secret VEDICWAY_YANDEX_METRIKA_TOKEN "${VEDICWAY_YANDEX_METRIKA_TOKEN_FILE:-/run/secrets/yandex_metrika_token}"
      read_secret VEDICWAY_VK_GROUP_ACCESS_TOKEN "${VEDICWAY_VK_GROUP_ACCESS_TOKEN_FILE:-/run/secrets/vedicway_vk_group_access_token}"
      read_secret VEDICWAY_VK_USER_ACCESS_TOKEN "${VEDICWAY_VK_USER_ACCESS_TOKEN_FILE:-/run/secrets/vedicway_vk_user_access_token}"
      ;;
    lifecycle)
      read_secret VEDICWAY_DATA_KEY "${VEDICWAY_DATA_KEY_FILE:-/run/secrets/vedicway_data_key}"
      read_secret VEDICWAY_SIGNING_KEY "${VEDICWAY_SIGNING_KEY_FILE:-/run/secrets/vedicway_signing_key}"
      ;;
    email)
      read_secret VEDICWAY_DATA_KEY "${VEDICWAY_DATA_KEY_FILE:-/run/secrets/vedicway_data_key}"
      read_secret VEDICWAY_SIGNING_KEY "${VEDICWAY_SIGNING_KEY_FILE:-/run/secrets/vedicway_signing_key}"
      read_secret VEDICWAY_SMTP_PASSWORD "${VEDICWAY_SMTP_PASSWORD_FILE:-/run/secrets/smtp_password}"
      ;;
    api)
      read_secret VEDICWAY_DATA_KEY "${VEDICWAY_DATA_KEY_FILE:-/run/secrets/vedicway_data_key}"
      read_secret VEDICWAY_SIGNING_KEY "${VEDICWAY_SIGNING_KEY_FILE:-/run/secrets/vedicway_signing_key}"
      read_secret VEDICWAY_OPERATIONS_TOKEN "${VEDICWAY_OPERATIONS_TOKEN_FILE:-/run/secrets/vedicway_operations_token}"
      read_secret VEDICWAY_METRICS_TOKEN "${VEDICWAY_METRICS_TOKEN_FILE:-/run/secrets/vedicway_metrics_token}"
      read_secret YOOKASSA_SHOP_ID "${YOOKASSA_SHOP_ID_FILE:-/run/secrets/yookassa_shop_id}"
      read_secret YOOKASSA_SECRET_KEY "${YOOKASSA_SECRET_KEY_FILE:-/run/secrets/yookassa_secret_key}"
      read_secret VEDICWAY_SEO_AGENT_TOKEN "${VEDICWAY_SEO_AGENT_TOKEN_FILE:-/run/secrets/vedicway_seo_agent_token}"
      ;;
    worker)
      read_secret VEDICWAY_DATA_KEY "${VEDICWAY_DATA_KEY_FILE:-/run/secrets/vedicway_data_key}"
      read_secret VEDICWAY_SIGNING_KEY "${VEDICWAY_SIGNING_KEY_FILE:-/run/secrets/vedicway_signing_key}"
      install_codex_auth "${CODEX_AUTH_FILE:-/run/secrets/codex_auth}"
      ;;
    *)
      echo "Unknown VEDICWAY_SECRET_PROFILE: $profile" >&2
      exit 78
      ;;
  esac

  read_secret postgres_password "${POSTGRES_PASSWORD_FILE:-/run/secrets/postgres_password}"

  encoded_password="$(python -c 'import os, urllib.parse; print(urllib.parse.quote(os.environ["postgres_password"], safe=""))')"
  encoded_user="$(python -c 'import os, urllib.parse; print(urllib.parse.quote(os.environ.get("POSTGRES_USER", "vedicway"), safe=""))')"
  encoded_database="$(python -c 'import os, urllib.parse; print(urllib.parse.quote(os.environ.get("POSTGRES_DB", "vedicway"), safe=""))')"
  database_url="postgresql+psycopg://${encoded_user}:${encoded_password}@${POSTGRES_HOST:-postgres}:${POSTGRES_PORT:-5432}/${encoded_database}"
  export DATABASE_URL="${DATABASE_URL:-$database_url}"
  export VEDICWAY_DATABASE_URL="${VEDICWAY_DATABASE_URL:-$database_url}"
  unset postgres_password encoded_password encoded_user encoded_database database_url profile
fi

exec "$@"
