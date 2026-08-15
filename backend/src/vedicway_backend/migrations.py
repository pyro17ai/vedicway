from __future__ import annotations

import hashlib
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


def apply_runtime_migrations(database_url: str | None = None) -> list[str]:
    configured_url = (
        database_url
        or os.environ.get("DATABASE_URL")
        or os.environ.get("VEDICWAY_DATABASE_URL")
    )
    if not configured_url:
        raise RuntimeError("DATABASE_URL is required")
    if not configured_url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise RuntimeError("DATABASE_URL must use PostgreSQL")
    dsn = configured_url.replace("postgresql+psycopg://", "postgresql://", 1)
    migration_dir = Path(__file__).resolve().parents[2] / "migrations"
    applied: list[str] = []

    with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS public.schema_migrations (
                 version text PRIMARY KEY,
                 checksum text NOT NULL,
                 applied_at timestamptz NOT NULL DEFAULT now()
               )"""
        )
        existing = {
            row["version"]: row["checksum"]
            for row in connection.execute(
                "SELECT version, checksum FROM public.schema_migrations"
            )
        }
        for migration in sorted(migration_dir.glob("*.sql")):
            version = migration.name
            sql = migration.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
            recorded = existing.get(version)
            if recorded:
                if recorded != checksum:
                    raise RuntimeError(f"Migration checksum changed after apply: {version}")
                continue
            connection.execute("BEGIN")
            try:
                connection.execute(sql)
                connection.execute(
                    """INSERT INTO public.schema_migrations(version, checksum)
                       VALUES (%s, %s)""",
                    (version, checksum),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            applied.append(version)
    return applied


def main() -> None:
    for version in apply_runtime_migrations():
        print(f"Applied runtime migration: {version}")


if __name__ == "__main__":
    main()
