from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg
from PIL import Image, UnidentifiedImageError
from psycopg.rows import dict_row

SCHEMA_VERSION = "1.4.0"
MANUAL_QUALITY_CHECKS = {
    "brief_alignment",
    "evidence_verified",
    "originality_reviewed",
    "prohibited_claims_reviewed",
}
TOOL_PROVIDER_ALIASES = {
    "yandex-search": "yandex-search",
    "yandex_search": "yandex-search",
    "search": "yandex-search",
    "yandex-wordstat": "wordstat",
    "yandex_wordstat": "wordstat",
    "wordstat": "wordstat",
    "yandex-webmaster": "webmaster",
    "yandex_webmaster": "webmaster",
    "webmaster": "webmaster",
    "yandex-metrika": "metrika",
    "yandex_metrika": "metrika",
    "metrika": "metrika",
    "site": "site",
    "dzen": "dzen",
    "vk": "vk",
    "pinterest": "pinterest",
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def normalize_tool_provider(value: Any) -> str:
    provider = TOOL_PROVIDER_ALIASES.get(str(value).strip().casefold())
    if provider is None:
        raise LedgerError("Unsupported tool-response provider")
    return provider


def normalize_tool_response(value: Any) -> dict[str, Any] | list[Any]:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str) and value.strip():
        return {"text": value}
    raise LedgerError("Tool response must be a JSON object, array or non-empty text")


class LedgerError(RuntimeError):
    pass


class AgentLedger:
    def __init__(
        self,
        database_url: str | None = None,
        *,
        data_dir: str | Path | None = None,
    ) -> None:
        root = Path(data_dir or os.environ.get("VEDICWAY_SEO_DATA_DIR", Path.cwd() / ".data" / "seo-agent"))
        self.data_dir = root.expanduser().resolve()
        configured_url = (
            database_url
            or os.environ.get("VEDICWAY_SEO_DATABASE_URL")
            or os.environ.get("DATABASE_URL")
            or os.environ.get("VEDICWAY_DATABASE_URL")
        )
        if not configured_url:
            raise LedgerError("DATABASE_URL is required for the SEO ledger")
        if not configured_url.startswith(("postgresql://", "postgresql+psycopg://")):
            raise LedgerError("SEO ledger database must use PostgreSQL")
        self.database_url = configured_url
        self._database_dsn = configured_url.replace("postgresql+psycopg://", "postgresql://", 1)
        self.migrations_dir = Path(__file__).with_name("migrations")

    @contextmanager
    def connect(self) -> Iterator[psycopg.Connection[dict[str, Any]]]:
        connection = psycopg.connect(
            self._database_dsn,
            autocommit=True,
            row_factory=dict_row,
        )
        try:
            connection.execute("SET search_path TO seo_agent, public")
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(
        self, *, immediate: bool = False
    ) -> Iterator[psycopg.Connection[dict[str, Any]]]:
        with self.connect() as connection:
            connection.execute("BEGIN")
            if immediate:
                connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended('vedicway-seo-ledger', 0))"
                )
            try:
                yield connection
            except Exception:
                connection.rollback()
                raise
            else:
                connection.commit()

    def initialize(self) -> list[str]:
        applied: list[str] = []
        with self.connect() as connection:
            connection.execute("CREATE SCHEMA IF NOT EXISTS seo_agent")
            existing = {
                row["version"]: row["checksum"]
                for row in connection.execute(
                    "SELECT version, checksum FROM schema_migrations"
                ).fetchall()
            } if self._table_exists(connection, "schema_migrations") else {}
            for migration in sorted(self.migrations_dir.glob("*.sql")):
                version = migration.stem
                sql = migration.read_text(encoding="utf-8")
                checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
                if version in existing:
                    if existing[version] != checksum:
                        raise LedgerError(f"Migration checksum changed: {version}")
                    continue
                connection.execute("BEGIN")
                try:
                    connection.execute(sql)
                    connection.execute(
                        """INSERT INTO schema_migrations(version, checksum, applied_at)
                           VALUES (%s, %s, %s)""",
                        (version, checksum, utc_now()),
                    )
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
                applied.append(version)
        return applied

    @staticmethod
    def _table_exists(
        connection: psycopg.Connection[dict[str, Any]], name: str
    ) -> bool:
        return connection.execute(
            """SELECT 1 FROM information_schema.tables
               WHERE table_schema = 'seo_agent' AND table_name = %s""",
            (name,),
        ).fetchone() is not None

    def health(self) -> dict[str, Any]:
        with self.connect() as connection:
            if not self._table_exists(connection, "schema_migrations"):
                raise LedgerError("SEO ledger is not initialized")
            versions = [
                row["version"]
                for row in connection.execute(
                    "SELECT version FROM schema_migrations ORDER BY version"
                )
            ]
            running = connection.execute(
                "SELECT COUNT(*) AS count FROM cron_runs WHERE status='running'"
            ).fetchone()["count"]
        return {
            "status": "ok",
            "schema_version": SCHEMA_VERSION,
            "migrations": versions,
            "integrity_check": "ok",
            "foreign_key_violations": 0,
            "running_jobs": running,
            "database": "postgresql:seo_agent",
        }

    def start_run(self, job_name: str, schedule_token: str, *, stale_after_seconds: int = 3600) -> dict[str, str]:
        now = datetime.now(UTC)
        now_text = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        owner = secrets.token_urlsafe(24)
        run_id = str(uuid.uuid4())
        with self.transaction(immediate=True) as connection:
            stale_before = (now - timedelta(seconds=stale_after_seconds)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            stale = connection.execute(
                "SELECT id FROM cron_runs WHERE job_name=%s AND status='running' AND heartbeat_at <= %s",
                (job_name, stale_before),
            ).fetchall()
            for row in stale:
                connection.execute(
                    "UPDATE cron_runs SET status='failed', finished_at=%s, error_code='STALE_LEASE', error_detail='Scheduler lease expired' WHERE id=%s",
                    (now_text, row["id"]),
                )
                connection.execute(
                    """INSERT INTO run_logs(cron_run_id,log_text) VALUES (%s,%s)
                    ON CONFLICT(cron_run_id) DO NOTHING""",
                    (
                        row["id"],
                        "Codex exec не завершил run: Scheduler обнаружил просроченную аренду.",
                    ),
                )
                self._release_run_claims(connection, str(row["id"]))
            try:
                connection.execute(
                    "INSERT INTO cron_runs(id,job_name,schedule_token,status,owner_token,started_at,heartbeat_at) VALUES (%s,%s,%s,'running',%s,%s,%s)",
                    (run_id, job_name, schedule_token, owner, now_text, now_text),
                )
            except psycopg.IntegrityError as exc:
                raise LedgerError("Job already started for this schedule token or has an active lease") from exc
            self._audit(connection, "scheduler", "run.started", "cron_run", run_id, {"job_name": job_name})
        return {"run_id": run_id, "owner_token": owner, "started_at": now_text}

    def heartbeat(self, run_id: str, owner_token: str) -> None:
        with self.transaction(immediate=True) as connection:
            changed = connection.execute(
                "UPDATE cron_runs SET heartbeat_at=%s WHERE id=%s AND owner_token=%s AND status='running'",
                (utc_now(), run_id, owner_token),
            ).rowcount
            if changed != 1:
                raise LedgerError("Run lease is not active or ownership token is stale")

    def record_run_log(self, run_id: str, log_text: str) -> dict[str, str]:
        text = str(log_text).strip()
        if not 1 <= len(text) <= 4000:
            raise LedgerError("Run log must contain between 1 and 4000 characters")
        with self.transaction(immediate=True) as connection:
            active = connection.execute(
                "SELECT 1 FROM cron_runs WHERE id=%s AND status='running'", (run_id,)
            ).fetchone()
            if not active:
                raise LedgerError("Cannot attach a log to an inactive run")
            if connection.execute(
                "SELECT 1 FROM run_logs WHERE cron_run_id=%s", (run_id,)
            ).fetchone():
                raise LedgerError("Run already has a log")
            connection.execute(
                "INSERT INTO run_logs(cron_run_id,log_text) VALUES (%s,%s)",
                (run_id, text),
            )
            self._audit(
                connection,
                "codex",
                "run.log_recorded",
                "cron_run",
                run_id,
                {},
            )
        return {"cron_run_id": run_id}

    def record_result(self, run_id: str, outcome: str, summary: str, artifact: Any) -> str:
        if outcome not in {"completed", "blocked", "skipped"}:
            raise LedgerError("Unsupported job outcome")
        if not summary.strip() or not isinstance(artifact, dict):
            raise LedgerError("Job result requires a summary and artifact object")
        if outcome == "completed" and not artifact:
            raise LedgerError("Completed job result requires a durable artifact reference")
        result_id = str(uuid.uuid4())
        with self.transaction(immediate=True) as connection:
            active = connection.execute(
                "SELECT 1 FROM cron_runs WHERE id=%s AND status='running'", (run_id,)
            ).fetchone()
            if not active:
                raise LedgerError("Cannot attach a result to an inactive run")
            connection.execute(
                "INSERT INTO job_results(id,cron_run_id,outcome,summary,artifact_json,created_at) VALUES (%s,%s,%s,%s,%s,%s)",
                (result_id, run_id, outcome, summary.strip(), canonical_json(artifact), utc_now()),
            )
            self._audit(connection, "codex", "result.recorded", "cron_run", run_id, {"outcome": outcome})
        return result_id

    def finish_run(self, run_id: str, owner_token: str, *, failed_error: str | None = None) -> str:
        with self.transaction(immediate=True) as connection:
            row = connection.execute(
                "SELECT outcome,summary FROM job_results WHERE cron_run_id=%s", (run_id,)
            ).fetchone()
            if failed_error:
                fallback_log = (
                    "Codex exec не записал отдельный лог. Ошибка запуска: "
                    + failed_error[:3000]
                )
            elif row:
                fallback_log = (
                    "Codex exec не записал отдельный лог. Итог: "
                    + str(row["summary"])[:3000]
                )
            else:
                fallback_log = (
                    "Codex exec не записал отдельный лог и завершился без job_result."
                )
            connection.execute(
                """INSERT INTO run_logs(cron_run_id,log_text) VALUES (%s,%s)
                ON CONFLICT(cron_run_id) DO NOTHING""",
                (run_id, fallback_log),
            )
            outstanding_claims = sum(
                int(
                    connection.execute(
                        f"SELECT COUNT(*) AS count FROM {table} WHERE claim_run_id=%s AND status=%s",
                        (run_id, status),
                    ).fetchone()["count"]
                )
                for table, status in (
                    ("keyword_clusters", "claimed"),
                    ("article_drafts", "publishing"),
                    ("optimization_actions", "claimed"),
                    ("distribution_items", "publishing"),
                )
            )
            outstanding_claims += int(
                connection.execute(
                    """SELECT COUNT(*) AS count FROM article_drafts
                    WHERE claim_run_id=%s AND status='published'""",
                    (run_id,),
                ).fetchone()["count"]
            )
            if failed_error:
                status, outcome, error_code, error_detail = "failed", "failed", "AGENT_EXEC_FAILED", failed_error[:4000]
            elif row and row["outcome"] == "completed" and outstanding_claims:
                status, outcome, error_code, error_detail = (
                    "failed",
                    "failed",
                    "CLAIM_UNFINISHED",
                    f"Agent left {outstanding_claims} claimed entities unfinished",
                )
            elif row:
                outcome = str(row["outcome"])
                status, error_code, error_detail = outcome, None, None
            else:
                status, outcome, error_code, error_detail = "failed", "failed", "RESULT_MISSING", "Agent exited without one durable job_result"
            changed = connection.execute(
                "UPDATE cron_runs SET status=%s, outcome=%s, finished_at=%s, error_code=%s, error_detail=%s WHERE id=%s AND owner_token=%s AND status='running'",
                (status, outcome, utc_now(), error_code, error_detail, run_id, owner_token),
            ).rowcount
            if changed != 1:
                raise LedgerError("Run lease is not active or ownership token is stale")
            self._release_run_claims(connection, run_id)
            self._audit(connection, "scheduler", "run.finished", "cron_run", run_id, {"status": status})
        return status

    def _release_run_claims(
        self, connection: psycopg.Connection[dict[str, Any]], run_id: str
    ) -> int:
        now = utc_now()
        released = connection.execute(
            """UPDATE keyword_clusters
            SET status='ready',claim_token=NULL,claim_expires_at=NULL,claim_run_id=NULL,updated_at=%s
            WHERE claim_run_id=%s AND status='claimed'""",
            (now, run_id),
        ).rowcount
        released += connection.execute(
            """UPDATE article_drafts
            SET status='approved',claim_token=NULL,claim_expires_at=NULL,claim_run_id=NULL,updated_at=%s
            WHERE claim_run_id=%s AND status='publishing'""",
            (now, run_id),
        ).rowcount
        released += connection.execute(
            """UPDATE article_drafts
            SET claim_token=NULL,claim_expires_at=NULL,claim_run_id=NULL,updated_at=%s
            WHERE claim_run_id=%s AND status='published'""",
            (now, run_id),
        ).rowcount
        released += connection.execute(
            """UPDATE optimization_actions
            SET status='open',claim_token=NULL,claim_expires_at=NULL,claim_run_id=NULL
            WHERE claim_run_id=%s AND status='claimed'""",
            (run_id,),
        ).rowcount
        released += connection.execute(
            """UPDATE distribution_items
            SET status='approved',claim_token=NULL,claim_expires_at=NULL,claim_run_id=NULL,updated_at=%s
            WHERE claim_run_id=%s AND status='publishing'""",
            (now, run_id),
        ).rowcount
        if released:
            self._audit(
                connection,
                "scheduler",
                "claims.released",
                "cron_run",
                run_id,
                {"count": released},
            )
        return released

    def claim(self, entity: str, *, lease_seconds: int = 3900) -> dict[str, Any] | None:
        if not 30 <= lease_seconds <= 86_400:
            raise LedgerError("Claim lease must be between 30 and 86400 seconds")
        contracts = {
            "cluster": ("keyword_clusters", "status IN ('ready','claimed')", "priority_score DESC, created_at ASC", "claimed"),
            "draft": (
                "article_drafts",
                """status IN ('approved','publishing')
                OR (
                  status='published'
                  AND EXISTS (
                    SELECT 1 FROM publications site
                    WHERE site.draft_id=article_drafts.id
                      AND site.target='site' AND site.status='verified'
                      AND site.content_hash=article_drafts.content_hash
                      AND (
                        (SELECT COUNT(*) FROM distribution_items item
                         WHERE item.source_publication_id=site.id
                           AND item.platform='vk') < 1
                        OR
                        (SELECT COUNT(*) FROM distribution_items item
                         WHERE item.source_publication_id=site.id
                           AND item.platform='pinterest') < 10
                      )
                  )
                )""",
                "approved_at ASC",
                "publishing",
            ),
            "dzen-article": (
                "article_drafts",
                """status='published'
                AND EXISTS (
                  SELECT 1 FROM publications site
                  WHERE site.draft_id=article_drafts.id
                    AND site.target='site' AND site.status='verified'
                )
                AND (
                  NOT EXISTS (
                    SELECT 1 FROM publications dzen
                    WHERE dzen.draft_id=article_drafts.id
                      AND dzen.target='dzen' AND dzen.status='verified'
                  )
                  OR EXISTS (
                    SELECT 1 FROM publications dzen
                    WHERE dzen.draft_id=article_drafts.id
                      AND dzen.target='dzen' AND dzen.status='verified'
                      AND COALESCE(
                        dzen.evidence_json::jsonb #>> '{checks,cover_present}',
                        'false'
                      ) <> 'true'
                  )
                )""",
                "updated_at ASC",
                "published",
            ),
            "action": ("optimization_actions", "status IN ('open','claimed')", "priority_score DESC, created_at ASC", "claimed"),
            "vk-post": ("distribution_items", "platform='vk' AND status IN ('approved','publishing')", "created_at ASC", "publishing"),
            "pinterest-pin": ("distribution_items", "platform='pinterest' AND status IN ('approved','publishing')", "created_at ASC", "publishing"),
        }
        if entity not in contracts:
            raise LedgerError("Unsupported claim entity")
        table, predicate, order_by, next_status = contracts[entity]
        token = secrets.token_urlsafe(24)
        run_id = os.environ.get("VEDICWAY_SEO_RUN_ID", "").strip() or None
        expires = (datetime.now(UTC) + timedelta(seconds=lease_seconds)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        now = utc_now()
        with self.transaction(immediate=True) as connection:
            if run_id:
                run = connection.execute(
                    "SELECT job_name FROM cron_runs WHERE id=%s AND status='running'", (run_id,)
                ).fetchone()
                if not run:
                    raise LedgerError("VEDICWAY_SEO_RUN_ID does not identify an active run")
                allowed_claims = {
                    "article_content_production": {"cluster"},
                    "article_site_publish": {"draft"},
                    "dzen_daily_publish": {"dzen-article"},
                    "article_optimization": {"action", "draft"},
                    "vk_daily_publish": {"vk-post"},
                    "pinterest_daily_publish": {"pinterest-pin"},
                }
                if entity not in allowed_claims.get(str(run["job_name"]), set()):
                    raise LedgerError(
                        f"Job {run['job_name']} is not allowed to claim {entity}"
                    )
            row = connection.execute(
                f"SELECT * FROM {table} WHERE ({predicate}) AND (claim_expires_at IS NULL OR claim_expires_at < %s) ORDER BY {order_by} LIMIT 1",
                (now,),
            ).fetchone()
            if not row:
                return None
            claimed_status = (
                str(row["status"])
                if entity == "draft" and row["status"] == "published"
                else next_status
            )
            connection.execute(
                f"UPDATE {table} SET status=%s, claim_token=%s, claim_expires_at=%s, claim_run_id=%s WHERE id=%s",
                (claimed_status, token, expires, run_id, row["id"]),
            )
            self._audit(connection, "codex", f"{entity}.claimed", entity, row["id"], {"expires_at": expires})
            result = dict(row)
            if entity == "cluster":
                query_rows = connection.execute(
                    """SELECT q.id,q.phrase,q.region_id,q.source,q.intent,
                    q.metrics_json,q.observed_at,q.raw_response_id,cq.is_primary
                    FROM cluster_queries cq
                    JOIN keyword_queries q ON q.id=cq.query_id
                    WHERE cq.cluster_id=%s
                    ORDER BY cq.is_primary DESC,q.observed_at DESC,q.id ASC""",
                    (row["id"],),
                ).fetchall()
                queries: list[dict[str, Any]] = []
                for query_row in query_rows:
                    snapshots = connection.execute(
                        """SELECT id,region_id,requested_at,result_json,checksum,
                        raw_response_id
                        FROM serp_snapshots
                        WHERE query_id=%s
                        ORDER BY requested_at DESC,id ASC""",
                        (query_row["id"],),
                    ).fetchall()
                    query = {
                        "id": str(query_row["id"]),
                        "phrase": str(query_row["phrase"]),
                        "region_id": str(query_row["region_id"]),
                        "source": str(query_row["source"]),
                        "intent": query_row["intent"],
                        "metrics": json.loads(str(query_row["metrics_json"])),
                        "observed_at": str(query_row["observed_at"]),
                        "raw_response_id": query_row["raw_response_id"],
                        "is_primary": bool(query_row["is_primary"]),
                        "serp_snapshots": [
                            {
                                "id": str(snapshot["id"]),
                                "region_id": str(snapshot["region_id"]),
                                "requested_at": str(snapshot["requested_at"]),
                                "results": json.loads(str(snapshot["result_json"])),
                                "checksum": str(snapshot["checksum"]),
                                "raw_response_id": snapshot["raw_response_id"],
                            }
                            for snapshot in snapshots
                        ],
                    }
                    queries.append(query)
                primary_query = next(
                    (query for query in queries if query["is_primary"]), None
                )
                result["queries"] = queries
                result["primary_query"] = primary_query
            elif entity == "draft":
                media = connection.execute(
                    """SELECT id,purpose,local_path,alt_text,title,caption,
                    source_kind,source_url,license_note,checksum,public_url,
                    distribution_role,width,height
                    FROM article_media
                    WHERE draft_id=%s
                    ORDER BY CASE purpose WHEN 'cover' THEN 0 ELSE 1 END,created_at,id""",
                    (row["id"],),
                ).fetchall()
                result["media"] = [dict(item) for item in media]
                if row["status"] == "published":
                    site = connection.execute(
                        """SELECT id,public_url FROM publications
                        WHERE draft_id=%s AND target='site' AND status='verified'
                          AND content_hash=%s""",
                        (row["id"], row["content_hash"]),
                    ).fetchone()
                    if not site:
                        raise LedgerError(
                            "Distribution recovery lost its verified site publication"
                        )
                    counts = {"vk": 0, "pinterest": 0}
                    for count_row in connection.execute(
                        """SELECT platform,COUNT(*) AS count
                        FROM distribution_items WHERE source_publication_id=%s
                        GROUP BY platform""",
                        (site["id"],),
                    ):
                        counts[str(count_row["platform"])] = int(count_row["count"])
                    existing = connection.execute(
                        """SELECT id,platform,media_id,status,title
                        FROM distribution_items WHERE source_publication_id=%s
                        ORDER BY platform,created_at,id""",
                        (site["id"],),
                    ).fetchall()
                    result.update(
                        {
                            "recovery_mode": "missing_distribution",
                            "site_publication_id": str(site["id"]),
                            "site_public_url": str(site["public_url"]),
                            "distribution_counts": counts,
                            "distribution_items": [dict(item) for item in existing],
                        }
                    )
            elif entity == "action":
                details = connection.execute(
                    """SELECT p.draft_id,p.public_url,p.content_hash AS published_content_hash,
                    p.request_hash AS published_request_hash,d.brief_id,d.slug,d.title,d.excerpt,
                    d.content_markdown,d.seo_title,d.meta_description,d.focus_keyphrase,
                    d.category,d.author_name
                    FROM optimization_actions a
                    JOIN publications p ON p.id=a.publication_id
                    JOIN article_drafts d ON d.id=p.draft_id
                    WHERE a.id=%s""",
                    (row["id"],),
                ).fetchone()
                if not details:
                    raise LedgerError("Optimization action lost its publication or draft")
                result.update(dict(details))
            elif entity == "dzen-article":
                site = connection.execute(
                    """SELECT id AS site_publication_id,public_url AS site_public_url,
                    request_hash AS site_request_hash
                    FROM publications
                    WHERE draft_id=%s AND target='site' AND status='verified'""",
                    (row["id"],),
                ).fetchone()
                dzen = connection.execute(
                    """SELECT id,public_url,external_id,evidence_json
                    FROM publications
                    WHERE draft_id=%s AND target='dzen' AND status='verified'""",
                    (row["id"],),
                ).fetchone()
                media = connection.execute(
                    """SELECT id,purpose,local_path,alt_text,caption,public_url,width,height
                    FROM article_media
                    WHERE draft_id=%s AND public_url IS NOT NULL
                      AND distribution_role IS NULL
                    ORDER BY CASE purpose WHEN 'cover' THEN 0 ELSE 1 END,created_at""",
                    (row["id"],),
                ).fetchall()
                if not site:
                    raise LedgerError("Dzen article lost its verified site publication")
                result.update(dict(site))
                result["media"] = [dict(item) for item in media]
                if dzen:
                    result.update(
                        {
                            "recovery_mode": "missing_cover",
                            "existing_dzen_publication_id": str(dzen["id"]),
                            "existing_dzen_public_url": str(dzen["public_url"]),
                            "existing_dzen_external_id": dzen["external_id"],
                        }
                    )
            result.update(
                {
                    "claim_token": token,
                    "claim_expires_at": expires,
                    "claim_run_id": run_id,
                    "status": claimed_status,
                }
            )
            return result

    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        with self.connect() as connection:
            for table in (
                "cron_runs", "source_documents", "keyword_queries", "keyword_clusters",
                "content_briefs", "article_drafts", "publications", "optimization_actions",
                "distribution_items", "distribution_publications", "run_logs",
            ):
                counts[table] = int(
                    connection.execute(
                        f"SELECT COUNT(*) AS count FROM {table}"
                    ).fetchone()["count"]
                )
            recent = [dict(row) for row in connection.execute(
                "SELECT id,job_name,status,started_at,finished_at,error_code FROM cron_runs ORDER BY started_at DESC LIMIT 10"
            )]
        return {"counts": counts, "recent_runs": recent}

    def due_lifecycle(self, *, limit: int = 25) -> list[dict[str, Any]]:
        if not 1 <= limit <= 100:
            raise LedgerError("Lifecycle queue limit must be between 1 and 100")
        run_id = os.environ.get("VEDICWAY_SEO_RUN_ID", "").strip()
        if not run_id:
            raise LedgerError("VEDICWAY_SEO_RUN_ID is required")
        with self.connect() as connection:
            run = connection.execute(
                "SELECT job_name FROM cron_runs WHERE id=%s AND status='running'",
                (run_id,),
            ).fetchone()
            if not run or str(run["job_name"]) != "article_lifecycle_review":
                raise LedgerError(
                    "Only article_lifecycle_review may read the lifecycle queue"
                )
            rows = connection.execute(
                """SELECT id,draft_id,target,status,public_url,content_hash,
                request_hash,published_at,verified_at
                FROM v_due_lifecycle
                ORDER BY published_at ASC, id ASC
                LIMIT %s""",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def write_record(self, record_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        handlers = {
            "source-document": self._record_source_document,
            "tool-response": self._record_tool_response,
            "query": self._record_query,
            "serp-snapshot": self._record_serp_snapshot,
            "cluster": self._record_cluster,
            "brief": self._record_brief,
            "draft": self._record_draft,
            "draft-quality": self._record_draft_quality,
            "media": self._record_media,
            "publication-attempt": self._record_publication_attempt,
            "publication": self._record_publication,
            "performance": self._record_performance,
            "action": self._record_action,
            "action-result": self._record_action_result,
            "distribution-item": self._record_distribution_item,
            "distribution-attempt": self._record_distribution_attempt,
            "distribution-publication": self._record_distribution_publication,
        }
        if record_type not in handlers:
            raise LedgerError(f"Unsupported record type: {record_type}")
        return handlers[record_type](payload)

    @staticmethod
    def _required(payload: dict[str, Any], *names: str) -> None:
        missing = [
            name
            for name in names
            if payload.get(name) is None or payload.get(name) == ""
        ]
        if missing:
            raise LedgerError("Missing record fields: " + ", ".join(missing))

    def _record_source_document(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._required(payload, "source_kind", "source_key", "checksum")
        source_kind = str(payload["source_kind"])
        status = str(payload.get("status", "active"))
        if source_kind not in {"web", "mcp", "repository", "editorial"}:
            raise LedgerError("Unsupported source document kind")
        if status not in {"active", "stale", "rejected"}:
            raise LedgerError("Unsupported source document status")
        record_id = str(payload.get("id") or uuid.uuid4())
        body = payload.get("payload", {})
        with self.transaction(immediate=True) as connection:
            row = connection.execute(
                "SELECT id FROM source_documents WHERE source_kind=%s AND source_key=%s AND checksum=%s",
                (source_kind, payload["source_key"], payload["checksum"]),
            ).fetchone()
            if row:
                record_id = str(row["id"])
            else:
                connection.execute(
                    "INSERT INTO source_documents(id,source_kind,source_key,url,status,checksum,retrieved_at,payload_json) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (record_id, source_kind, payload["source_key"], payload.get("url"), status, payload["checksum"], payload.get("retrieved_at", utc_now()), canonical_json(body)),
                )
            self._audit(connection, "codex", "source.recorded", "source_document", record_id, {"source_key": payload["source_key"]})
        return {"id": record_id}

    def _record_tool_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._required(payload, "provider", "tool_name", "request_hash", "response")
        provider = normalize_tool_provider(payload["provider"])
        response = normalize_tool_response(payload["response"])
        run_id = str(payload.get("cron_run_id") or os.environ.get("VEDICWAY_SEO_RUN_ID", ""))
        if not run_id:
            raise LedgerError("cron_run_id or VEDICWAY_SEO_RUN_ID is required")
        record_id = str(payload.get("id") or uuid.uuid4())
        with self.transaction(immediate=True) as connection:
            if not connection.execute(
                "SELECT 1 FROM cron_runs WHERE id=%s AND status='running'", (run_id,)
            ).fetchone():
                raise LedgerError("Tool response requires an active cron run")
            connection.execute(
                "INSERT INTO raw_tool_responses(id,cron_run_id,provider,tool_name,request_hash,response_json,observed_at,expires_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (record_id, run_id, provider, payload["tool_name"], payload["request_hash"], canonical_json(response), payload.get("observed_at", utc_now()), payload.get("expires_at")),
            )
        return {"id": record_id}

    def _record_query(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._required(payload, "phrase", "region_id", "source")
        source = str(payload["source"])
        intent = payload.get("intent")
        if source not in {"wordstat", "webmaster", "metrika", "seed"}:
            raise LedgerError("Unsupported query source")
        if intent not in {None, "informational", "commercial", "navigational"}:
            raise LedgerError("Unsupported query intent")
        record_id = str(payload.get("id") or uuid.uuid4())
        phrase = str(payload["phrase"]).strip()
        region_id = str(payload["region_id"])
        observed_at = str(payload.get("observed_at") or utc_now())
        raw_response_id = payload.get("raw_response_id")
        if source != "seed" and not raw_response_id:
            raise LedgerError("Observed query requires its raw tool response")
        with self.transaction(immediate=True) as connection:
            if source != "seed":
                raw = connection.execute(
                    "SELECT provider FROM raw_tool_responses WHERE id=%s",
                    (raw_response_id,),
                ).fetchone()
                if not raw or raw["provider"] != source:
                    raise LedgerError("Query source differs from its raw tool response")
            row = connection.execute(
                "SELECT id FROM keyword_queries WHERE phrase=%s AND region_id=%s AND source=%s AND observed_at=%s",
                (phrase, region_id, source, observed_at),
            ).fetchone()
            if row:
                record_id = str(row["id"])
                connection.execute(
                    "UPDATE keyword_queries SET raw_response_id=%s WHERE id=%s",
                    (raw_response_id, record_id),
                )
            else:
                connection.execute(
                    "INSERT INTO keyword_queries(id,phrase,region_id,source,intent,metrics_json,observed_at,raw_response_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (record_id, phrase, region_id, source, intent, canonical_json(payload.get("metrics", {})), observed_at, raw_response_id),
                )
        return {"id": record_id}

    def _record_serp_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._required(payload, "query_id", "region_id", "results", "raw_response_id")
        results = payload["results"]
        if not isinstance(results, list) or not results:
            raise LedgerError("SERP snapshot requires a non-empty results array")
        checksum = hashlib.sha256(canonical_json(results).encode("utf-8")).hexdigest()
        requested_at = str(payload.get("requested_at") or utc_now())
        record_id = str(payload.get("id") or uuid.uuid4())
        with self.transaction(immediate=True) as connection:
            raw = connection.execute(
                "SELECT provider FROM raw_tool_responses WHERE id=%s",
                (payload["raw_response_id"],),
            ).fetchone()
            if not raw or raw["provider"] != "yandex-search":
                raise LedgerError("SERP snapshot requires a Yandex Search raw response")
            query = connection.execute(
                "SELECT region_id FROM keyword_queries WHERE id=%s", (payload["query_id"],)
            ).fetchone()
            if not query or str(query["region_id"]) != str(payload["region_id"]):
                raise LedgerError("SERP snapshot query and region do not match")
            existing = connection.execute(
                "SELECT id,checksum FROM serp_snapshots WHERE query_id=%s AND requested_at=%s",
                (payload["query_id"], requested_at),
            ).fetchone()
            if existing:
                if not secrets.compare_digest(str(existing["checksum"]), checksum):
                    raise LedgerError("Existing SERP snapshot has different results")
                record_id = str(existing["id"])
            else:
                connection.execute(
                    "INSERT INTO serp_snapshots(id,query_id,region_id,requested_at,result_json,checksum,raw_response_id) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (
                        record_id,
                        payload["query_id"],
                        str(payload["region_id"]),
                        requested_at,
                        canonical_json(results),
                        checksum,
                        payload["raw_response_id"],
                    ),
                )
        return {"id": record_id, "checksum": checksum}

    def _record_cluster(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._required(payload, "slug", "title", "intent")
        status = str(payload.get("status", "candidate"))
        if status not in {"candidate", "ready", "rejected"}:
            raise LedgerError("A planner may create only candidate, ready or rejected clusters")
        query_ids = list(dict.fromkeys(str(value) for value in payload.get("query_ids", [])))
        primary_query_id = payload.get("primary_query_id")
        if primary_query_id is not None and str(primary_query_id) not in query_ids:
            raise LedgerError("primary_query_id must belong to query_ids")
        if status == "ready" and (not query_ids or primary_query_id is None):
            raise LedgerError("Ready cluster requires query_ids and one primary_query_id")
        record_id = str(payload.get("id") or uuid.uuid4())
        now = utc_now()
        with self.transaction(immediate=True) as connection:
            if status == "ready":
                provenance = connection.execute(
                    """SELECT q.source,q.raw_response_id,
                    EXISTS(
                        SELECT 1 FROM serp_snapshots s
                        JOIN raw_tool_responses r ON r.id=s.raw_response_id
                        WHERE s.query_id=q.id AND r.provider='yandex-search'
                    ) AS has_serp
                    FROM keyword_queries q WHERE q.id=%s""",
                    (str(primary_query_id),),
                ).fetchone()
                if (
                    not provenance
                    or provenance["source"] != "wordstat"
                    or not provenance["raw_response_id"]
                ):
                    raise LedgerError(
                        "Ready cluster requires a Wordstat primary query with raw provenance"
                    )
                if provenance["has_serp"] is not True:
                    raise LedgerError(
                        "Ready cluster requires a SERP snapshot for its Wordstat primary query"
                    )
            connection.execute(
                """INSERT INTO keyword_clusters(id,slug,title,intent,status,priority_score,rationale,created_at,updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(slug) DO UPDATE SET
                  title=excluded.title, intent=excluded.intent, priority_score=excluded.priority_score,
                  rationale=excluded.rationale, updated_at=excluded.updated_at,
                  status=CASE WHEN keyword_clusters.status IN ('claimed','briefed','published')
                    THEN keyword_clusters.status ELSE excluded.status END""",
                (record_id, payload["slug"], payload["title"], payload["intent"], status, float(payload.get("priority_score", 0)), payload.get("rationale", ""), now, now),
            )
            row = connection.execute("SELECT id FROM keyword_clusters WHERE slug=%s", (payload["slug"],)).fetchone()
            record_id = str(row["id"])
            if "query_ids" in payload:
                connection.execute("DELETE FROM cluster_queries WHERE cluster_id=%s", (record_id,))
            for query_id in query_ids:
                connection.execute(
                    "INSERT INTO cluster_queries(cluster_id,query_id,is_primary) VALUES (%s,%s,%s)",
                    (record_id, query_id, int(query_id == str(primary_query_id))),
                )
        return {"id": record_id}

    def _record_brief(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._required(
            payload,
            "cluster_id",
            "claim_token",
            "title",
            "primary_query",
            "audience_problem",
            "search_intent",
        )
        outline = payload.get("outline")
        evidence = payload.get("evidence")
        internal_links = payload.get("internal_links")
        prohibited_claims = payload.get("prohibited_claims")
        if (
            not isinstance(outline, list)
            or not 4 <= len(outline) <= 8
            or not isinstance(evidence, list)
            or len(evidence) < 2
            or not isinstance(internal_links, list)
            or len(internal_links) < 2
            or not isinstance(prohibited_claims, list)
            or not prohibited_claims
        ):
            raise LedgerError("Approved brief requires 4-8 sections, evidence, internal links and prohibited claims")
        brief_contract = {
            "title": payload["title"],
            "primary_query": payload["primary_query"],
            "audience_problem": payload["audience_problem"],
            "search_intent": payload["search_intent"],
            "outline": outline,
            "evidence": evidence,
            "internal_links": internal_links,
            "prohibited_claims": prohibited_claims,
        }
        checksum = hashlib.sha256(canonical_json(brief_contract).encode("utf-8")).hexdigest()
        record_id = str(payload.get("id") or uuid.uuid4())
        now = utc_now()
        with self.transaction(immediate=True) as connection:
            changed = connection.execute(
                "UPDATE keyword_clusters SET status='briefed',claim_token=NULL,claim_expires_at=NULL,claim_run_id=NULL,updated_at=%s WHERE id=%s AND status='claimed' AND claim_token=%s AND claim_expires_at>=%s",
                (now, payload["cluster_id"], payload["claim_token"], now),
            ).rowcount
            if changed != 1:
                raise LedgerError("Cluster claim is stale or does not belong to this run")
            connection.execute(
                "INSERT INTO content_briefs(id,cluster_id,status,title,primary_query,audience_problem,search_intent,outline_json,evidence_json,internal_links_json,prohibited_claims_json,checksum,created_at,approved_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (record_id, payload["cluster_id"], "approved", payload["title"], payload["primary_query"], payload["audience_problem"], payload["search_intent"], canonical_json(outline), canonical_json(evidence), canonical_json(internal_links), canonical_json(prohibited_claims), checksum, now, now),
            )
        return {"id": record_id, "checksum": checksum}

    def _record_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._required(
            payload,
            "brief_id",
            "slug",
            "title",
            "excerpt",
            "content_markdown",
            "seo_title",
            "meta_description",
            "focus_keyphrase",
            "category",
        )
        content = str(payload["content_markdown"]).strip()
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if payload.get("status", "draft") not in {"draft", "editing"}:
            raise LedgerError("Draft writer cannot set an approved or terminal status")
        record_id = str(payload.get("id") or uuid.uuid4())
        now = utc_now()
        with self.transaction(immediate=True) as connection:
            brief = connection.execute("SELECT status FROM content_briefs WHERE id=%s", (payload["brief_id"],)).fetchone()
            if not brief or brief["status"] not in {"approved", "consumed"}:
                raise LedgerError("Draft requires an approved brief")
            existing = connection.execute(
                "SELECT id,brief_id,status FROM article_drafts WHERE slug=%s", (payload["slug"],)
            ).fetchone()
            if existing and existing["brief_id"] != payload["brief_id"]:
                raise LedgerError("A published slug cannot be reassigned to another brief")
            if existing and existing["status"] == "publishing":
                raise LedgerError("A draft cannot change while a publication lease is active")
            if existing and existing["status"] == "published":
                self._required(payload, "action_id", "action_claim_token")
                action = connection.execute(
                    """SELECT 1 FROM optimization_actions a
                    JOIN publications p ON p.id=a.publication_id
                    WHERE a.id=%s AND a.claim_token=%s AND a.status='claimed'
                      AND a.claim_expires_at>=%s AND p.draft_id=%s""",
                    (payload["action_id"], payload["action_claim_token"], now, existing["id"]),
                ).fetchone()
                if not action:
                    raise LedgerError("Published draft changes require an active optimization action")
            connection.execute("UPDATE content_briefs SET status='consumed' WHERE id=%s", (payload["brief_id"],))
            connection.execute(
                """INSERT INTO article_drafts(id,brief_id,slug,status,title,excerpt,content_markdown,seo_title,meta_description,focus_keyphrase,category,author_name,content_hash,created_at,updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(slug) DO UPDATE SET title=excluded.title,excerpt=excluded.excerpt,
                content_markdown=excluded.content_markdown,seo_title=excluded.seo_title,
                meta_description=excluded.meta_description,focus_keyphrase=excluded.focus_keyphrase,
                category=excluded.category,author_name=excluded.author_name,content_hash=excluded.content_hash,
                updated_at=excluded.updated_at,status='editing',quality_report_json=NULL,approved_at=NULL""",
                (record_id, payload["brief_id"], payload["slug"], payload.get("status", "draft"), payload["title"], payload["excerpt"], content, payload["seo_title"], payload["meta_description"], payload["focus_keyphrase"], payload["category"], payload.get("author_name", "Редакция VedicWay"), content_hash, now, now),
            )
            row = connection.execute("SELECT id FROM article_drafts WHERE slug=%s", (payload["slug"],)).fetchone()
            record_id = str(row["id"])
        return {"id": record_id, "content_hash": content_hash}

    def _record_draft_quality(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._required(payload, "draft_id", "passed", "report")
        if not isinstance(payload["passed"], bool) or not isinstance(payload["report"], dict):
            raise LedgerError("Draft quality requires a boolean passed value and report object")
        if payload["report"].get("passed") is not payload["passed"]:
            raise LedgerError("Draft quality outcome differs from the deterministic report")
        manual = payload["report"].get("manual_checks")
        if payload["passed"] and (
            not isinstance(manual, dict)
            or set(manual) != MANUAL_QUALITY_CHECKS
            or not all(manual[name] is True for name in MANUAL_QUALITY_CHECKS)
        ):
            raise LedgerError("Passed quality report requires all manual editorial checks")
        status = "approved" if payload["passed"] is True else "quality_failed"
        now = utc_now()
        with self.transaction(immediate=True) as connection:
            draft = connection.execute(
                "SELECT content_hash FROM article_drafts WHERE id=%s", (payload["draft_id"],)
            ).fetchone()
            if not draft or payload["report"].get("content_hash") != draft["content_hash"]:
                raise LedgerError("Quality report is not bound to the current draft content")
            changed = connection.execute(
                "UPDATE article_drafts SET status=%s,quality_report_json=%s,updated_at=%s,approved_at=%s WHERE id=%s AND status IN ('draft','editing','quality_failed','approved')",
                (status, canonical_json(payload["report"]), now, now if status == "approved" else None, payload["draft_id"]),
            ).rowcount
            if changed != 1:
                raise LedgerError("Draft is missing or already terminal")
        return {"id": payload["draft_id"], "status": status}

    def _record_media(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._required(payload, "draft_id", "purpose", "local_path", "alt_text", "source_kind", "license_note", "checksum")
        distribution_role = payload.get("distribution_role")
        if distribution_role not in {None, "pinterest"}:
            raise LedgerError("Article media has an unsupported distribution role")
        if distribution_role is not None and payload["purpose"] != "body":
            raise LedgerError("Distribution media must use the body purpose")
        source = Path(str(payload["local_path"]))
        if not source.is_absolute():
            source = self.data_dir / source
        source = source.expanduser().resolve()
        try:
            relative_path = source.relative_to(self.data_dir).as_posix()
        except ValueError as exc:
            raise LedgerError("Article media must stay inside VEDICWAY_SEO_DATA_DIR") from exc
        if not source.is_file():
            raise LedgerError("Article media file is missing")
        checksum = hashlib.sha256(source.read_bytes()).hexdigest()
        if not secrets.compare_digest(str(payload["checksum"]), checksum):
            raise LedgerError("Article media checksum does not match the local file")
        try:
            with Image.open(source) as image:
                width, height = image.size
                image.verify()
        except (UnidentifiedImageError, OSError) as exc:
            raise LedgerError("Article media is not a valid image") from exc
        if distribution_role == "pinterest" and (width, height) != (1000, 1500):
            raise LedgerError("Pinterest article media must be exactly 1000x1500")
        record_id = str(payload.get("id") or uuid.uuid4())
        with self.transaction(immediate=True) as connection:
            existing = connection.execute(
                "SELECT id FROM article_media WHERE draft_id=%s AND (purpose='cover' AND %s='cover' OR checksum=%s AND purpose=%s)",
                (payload["draft_id"], payload["purpose"], checksum, payload["purpose"]),
            ).fetchone()
            if existing:
                record_id = str(existing["id"])
                connection.execute(
                    "UPDATE article_media SET purpose=%s,local_path=%s,alt_text=%s,title=%s,caption=%s,source_kind=%s,source_url=%s,license_note=%s,checksum=%s,backend_media_id=%s,public_url=%s,distribution_role=%s,width=%s,height=%s WHERE id=%s",
                    (payload["purpose"], relative_path, payload["alt_text"], payload.get("title", ""), payload.get("caption", ""), payload["source_kind"], payload.get("source_url"), payload["license_note"], checksum, payload.get("backend_media_id"), payload.get("public_url"), distribution_role, width, height, record_id),
                )
            else:
                connection.execute(
                    "INSERT INTO article_media(id,draft_id,purpose,local_path,alt_text,title,caption,source_kind,source_url,license_note,checksum,backend_media_id,public_url,distribution_role,width,height,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (record_id, payload["draft_id"], payload["purpose"], relative_path, payload["alt_text"], payload.get("title", ""), payload.get("caption", ""), payload["source_kind"], payload.get("source_url"), payload["license_note"], checksum, payload.get("backend_media_id"), payload.get("public_url"), distribution_role, width, height, utc_now()),
                )
        return {"id": record_id}

    def _record_publication_attempt(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._required(payload, "draft_id", "target", "idempotency_key", "attempt_token", "status", "content_hash", "request_hash")
        if not re.fullmatch(r"[A-Za-z0-9._:-]{16,160}", str(payload["idempotency_key"])):
            raise LedgerError("Publication idempotency_key has an invalid format")
        if payload["status"] not in {"succeeded", "failed", "blocked"}:
            raise LedgerError("Publication attempt must record a terminal status")
        record_id = str(payload.get("id") or uuid.uuid4())
        now = utc_now()
        with self.transaction(immediate=True) as connection:
            draft = connection.execute(
                "SELECT status,content_hash,claim_token,claim_expires_at,claim_run_id FROM article_drafts WHERE id=%s",
                (payload["draft_id"],),
            ).fetchone()
            if not draft or draft["content_hash"] != payload["content_hash"]:
                raise LedgerError("Publication attempt does not match the current draft content")
            if payload["target"] == "site":
                self._required(payload, "claim_token")
                if (
                    draft["status"] not in {"publishing", "published"}
                    or draft["claim_token"] != payload["claim_token"]
                    or not draft["claim_expires_at"]
                    or draft["claim_expires_at"] < now
                ):
                    raise LedgerError("Site publication attempt requires the active draft claim")
            previous = connection.execute(
                "SELECT content_hash,request_hash FROM publication_attempts WHERE idempotency_key=%s LIMIT 1",
                (payload["idempotency_key"],),
            ).fetchone()
            if previous and (
                previous["content_hash"] != payload["content_hash"]
                or previous["request_hash"] != payload["request_hash"]
            ):
                raise LedgerError("An idempotency_key cannot be reused for different publication content")
            attempt_no = int(
                payload.get("attempt_no")
                or connection.execute(
                    """SELECT COALESCE(MAX(attempt_no), 0) + 1 AS next_attempt
                       FROM publication_attempts WHERE draft_id=%s AND target=%s""",
                    (payload["draft_id"], payload["target"]),
                ).fetchone()["next_attempt"]
            )
            connection.execute(
                "INSERT INTO publication_attempts(id,draft_id,target,attempt_no,idempotency_key,attempt_token,status,content_hash,request_hash,response_json,started_at,finished_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (record_id, payload["draft_id"], payload["target"], attempt_no, payload["idempotency_key"], payload["attempt_token"], payload["status"], payload["content_hash"], payload["request_hash"], canonical_json(payload.get("response", {})), payload.get("started_at", now), now),
            )
        return {"id": record_id, "attempt_no": attempt_no}

    def _record_publication(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._required(payload, "draft_id", "target", "public_url", "content_hash", "request_hash", "attempt_token", "evidence")
        status = str(payload.get("status", "verified"))
        if status not in {"published", "verified"}:
            raise LedgerError("Publication writer accepts only published or verified status")
        if not isinstance(payload["evidence"], dict):
            raise LedgerError("Publication evidence must be a JSON object")
        record_id = str(payload.get("id") or uuid.uuid4())
        now = utc_now()
        with self.transaction(immediate=True) as connection:
            draft = connection.execute(
                "SELECT brief_id,status,content_hash,claim_token,claim_expires_at,claim_run_id FROM article_drafts WHERE id=%s",
                (payload["draft_id"],),
            ).fetchone()
            if not draft or draft["content_hash"] != payload["content_hash"]:
                raise LedgerError("Publication evidence does not match an approved draft")
            attempt = connection.execute(
                "SELECT content_hash,request_hash FROM publication_attempts WHERE draft_id=%s AND target=%s AND attempt_token=%s AND status='succeeded'",
                (payload["draft_id"], payload["target"], payload["attempt_token"]),
            ).fetchone()
            if not attempt or attempt["content_hash"] != payload["content_hash"] or attempt["request_hash"] != payload["request_hash"]:
                raise LedgerError("A succeeded publication attempt is required before publication evidence")
            if payload["target"] == "site":
                self._required(payload, "claim_token")
                if (
                    draft["status"] not in {"publishing", "published"}
                    or draft["claim_token"] != payload["claim_token"]
                    or not draft["claim_expires_at"]
                    or draft["claim_expires_at"] < now
                ):
                    raise LedgerError("Site publication requires the active draft claim")
                required_checks = {
                    "canonical",
                    "article_schema",
                    "title",
                    "request_hash",
                    "sitemap",
                    "cover",
                    "all_media_public",
                }
                checks = payload["evidence"].get("checks")
                if not isinstance(checks, dict) or not required_checks.issubset(checks) or not all(
                    checks[name] is True for name in required_checks
                ):
                    raise LedgerError("Site publication evidence is incomplete")
            elif payload["target"] == "dzen":
                site = connection.execute(
                    "SELECT 1 FROM publications WHERE draft_id=%s AND target='site' AND status='verified' AND content_hash=%s",
                    (payload["draft_id"], payload["content_hash"]),
                ).fetchone()
                if not site:
                    raise LedgerError("Dzen evidence requires the matching verified site publication")
                required = {
                    "editor_persisted",
                    "public_url_verified",
                    "playwright_ui",
                    "cover_present",
                }
                checks = payload["evidence"].get("checks")
                if (
                    not isinstance(checks, dict)
                    or not required.issubset(checks)
                    or not all(checks[name] is True for name in required)
                ):
                    raise LedgerError(
                        "Dzen publication evidence is incomplete or cover is unverified"
                    )
            connection.execute(
                """INSERT INTO publications(id,draft_id,target,status,public_url,external_id,content_hash,request_hash,evidence_json,published_at,verified_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(draft_id,target) DO UPDATE SET
                  status=CASE WHEN publications.status='verified' THEN 'verified' ELSE excluded.status END,
                  public_url=excluded.public_url,external_id=excluded.external_id,
                  content_hash=excluded.content_hash,request_hash=excluded.request_hash,
                  evidence_json=excluded.evidence_json,
                  verified_at=COALESCE(excluded.verified_at,publications.verified_at)""",
                (record_id, payload["draft_id"], payload["target"], status, payload["public_url"], payload.get("external_id"), payload["content_hash"], payload["request_hash"], canonical_json(payload["evidence"]), payload.get("published_at", now), now if status == "verified" else None),
            )
            publication = connection.execute(
                "SELECT id FROM publications WHERE draft_id=%s AND target=%s",
                (payload["draft_id"], payload["target"]),
            ).fetchone()
            record_id = str(publication["id"])
            if payload["target"] == "site":
                connection.execute("UPDATE article_drafts SET status='published',claim_token=NULL,claim_expires_at=NULL,claim_run_id=NULL,updated_at=%s WHERE id=%s", (now, payload["draft_id"]))
                connection.execute("UPDATE keyword_clusters SET status='published',updated_at=%s WHERE id=(SELECT cluster_id FROM content_briefs WHERE id=%s)", (now, draft["brief_id"]))
            else:
                connection.execute(
                    """UPDATE article_drafts
                    SET claim_token=NULL,claim_expires_at=NULL,claim_run_id=NULL,updated_at=%s
                    WHERE id=%s""",
                    (now, payload["draft_id"]),
                )
        return {"id": record_id}

    def _record_performance(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._required(payload, "publication_id", "window_start", "window_end", "webmaster", "metrika")
        record_id = str(payload.get("id") or uuid.uuid4())
        with self.transaction(immediate=True) as connection:
            connection.execute(
                "INSERT INTO performance_snapshots(id,publication_id,window_start,window_end,webmaster_json,metrika_json,captured_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (record_id, payload["publication_id"], payload["window_start"], payload["window_end"], canonical_json(payload["webmaster"]), canonical_json(payload["metrika"]), payload.get("captured_at", utc_now())),
            )
        return {"id": record_id}

    def _record_action(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._required(payload, "publication_id", "action_type", "hypothesis", "success_metric", "evidence")
        record_id = str(payload.get("id") or uuid.uuid4())
        with self.transaction(immediate=True) as connection:
            publication = connection.execute(
                "SELECT request_hash FROM publications WHERE id=%s AND target='site' AND status='verified'",
                (payload["publication_id"],),
            ).fetchone()
            if not publication:
                raise LedgerError("Optimization action requires a verified site publication")
            connection.execute(
                "INSERT INTO optimization_actions(id,publication_id,action_type,status,priority_score,hypothesis,success_metric,evidence_json,baseline_request_hash,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (record_id, payload["publication_id"], payload["action_type"], "open", float(payload.get("priority_score", 0)), payload["hypothesis"], payload["success_metric"], canonical_json(payload["evidence"]), publication["request_hash"], utc_now()),
            )
        return {"id": record_id}

    def _record_action_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._required(payload, "action_id", "claim_token", "status", "evidence")
        status = str(payload["status"])
        if status not in {"completed", "rejected"} or not isinstance(payload["evidence"], dict):
            raise LedgerError("Action result must be completed or rejected with evidence")
        now = utc_now()
        with self.transaction(immediate=True) as connection:
            row = connection.execute(
                """SELECT a.action_type,a.baseline_request_hash,p.status AS publication_status,
                p.content_hash,p.request_hash,d.content_hash AS draft_content_hash
                FROM optimization_actions a
                JOIN publications p ON p.id=a.publication_id
                JOIN article_drafts d ON d.id=p.draft_id
                WHERE a.id=%s AND a.status='claimed' AND a.claim_token=%s AND a.claim_expires_at>=%s""",
                (payload["action_id"], payload["claim_token"], now),
            ).fetchone()
            if not row:
                raise LedgerError("Optimization action claim is stale or belongs to another run")
            mutation_types = {"rewrite", "expand", "internal_links", "title_test"}
            if status == "completed":
                if row["publication_status"] != "verified" or row["content_hash"] != row["draft_content_hash"]:
                    raise LedgerError("Completed action requires a verified current draft publication")
                if row["action_type"] in mutation_types and row["request_hash"] == row["baseline_request_hash"]:
                    raise LedgerError("Content-changing action did not produce a new published request hash")
            connection.execute(
                "UPDATE optimization_actions SET status=%s,result_evidence_json=%s,claim_token=NULL,claim_expires_at=NULL,claim_run_id=NULL,completed_at=%s WHERE id=%s",
                (status, canonical_json(payload["evidence"]), now, payload["action_id"]),
            )
            self._audit(connection, "codex", "action.finished", "optimization_action", payload["action_id"], {"status": status})
        return {"id": payload["action_id"], "status": status}

    def _record_distribution_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._required(
            payload,
            "source_publication_id",
            "platform",
            "kind",
            "title",
            "body",
            "target_url",
            "media_width",
            "media_height",
            "alt_text",
        )
        platform = str(payload["platform"])
        kind = str(payload["kind"])
        media_role = str(payload.get("media_role", ""))
        if platform == "pinterest" and not payload.get("media_id"):
            raise LedgerError("Pinterest distribution item requires an explicit media_id")
        if not payload.get("media_id") and media_role not in {"cover", "pinterest"}:
            raise LedgerError("Distribution item requires media_id or a supported media_role")
        if media_role and (
            (platform == "vk" and media_role != "cover")
            or (platform == "pinterest" and media_role != "pinterest")
        ):
            raise LedgerError("Distribution media role does not match its platform")
        if (platform, kind) not in {
            ("vk", "article_digest"),
            ("pinterest", "astrology_card"),
        }:
            raise LedgerError("Distribution kind does not match its platform")
        width = int(payload["media_width"])
        height = int(payload["media_height"])
        if platform == "pinterest" and (width, height) != (1000, 1500):
            raise LedgerError("Pinterest distribution media must be exactly 1000x1500")
        if not str(payload["target_url"]).startswith("https://vedicway.ru/blog/"):
            raise LedgerError("Distribution target must be a VedicWay blog URL")
        metadata = payload.get("metadata", {})
        if not isinstance(metadata, dict):
            raise LedgerError("Distribution metadata must be an object")
        content = {
            "platform": platform,
            "kind": kind,
            "title": str(payload["title"]).strip(),
            "body": str(payload["body"]).strip(),
            "target_url": str(payload["target_url"]),
            "media_role": media_role,
            "media_width": width,
            "media_height": height,
            "alt_text": str(payload["alt_text"]).strip(),
            "metadata": metadata,
        }
        if not content["title"] or not content["body"] or not content["alt_text"]:
            raise LedgerError("Distribution text fields cannot be blank")
        record_id = str(payload.get("id") or uuid.uuid4())
        now = utc_now()
        with self.transaction(immediate=True) as connection:
            if payload.get("media_id"):
                media_predicate = "m.id=%s"
                query_parameters = (
                    payload["media_id"],
                    payload["source_publication_id"],
                )
            else:
                media_predicate = (
                    "m.purpose='cover'"
                    if media_role == "cover"
                    else "m.distribution_role='pinterest'"
                )
                query_parameters = (payload["source_publication_id"],)
            source = connection.execute(
                f"""SELECT p.public_url,p.draft_id,m.id AS media_id,
                m.public_url AS media_public_url,m.width AS media_width,
                m.height AS media_height
                FROM publications p
                JOIN article_media m ON m.draft_id=p.draft_id AND {media_predicate}
                WHERE p.id=%s AND p.target='site' AND p.status='verified'""",
                query_parameters,
            ).fetchone()
            if not source:
                raise LedgerError(
                    "Distribution requires verified site publication media from the same draft"
                )
            if str(source["public_url"]) != content["target_url"]:
                raise LedgerError("Distribution target URL differs from its site publication")
            media_public_url = str(source["media_public_url"] or "")
            if not media_public_url.startswith("https://vedicway.ru/media/articles/"):
                raise LedgerError("Distribution media requires public VedicWay article media")
            if (source["media_width"], source["media_height"]) != (width, height):
                raise LedgerError("Declared dimensions differ from actual media dimensions")
            content["media_id"] = str(source["media_id"])
            content["media_width"] = int(source["media_width"])
            content["media_height"] = int(source["media_height"])
            content_hash = hashlib.sha256(
                canonical_json(content).encode("utf-8")
            ).hexdigest()
            existing = connection.execute(
                "SELECT id,status,content_hash FROM distribution_items WHERE platform=%s AND content_hash=%s",
                (platform, content_hash),
            ).fetchone()
            if existing:
                return dict(existing)
            connection.execute(
                """INSERT INTO distribution_items(
                id,source_publication_id,platform,kind,title,body,target_url,media_id,
                media_public_url,media_width,media_height,alt_text,metadata_json,
                content_hash,status,created_at,updated_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'approved',%s,%s)""",
                (
                    record_id,
                    payload["source_publication_id"],
                    platform,
                    kind,
                    content["title"],
                    content["body"],
                    content["target_url"],
                    source["media_id"],
                    media_public_url,
                    width,
                    height,
                    content["alt_text"],
                    canonical_json(metadata),
                    content_hash,
                    now,
                    now,
                ),
            )
            self._audit(
                connection,
                "codex",
                "distribution.prepared",
                "distribution_item",
                record_id,
                {"platform": platform},
            )
        return {"id": record_id, "status": "approved", "content_hash": content_hash}

    def _record_distribution_attempt(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._required(
            payload,
            "item_id",
            "claim_token",
            "attempt_token",
            "idempotency_key",
            "status",
            "request_hash",
            "response",
        )
        status = str(payload["status"])
        if status not in {"succeeded", "failed", "blocked"}:
            raise LedgerError("Distribution attempt must be terminal")
        if not isinstance(payload["response"], dict):
            raise LedgerError("Distribution response must be an object")
        if status == "succeeded" and (
            not payload.get("external_id") or not payload.get("external_url")
        ):
            raise LedgerError("Succeeded distribution attempt requires external evidence")
        record_id = str(payload.get("id") or uuid.uuid4())
        now = utc_now()
        with self.transaction(immediate=True) as connection:
            item = connection.execute(
                """SELECT platform,content_hash FROM distribution_items
                WHERE id=%s AND status='publishing' AND claim_token=%s
                  AND claim_expires_at>=%s""",
                (payload["item_id"], payload["claim_token"], now),
            ).fetchone()
            if not item:
                raise LedgerError("Distribution claim is stale or belongs to another run")
            if str(payload["idempotency_key"]) != str(item["content_hash"]):
                raise LedgerError("Distribution idempotency key must equal the content hash")
            attempt_no = int(
                connection.execute(
                    "SELECT COUNT(*) AS count FROM distribution_attempts WHERE item_id=%s",
                    (payload["item_id"],),
                ).fetchone()["count"]
            ) + 1
            connection.execute(
                """INSERT INTO distribution_attempts(
                id,item_id,platform,attempt_no,attempt_token,idempotency_key,status,
                request_hash,response_json,external_id,external_url,created_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    record_id,
                    payload["item_id"],
                    item["platform"],
                    attempt_no,
                    payload["attempt_token"],
                    payload["idempotency_key"],
                    status,
                    payload["request_hash"],
                    canonical_json(payload["response"]),
                    payload.get("external_id"),
                    payload.get("external_url"),
                    now,
                ),
            )
        return {"id": record_id, "status": status, "attempt_no": attempt_no}

    def _record_distribution_publication(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._required(
            payload,
            "item_id",
            "claim_token",
            "attempt_token",
            "request_hash",
            "external_id",
            "external_url",
            "evidence",
        )
        evidence = payload["evidence"]
        if not isinstance(evidence, dict) or evidence.get("external_state_verified") is not True:
            raise LedgerError("Distribution publication requires verified external state")
        if not str(payload["external_url"]).startswith("https://"):
            raise LedgerError("Distribution external URL must use HTTPS")
        record_id = str(payload.get("id") or uuid.uuid4())
        now = utc_now()
        with self.transaction(immediate=True) as connection:
            existing = connection.execute(
                "SELECT id,status FROM distribution_publications WHERE item_id=%s",
                (payload["item_id"],),
            ).fetchone()
            if existing:
                return dict(existing)
            item = connection.execute(
                """SELECT i.platform,i.content_hash,a.external_id,a.external_url,a.request_hash
                FROM distribution_items i
                JOIN distribution_attempts a ON a.item_id=i.id
                  AND a.attempt_token=%s AND a.status='succeeded'
                WHERE i.id=%s AND i.status='publishing' AND i.claim_token=%s
                  AND i.claim_expires_at>=%s""",
                (
                    payload["attempt_token"],
                    payload["item_id"],
                    payload["claim_token"],
                    now,
                ),
            ).fetchone()
            if not item:
                raise LedgerError("Verified distribution attempt or active claim is missing")
            if (
                str(item["request_hash"]) != str(payload["request_hash"])
                or str(item["external_id"]) != str(payload["external_id"])
                or str(item["external_url"]) != str(payload["external_url"])
            ):
                raise LedgerError("Distribution publication differs from its succeeded attempt")
            connection.execute(
                """INSERT INTO distribution_publications(
                id,item_id,platform,status,external_id,external_url,content_hash,
                request_hash,evidence_json,published_at
                ) VALUES (%s,%s,%s,'verified',%s,%s,%s,%s,%s,%s)""",
                (
                    record_id,
                    payload["item_id"],
                    item["platform"],
                    payload["external_id"],
                    payload["external_url"],
                    item["content_hash"],
                    payload["request_hash"],
                    canonical_json(evidence),
                    now,
                ),
            )
            connection.execute(
                """UPDATE distribution_items
                SET status='published',claim_token=NULL,claim_expires_at=NULL,
                    claim_run_id=NULL,published_at=%s,updated_at=%s
                WHERE id=%s""",
                (now, now, payload["item_id"]),
            )
            self._audit(
                connection,
                "codex",
                "distribution.verified",
                "distribution_item",
                payload["item_id"],
                {"platform": item["platform"], "external_id": payload["external_id"]},
            )
        return {"id": record_id, "status": "verified"}

    @staticmethod
    def _audit(
        connection: psycopg.Connection[dict[str, Any]],
        actor: str,
        action: str,
        entity_type: str,
        entity_id: str | None,
        detail: Any,
    ) -> None:
        connection.execute(
            "INSERT INTO audit_events(occurred_at,actor,action,entity_type,entity_id,detail_json) VALUES (%s,%s,%s,%s,%s,%s)",
            (utc_now(), actor, action, entity_type, entity_id, canonical_json(detail)),
        )
