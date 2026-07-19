from __future__ import annotations

import argparse
import os
from pathlib import Path
from urllib.parse import quote

from vedicway_backend.content_store import ContentDatabase


def _secret(path: Path, label: str) -> str:
    if not path.is_file():
        raise SystemExit(f"{label} secret is missing")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise SystemExit(f"{label} secret is empty")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="One-shot VedicWay administrator bootstrap")
    parser.add_argument("--email-file", type=Path, default=Path("/run/secrets/admin_bootstrap_email"))
    parser.add_argument("--password-file", type=Path, default=Path("/run/secrets/admin_bootstrap_password"))
    parser.add_argument("--postgres-password-file", type=Path, default=Path("/run/secrets/postgres_password"))
    args = parser.parse_args()

    email = _secret(args.email_file, "Admin email")
    password = _secret(args.password_file, "Admin password")
    postgres_password = _secret(args.postgres_password_file, "PostgreSQL password")
    user = quote(os.environ.get("POSTGRES_USER", "vedicway"), safe="")
    database = quote(os.environ.get("POSTGRES_DB", "vedicway"), safe="")
    host = os.environ.get("POSTGRES_HOST", "postgres")
    port = os.environ.get("POSTGRES_PORT", "5432")
    database_url = (
        f"postgresql+psycopg://{user}:{quote(postgres_password, safe='')}@{host}:{port}/{database}"
    )

    os.environ.update(
        VEDICWAY_ENV="production",
        VEDICWAY_DATABASE_URL=database_url,
        VEDICWAY_BOOTSTRAP_ADMIN_EMAIL=email,
        VEDICWAY_BOOTSTRAP_ADMIN_PASSWORD=password,
    )
    try:
        content_database = ContentDatabase()
        content_database.ping(require_migrations=True)
        created = content_database.bootstrap_admin_from_environment()
    finally:
        for name in (
            "VEDICWAY_BOOTSTRAP_ADMIN_EMAIL",
            "VEDICWAY_BOOTSTRAP_ADMIN_PASSWORD",
            "VEDICWAY_DATABASE_URL",
        ):
            os.environ.pop(name, None)
    print("Administrator created." if created else "Administrator already exists.")


if __name__ == "__main__":
    main()
