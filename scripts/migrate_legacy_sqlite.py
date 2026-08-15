from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]

RUNTIME_TABLES = (
    "anonymous_sessions",
    "birth_profiles",
    "charts",
    "chart_access",
    "jobs",
    "outbox_events",
    "agent_runs",
    "purchases",
    "payment_events",
    "payment_incidents",
    "entitlements",
    "rectifications",
    "refunds",
    "payment_operations",
    "reports",
    "pdf_render_requests",
    "rate_limit_events",
    "saved_questions",
    "magic_links",
    "magic_link_confirmations",
    "privacy_requests",
    "erasure_tombstones",
    "retention_runs",
    "email_deliveries",
)

CONTENT_TABLES = (
    "articles",
    "article_comments",
    "media_assets",
    "consent_records",
)

SEO_TABLES = (
    "settings",
    "source_documents",
    "cron_runs",
    "skill_runs",
    "raw_tool_responses",
    "keyword_queries",
    "serp_snapshots",
    "keyword_clusters",
    "cluster_queries",
    "content_briefs",
    "article_drafts",
    "article_media",
    "publication_attempts",
    "publications",
    "performance_snapshots",
    "optimization_actions",
    "job_results",
    "audit_events",
)


def _dsn(database_url: str) -> str:
    if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise SystemExit("DATABASE_URL must use PostgreSQL")
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def _source_tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }


def _target_columns(
    connection: psycopg.Connection[Any], schema: str, table: str
) -> dict[str, str]:
    return {
        str(name): str(data_type)
        for name, data_type in connection.execute(
            """SELECT column_name, data_type
               FROM information_schema.columns
               WHERE table_schema = %s AND table_name = %s
               ORDER BY ordinal_position""",
            (schema, table),
        )
    }


def _convert(value: Any, data_type: str) -> Any:
    if value is None:
        return None
    if data_type in {"json", "jsonb"}:
        return Jsonb(json.loads(value) if isinstance(value, str) else value)
    if data_type == "boolean":
        return bool(value)
    if data_type.startswith("timestamp") and isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


def _copy_database(
    target: psycopg.Connection[Any],
    source_path: Path,
    schema: str,
    tables: tuple[str, ...],
) -> dict[str, int]:
    result: dict[str, int] = {}
    uri = f"file:{source_path.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as source:
        source.row_factory = sqlite3.Row
        available = _source_tables(source)
        for table in tables:
            if table not in available:
                continue
            target_columns = _target_columns(target, schema, table)
            source_columns = [
                str(row[1])
                for row in source.execute(f'PRAGMA table_info("{table}")')
                if str(row[1]) in target_columns
            ]
            if not source_columns:
                continue
            column_sql = sql.SQL(", ").join(map(sql.Identifier, source_columns))
            placeholders = sql.SQL(", ").join(sql.Placeholder() * len(source_columns))
            statement = sql.SQL(
                "INSERT INTO {}.{} ({}) VALUES ({}) ON CONFLICT DO NOTHING"
            ).format(
                sql.Identifier(schema),
                sql.Identifier(table),
                column_sql,
                placeholders,
            )
            quoted_columns = ", ".join(
                f'"{name.replace(chr(34), chr(34) * 2)}"' for name in source_columns
            )
            quoted_table = table.replace('"', '""')
            inserted = 0
            for row in source.execute(
                f'SELECT {quoted_columns} FROM "{quoted_table}"'
            ):
                values = [
                    _convert(row[name], target_columns[name]) for name in source_columns
                ]
                inserted += target.execute(statement, values).rowcount
            result[table] = inserted
    return result


def _reset_sequence(
    connection: psycopg.Connection[Any], schema: str, table: str
) -> None:
    sequence = connection.execute(
        "SELECT pg_get_serial_sequence(%s, 'id')", (f"{schema}.{table}",)
    ).fetchone()[0]
    if not sequence:
        return
    maximum = connection.execute(
        sql.SQL("SELECT COALESCE(MAX(id), 0) FROM {}.{}").format(
            sql.Identifier(schema), sql.Identifier(table)
        )
    ).fetchone()[0]
    connection.execute(
        "SELECT setval(%s::regclass, %s, %s)",
        (sequence, max(1, maximum), maximum > 0),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="One-time import of legacy VedicWay databases into PostgreSQL"
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL")
        or os.environ.get("VEDICWAY_DATABASE_URL"),
    )
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit("DATABASE_URL is required")

    sources = (
        (ROOT / "backend/.data/vedicway.sqlite3", "runtime", RUNTIME_TABLES),
        (ROOT / "backend/.data/content.sqlite3", "public", CONTENT_TABLES),
        (ROOT / ".data/content.sqlite3", "public", CONTENT_TABLES),
        (
            ROOT / ".data/seo-agent/vedicway_seo_agent.sqlite3",
            "seo_agent",
            SEO_TABLES,
        ),
    )
    existing = [source for source in sources if source[0].is_file()]
    if not existing:
        raise SystemExit("No legacy database files were found")

    summaries: dict[str, dict[str, int]] = {}
    with psycopg.connect(_dsn(args.database_url)) as target:
        target.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended('vedicway-legacy-import', 0))"
        )
        for source_path, schema, tables in existing:
            summaries[str(source_path.relative_to(ROOT))] = _copy_database(
                target, source_path, schema, tables
            )
        _reset_sequence(target, "runtime", "outbox_events")
        _reset_sequence(target, "seo_agent", "audit_events")

    print(json.dumps(summaries, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
