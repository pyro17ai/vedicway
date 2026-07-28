from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.1.0"
MANUAL_QUALITY_CHECKS = {
    "brief_alignment",
    "evidence_verified",
    "originality_reviewed",
    "prohibited_claims_reviewed",
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class LedgerError(RuntimeError):
    pass


class AgentLedger:
    def __init__(self, path: str | Path | None = None, *, data_dir: str | Path | None = None) -> None:
        root = Path(data_dir or os.environ.get("VEDICWAY_SEO_DATA_DIR", Path.cwd() / ".data" / "seo-agent"))
        self.data_dir = root.expanduser().resolve()
        candidate = Path(path or os.environ.get("VEDICWAY_SEO_DB", self.data_dir / "vedicway_seo_agent.sqlite3"))
        if not candidate.is_absolute():
            candidate = self.data_dir / candidate
        self.path = candidate.expanduser().resolve()
        try:
            self.path.relative_to(self.data_dir)
        except ValueError as exc:
            raise LedgerError("SEO ledger must stay inside VEDICWAY_SEO_DATA_DIR") from exc
        self.migrations_dir = Path(__file__).with_name("migrations")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute("PRAGMA busy_timeout = 30000")
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            try:
                yield connection
            except Exception:
                connection.rollback()
                raise
            else:
                connection.commit()

    def initialize(self) -> list[str]:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        applied: list[str] = []
        with self.connect() as connection:
            existing = {
                row[0]: row[1]
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
                connection.executescript(sql)
                connection.execute(
                    "INSERT OR REPLACE INTO schema_migrations(version, checksum, applied_at) VALUES (?, ?, ?)",
                    (version, checksum, utc_now()),
                )
                connection.execute(f"PRAGMA user_version = {int(version.split('_', 1)[0])}")
                applied.append(version)
        return applied

    @staticmethod
    def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
        return connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone() is not None

    def health(self) -> dict[str, Any]:
        if not self.path.is_file():
            raise LedgerError("SEO ledger is not initialized")
        with self.connect() as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
            versions = [row[0] for row in connection.execute("SELECT version FROM schema_migrations ORDER BY version")]
            running = connection.execute("SELECT COUNT(*) FROM cron_runs WHERE status='running'").fetchone()[0]
        return {
            "status": "ok" if integrity == "ok" and not foreign_keys else "failed",
            "schema_version": SCHEMA_VERSION,
            "migrations": versions,
            "integrity_check": integrity,
            "foreign_key_violations": len(foreign_keys),
            "running_jobs": running,
            "database": str(self.path),
        }

    def start_run(self, job_name: str, schedule_token: str, *, stale_after_seconds: int = 3600) -> dict[str, str]:
        now = datetime.now(UTC)
        now_text = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        owner = secrets.token_urlsafe(24)
        run_id = str(uuid.uuid4())
        with self.transaction(immediate=True) as connection:
            stale_before = (now - timedelta(seconds=stale_after_seconds)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            stale = connection.execute(
                "SELECT id FROM cron_runs WHERE job_name=? AND status='running' AND heartbeat_at <= ?",
                (job_name, stale_before),
            ).fetchall()
            for row in stale:
                connection.execute(
                    "UPDATE cron_runs SET status='failed', finished_at=?, error_code='STALE_LEASE', error_detail='Scheduler lease expired' WHERE id=?",
                    (now_text, row[0]),
                )
                self._release_run_claims(connection, str(row[0]))
            try:
                connection.execute(
                    "INSERT INTO cron_runs(id,job_name,schedule_token,status,owner_token,started_at,heartbeat_at) VALUES (?,?,?,'running',?,?,?)",
                    (run_id, job_name, schedule_token, owner, now_text, now_text),
                )
            except sqlite3.IntegrityError as exc:
                raise LedgerError("Job already started for this schedule token or has an active lease") from exc
            self._audit(connection, "scheduler", "run.started", "cron_run", run_id, {"job_name": job_name})
        return {"run_id": run_id, "owner_token": owner, "started_at": now_text}

    def heartbeat(self, run_id: str, owner_token: str) -> None:
        with self.transaction(immediate=True) as connection:
            changed = connection.execute(
                "UPDATE cron_runs SET heartbeat_at=? WHERE id=? AND owner_token=? AND status='running'",
                (utc_now(), run_id, owner_token),
            ).rowcount
            if changed != 1:
                raise LedgerError("Run lease is not active or ownership token is stale")

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
                "SELECT 1 FROM cron_runs WHERE id=? AND status='running'", (run_id,)
            ).fetchone()
            if not active:
                raise LedgerError("Cannot attach a result to an inactive run")
            connection.execute(
                "INSERT INTO job_results(id,cron_run_id,outcome,summary,artifact_json,created_at) VALUES (?,?,?,?,?,?)",
                (result_id, run_id, outcome, summary.strip(), canonical_json(artifact), utc_now()),
            )
            self._audit(connection, "codex", "result.recorded", "cron_run", run_id, {"outcome": outcome})
        return result_id

    def finish_run(self, run_id: str, owner_token: str, *, failed_error: str | None = None) -> str:
        with self.transaction(immediate=True) as connection:
            row = connection.execute(
                "SELECT outcome FROM job_results WHERE cron_run_id=?", (run_id,)
            ).fetchone()
            outstanding_claims = sum(
                int(
                    connection.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE claim_run_id=? AND status=?",
                        (run_id, status),
                    ).fetchone()[0]
                )
                for table, status in (
                    ("keyword_clusters", "claimed"),
                    ("article_drafts", "publishing"),
                    ("optimization_actions", "claimed"),
                )
            )
            if failed_error:
                status, outcome, error_code, error_detail = "failed", "failed", "AGENT_EXEC_FAILED", failed_error[:4000]
            elif row and row[0] == "completed" and outstanding_claims:
                status, outcome, error_code, error_detail = (
                    "failed",
                    "failed",
                    "CLAIM_UNFINISHED",
                    f"Agent left {outstanding_claims} claimed entities unfinished",
                )
            elif row:
                outcome = str(row[0])
                status, error_code, error_detail = outcome, None, None
            else:
                status, outcome, error_code, error_detail = "failed", "failed", "RESULT_MISSING", "Agent exited without one durable job_result"
            changed = connection.execute(
                "UPDATE cron_runs SET status=?, outcome=?, finished_at=?, error_code=?, error_detail=? WHERE id=? AND owner_token=? AND status='running'",
                (status, outcome, utc_now(), error_code, error_detail, run_id, owner_token),
            ).rowcount
            if changed != 1:
                raise LedgerError("Run lease is not active or ownership token is stale")
            self._release_run_claims(connection, run_id)
            self._audit(connection, "scheduler", "run.finished", "cron_run", run_id, {"status": status})
        return status

    def _release_run_claims(self, connection: sqlite3.Connection, run_id: str) -> int:
        now = utc_now()
        released = connection.execute(
            """UPDATE keyword_clusters
            SET status='ready',claim_token=NULL,claim_expires_at=NULL,claim_run_id=NULL,updated_at=?
            WHERE claim_run_id=? AND status='claimed'""",
            (now, run_id),
        ).rowcount
        released += connection.execute(
            """UPDATE article_drafts
            SET status='approved',claim_token=NULL,claim_expires_at=NULL,claim_run_id=NULL,updated_at=?
            WHERE claim_run_id=? AND status='publishing'""",
            (now, run_id),
        ).rowcount
        released += connection.execute(
            """UPDATE optimization_actions
            SET status='open',claim_token=NULL,claim_expires_at=NULL,claim_run_id=NULL
            WHERE claim_run_id=? AND status='claimed'""",
            (run_id,),
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
            "draft": ("article_drafts", "status IN ('approved','publishing')", "approved_at ASC", "publishing"),
            "action": ("optimization_actions", "status IN ('open','claimed')", "priority_score DESC, created_at ASC", "claimed"),
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
                    "SELECT job_name FROM cron_runs WHERE id=? AND status='running'", (run_id,)
                ).fetchone()
                if not run:
                    raise LedgerError("VEDICWAY_SEO_RUN_ID does not identify an active run")
                allowed_claims = {
                    "article_content_production": {"cluster"},
                    "article_site_publish": {"draft"},
                    "article_optimization": {"action", "draft"},
                }
                if entity not in allowed_claims.get(str(run["job_name"]), set()):
                    raise LedgerError(
                        f"Job {run['job_name']} is not allowed to claim {entity}"
                    )
            row = connection.execute(
                f"SELECT * FROM {table} WHERE {predicate} AND (claim_expires_at IS NULL OR claim_expires_at < ?) ORDER BY {order_by} LIMIT 1",
                (now,),
            ).fetchone()
            if not row:
                return None
            connection.execute(
                f"UPDATE {table} SET status=?, claim_token=?, claim_expires_at=?, claim_run_id=? WHERE id=?",
                (next_status, token, expires, run_id, row["id"]),
            )
            self._audit(connection, "codex", f"{entity}.claimed", entity, row["id"], {"expires_at": expires})
            result = dict(row)
            if entity == "action":
                details = connection.execute(
                    """SELECT p.draft_id,p.public_url,p.content_hash AS published_content_hash,
                    p.request_hash AS published_request_hash,d.brief_id,d.slug,d.title,d.excerpt,
                    d.content_markdown,d.seo_title,d.meta_description,d.focus_keyphrase,
                    d.category,d.author_name
                    FROM optimization_actions a
                    JOIN publications p ON p.id=a.publication_id
                    JOIN article_drafts d ON d.id=p.draft_id
                    WHERE a.id=?""",
                    (row["id"],),
                ).fetchone()
                if not details:
                    raise LedgerError("Optimization action lost its publication or draft")
                result.update(dict(details))
            result.update(
                {
                    "claim_token": token,
                    "claim_expires_at": expires,
                    "claim_run_id": run_id,
                    "status": next_status,
                }
            )
            return result

    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        with self.connect() as connection:
            for table in (
                "cron_runs", "source_documents", "keyword_queries", "keyword_clusters",
                "content_briefs", "article_drafts", "publications", "optimization_actions",
            ):
                counts[table] = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            recent = [dict(row) for row in connection.execute(
                "SELECT id,job_name,status,started_at,finished_at,error_code FROM cron_runs ORDER BY started_at DESC LIMIT 10"
            )]
        return {"counts": counts, "recent_runs": recent}

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
                "SELECT id FROM source_documents WHERE source_kind=? AND source_key=? AND checksum=?",
                (source_kind, payload["source_key"], payload["checksum"]),
            ).fetchone()
            if row:
                record_id = str(row[0])
            else:
                connection.execute(
                    "INSERT INTO source_documents(id,source_kind,source_key,url,status,checksum,retrieved_at,payload_json) VALUES (?,?,?,?,?,?,?,?)",
                    (record_id, source_kind, payload["source_key"], payload.get("url"), status, payload["checksum"], payload.get("retrieved_at", utc_now()), canonical_json(body)),
                )
            self._audit(connection, "codex", "source.recorded", "source_document", record_id, {"source_key": payload["source_key"]})
        return {"id": record_id}

    def _record_tool_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._required(payload, "provider", "tool_name", "request_hash", "response")
        if not isinstance(payload["response"], (dict, list)):
            raise LedgerError("Tool response must be a JSON object or array")
        run_id = str(payload.get("cron_run_id") or os.environ.get("VEDICWAY_SEO_RUN_ID", ""))
        if not run_id:
            raise LedgerError("cron_run_id or VEDICWAY_SEO_RUN_ID is required")
        record_id = str(payload.get("id") or uuid.uuid4())
        with self.transaction(immediate=True) as connection:
            if not connection.execute(
                "SELECT 1 FROM cron_runs WHERE id=? AND status='running'", (run_id,)
            ).fetchone():
                raise LedgerError("Tool response requires an active cron run")
            connection.execute(
                "INSERT INTO raw_tool_responses(id,cron_run_id,provider,tool_name,request_hash,response_json,observed_at,expires_at) VALUES (?,?,?,?,?,?,?,?)",
                (record_id, run_id, payload["provider"], payload["tool_name"], payload["request_hash"], canonical_json(payload["response"]), payload.get("observed_at", utc_now()), payload.get("expires_at")),
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
        with self.transaction(immediate=True) as connection:
            row = connection.execute(
                "SELECT id FROM keyword_queries WHERE phrase=? AND region_id=? AND source=? AND observed_at=?",
                (phrase, region_id, source, observed_at),
            ).fetchone()
            if row:
                record_id = str(row[0])
            else:
                connection.execute(
                    "INSERT INTO keyword_queries(id,phrase,region_id,source,intent,metrics_json,observed_at) VALUES (?,?,?,?,?,?,?)",
                    (record_id, phrase, region_id, source, intent, canonical_json(payload.get("metrics", {})), observed_at),
                )
        return {"id": record_id}

    def _record_serp_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._required(payload, "query_id", "region_id", "results", "checksum")
        results = payload["results"]
        if not isinstance(results, list) or not results:
            raise LedgerError("SERP snapshot requires a non-empty results array")
        checksum = hashlib.sha256(canonical_json(results).encode("utf-8")).hexdigest()
        if not secrets.compare_digest(str(payload["checksum"]), checksum):
            raise LedgerError("SERP snapshot checksum does not match its canonical results")
        requested_at = str(payload.get("requested_at") or utc_now())
        record_id = str(payload.get("id") or uuid.uuid4())
        with self.transaction(immediate=True) as connection:
            query = connection.execute(
                "SELECT region_id FROM keyword_queries WHERE id=?", (payload["query_id"],)
            ).fetchone()
            if not query or str(query["region_id"]) != str(payload["region_id"]):
                raise LedgerError("SERP snapshot query and region do not match")
            existing = connection.execute(
                "SELECT id,checksum FROM serp_snapshots WHERE query_id=? AND requested_at=?",
                (payload["query_id"], requested_at),
            ).fetchone()
            if existing:
                if not secrets.compare_digest(str(existing["checksum"]), checksum):
                    raise LedgerError("Existing SERP snapshot has different results")
                record_id = str(existing["id"])
            else:
                connection.execute(
                    "INSERT INTO serp_snapshots(id,query_id,region_id,requested_at,result_json,checksum) VALUES (?,?,?,?,?,?)",
                    (
                        record_id,
                        payload["query_id"],
                        str(payload["region_id"]),
                        requested_at,
                        canonical_json(results),
                        checksum,
                    ),
                )
        return {"id": record_id}

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
            connection.execute(
                """INSERT INTO keyword_clusters(id,slug,title,intent,status,priority_score,rationale,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(slug) DO UPDATE SET
                  title=excluded.title, intent=excluded.intent, priority_score=excluded.priority_score,
                  rationale=excluded.rationale, updated_at=excluded.updated_at,
                  status=CASE WHEN keyword_clusters.status IN ('claimed','briefed','published')
                    THEN keyword_clusters.status ELSE excluded.status END""",
                (record_id, payload["slug"], payload["title"], payload["intent"], status, float(payload.get("priority_score", 0)), payload.get("rationale", ""), now, now),
            )
            row = connection.execute("SELECT id FROM keyword_clusters WHERE slug=?", (payload["slug"],)).fetchone()
            record_id = str(row[0])
            if "query_ids" in payload:
                connection.execute("DELETE FROM cluster_queries WHERE cluster_id=?", (record_id,))
            for query_id in query_ids:
                connection.execute(
                    "INSERT INTO cluster_queries(cluster_id,query_id,is_primary) VALUES (?,?,?)",
                    (record_id, query_id, int(query_id == str(primary_query_id))),
                )
        return {"id": record_id}

    def _record_brief(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._required(payload, "cluster_id", "claim_token", "title", "primary_query", "audience_problem", "search_intent", "checksum")
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
        if not secrets.compare_digest(str(payload["checksum"]), checksum):
            raise LedgerError("Brief checksum does not match its canonical contract")
        record_id = str(payload.get("id") or uuid.uuid4())
        now = utc_now()
        with self.transaction(immediate=True) as connection:
            changed = connection.execute(
                "UPDATE keyword_clusters SET status='briefed',claim_token=NULL,claim_expires_at=NULL,claim_run_id=NULL,updated_at=? WHERE id=? AND status='claimed' AND claim_token=? AND claim_expires_at>=?",
                (now, payload["cluster_id"], payload["claim_token"], now),
            ).rowcount
            if changed != 1:
                raise LedgerError("Cluster claim is stale or does not belong to this run")
            connection.execute(
                "INSERT INTO content_briefs(id,cluster_id,status,title,primary_query,audience_problem,search_intent,outline_json,evidence_json,internal_links_json,prohibited_claims_json,checksum,created_at,approved_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (record_id, payload["cluster_id"], "approved", payload["title"], payload["primary_query"], payload["audience_problem"], payload["search_intent"], canonical_json(outline), canonical_json(evidence), canonical_json(internal_links), canonical_json(prohibited_claims), checksum, now, now),
            )
        return {"id": record_id}

    def _record_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._required(payload, "brief_id", "slug", "title", "excerpt", "content_markdown", "seo_title", "meta_description", "focus_keyphrase", "category", "content_hash")
        content = str(payload["content_markdown"]).strip()
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if not secrets.compare_digest(str(payload["content_hash"]), content_hash):
            raise LedgerError("Draft content_hash does not match content_markdown")
        if payload.get("status", "draft") not in {"draft", "editing"}:
            raise LedgerError("Draft writer cannot set an approved or terminal status")
        record_id = str(payload.get("id") or uuid.uuid4())
        now = utc_now()
        with self.transaction(immediate=True) as connection:
            brief = connection.execute("SELECT status FROM content_briefs WHERE id=?", (payload["brief_id"],)).fetchone()
            if not brief or brief[0] not in {"approved", "consumed"}:
                raise LedgerError("Draft requires an approved brief")
            existing = connection.execute(
                "SELECT id,brief_id,status FROM article_drafts WHERE slug=?", (payload["slug"],)
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
                    WHERE a.id=? AND a.claim_token=? AND a.status='claimed'
                      AND a.claim_expires_at>=? AND p.draft_id=?""",
                    (payload["action_id"], payload["action_claim_token"], now, existing["id"]),
                ).fetchone()
                if not action:
                    raise LedgerError("Published draft changes require an active optimization action")
            connection.execute("UPDATE content_briefs SET status='consumed' WHERE id=?", (payload["brief_id"],))
            connection.execute(
                """INSERT INTO article_drafts(id,brief_id,slug,status,title,excerpt,content_markdown,seo_title,meta_description,focus_keyphrase,category,author_name,content_hash,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(slug) DO UPDATE SET title=excluded.title,excerpt=excluded.excerpt,
                content_markdown=excluded.content_markdown,seo_title=excluded.seo_title,
                meta_description=excluded.meta_description,focus_keyphrase=excluded.focus_keyphrase,
                category=excluded.category,author_name=excluded.author_name,content_hash=excluded.content_hash,
                updated_at=excluded.updated_at,status='editing',quality_report_json=NULL,approved_at=NULL""",
                (record_id, payload["brief_id"], payload["slug"], payload.get("status", "draft"), payload["title"], payload["excerpt"], content, payload["seo_title"], payload["meta_description"], payload["focus_keyphrase"], payload["category"], payload.get("author_name", "Редакция VedicWay"), content_hash, now, now),
            )
            row = connection.execute("SELECT id FROM article_drafts WHERE slug=?", (payload["slug"],)).fetchone()
            record_id = str(row[0])
        return {"id": record_id}

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
                "SELECT content_hash FROM article_drafts WHERE id=?", (payload["draft_id"],)
            ).fetchone()
            if not draft or payload["report"].get("content_hash") != draft["content_hash"]:
                raise LedgerError("Quality report is not bound to the current draft content")
            changed = connection.execute(
                "UPDATE article_drafts SET status=?,quality_report_json=?,updated_at=?,approved_at=? WHERE id=? AND status IN ('draft','editing','quality_failed','approved')",
                (status, canonical_json(payload["report"]), now, now if status == "approved" else None, payload["draft_id"]),
            ).rowcount
            if changed != 1:
                raise LedgerError("Draft is missing or already terminal")
        return {"id": payload["draft_id"], "status": status}

    def _record_media(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._required(payload, "draft_id", "purpose", "local_path", "alt_text", "source_kind", "license_note", "checksum")
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
        record_id = str(payload.get("id") or uuid.uuid4())
        with self.transaction(immediate=True) as connection:
            existing = connection.execute(
                "SELECT id FROM article_media WHERE draft_id=? AND (purpose='cover' AND ?='cover' OR checksum=? AND purpose=?)",
                (payload["draft_id"], payload["purpose"], checksum, payload["purpose"]),
            ).fetchone()
            if existing:
                record_id = str(existing["id"])
                connection.execute(
                    "UPDATE article_media SET purpose=?,local_path=?,alt_text=?,title=?,caption=?,source_kind=?,source_url=?,license_note=?,checksum=?,backend_media_id=?,public_url=? WHERE id=?",
                    (payload["purpose"], relative_path, payload["alt_text"], payload.get("title", ""), payload.get("caption", ""), payload["source_kind"], payload.get("source_url"), payload["license_note"], checksum, payload.get("backend_media_id"), payload.get("public_url"), record_id),
                )
            else:
                connection.execute(
                    "INSERT INTO article_media(id,draft_id,purpose,local_path,alt_text,title,caption,source_kind,source_url,license_note,checksum,backend_media_id,public_url,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (record_id, payload["draft_id"], payload["purpose"], relative_path, payload["alt_text"], payload.get("title", ""), payload.get("caption", ""), payload["source_kind"], payload.get("source_url"), payload["license_note"], checksum, payload.get("backend_media_id"), payload.get("public_url"), utc_now()),
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
                "SELECT status,content_hash,claim_token,claim_expires_at FROM article_drafts WHERE id=?",
                (payload["draft_id"],),
            ).fetchone()
            if not draft or draft["content_hash"] != payload["content_hash"]:
                raise LedgerError("Publication attempt does not match the current draft content")
            if payload["target"] == "site":
                self._required(payload, "claim_token")
                if (
                    draft["status"] != "publishing"
                    or draft["claim_token"] != payload["claim_token"]
                    or not draft["claim_expires_at"]
                    or draft["claim_expires_at"] < now
                ):
                    raise LedgerError("Site publication attempt requires the active draft claim")
            previous = connection.execute(
                "SELECT content_hash,request_hash FROM publication_attempts WHERE idempotency_key=? LIMIT 1",
                (payload["idempotency_key"],),
            ).fetchone()
            if previous and (
                previous["content_hash"] != payload["content_hash"]
                or previous["request_hash"] != payload["request_hash"]
            ):
                raise LedgerError("An idempotency_key cannot be reused for different publication content")
            attempt_no = int(payload.get("attempt_no") or connection.execute(
                "SELECT COALESCE(MAX(attempt_no),0)+1 FROM publication_attempts WHERE draft_id=? AND target=?",
                (payload["draft_id"], payload["target"]),
            ).fetchone()[0])
            connection.execute(
                "INSERT INTO publication_attempts(id,draft_id,target,attempt_no,idempotency_key,attempt_token,status,content_hash,request_hash,response_json,started_at,finished_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
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
                "SELECT brief_id,status,content_hash,claim_token,claim_expires_at FROM article_drafts WHERE id=?",
                (payload["draft_id"],),
            ).fetchone()
            if not draft or draft["content_hash"] != payload["content_hash"]:
                raise LedgerError("Publication evidence does not match an approved draft")
            attempt = connection.execute(
                "SELECT content_hash,request_hash FROM publication_attempts WHERE draft_id=? AND target=? AND attempt_token=? AND status='succeeded'",
                (payload["draft_id"], payload["target"], payload["attempt_token"]),
            ).fetchone()
            if not attempt or attempt["content_hash"] != payload["content_hash"] or attempt["request_hash"] != payload["request_hash"]:
                raise LedgerError("A succeeded publication attempt is required before publication evidence")
            if payload["target"] == "site":
                self._required(payload, "claim_token")
                if (
                    draft["status"] != "publishing"
                    or draft["claim_token"] != payload["claim_token"]
                    or not draft["claim_expires_at"]
                    or draft["claim_expires_at"] < now
                ):
                    raise LedgerError("Site publication requires the active draft claim")
                required_checks = {"canonical", "article_schema", "title", "request_hash", "sitemap", "dzen_feed", "cover"}
                checks = payload["evidence"].get("checks")
                if not isinstance(checks, dict) or not required_checks.issubset(checks) or not all(
                    checks[name] is True for name in required_checks
                ):
                    raise LedgerError("Site publication evidence is incomplete")
            elif payload["target"] == "dzen":
                site = connection.execute(
                    "SELECT 1 FROM publications WHERE draft_id=? AND target='site' AND status='verified' AND content_hash=?",
                    (payload["draft_id"], payload["content_hash"]),
                ).fetchone()
                if not site:
                    raise LedgerError("Dzen evidence requires the matching verified site publication")
            connection.execute(
                """INSERT INTO publications(id,draft_id,target,status,public_url,external_id,content_hash,request_hash,evidence_json,published_at,verified_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(draft_id,target) DO UPDATE SET
                  status=CASE WHEN publications.status='verified' THEN 'verified' ELSE excluded.status END,
                  public_url=excluded.public_url,external_id=excluded.external_id,
                  content_hash=excluded.content_hash,request_hash=excluded.request_hash,
                  evidence_json=excluded.evidence_json,
                  verified_at=COALESCE(excluded.verified_at,publications.verified_at)""",
                (record_id, payload["draft_id"], payload["target"], status, payload["public_url"], payload.get("external_id"), payload["content_hash"], payload["request_hash"], canonical_json(payload["evidence"]), payload.get("published_at", now), now if status == "verified" else None),
            )
            publication = connection.execute(
                "SELECT id FROM publications WHERE draft_id=? AND target=?",
                (payload["draft_id"], payload["target"]),
            ).fetchone()
            record_id = str(publication["id"])
            if payload["target"] == "site":
                connection.execute("UPDATE article_drafts SET status='published',claim_token=NULL,claim_expires_at=NULL,claim_run_id=NULL,updated_at=? WHERE id=?", (now, payload["draft_id"]))
                connection.execute("UPDATE keyword_clusters SET status='published',updated_at=? WHERE id=(SELECT cluster_id FROM content_briefs WHERE id=?)", (now, draft["brief_id"]))
        return {"id": record_id}

    def _record_performance(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._required(payload, "publication_id", "window_start", "window_end", "webmaster", "metrika")
        record_id = str(payload.get("id") or uuid.uuid4())
        with self.transaction(immediate=True) as connection:
            connection.execute(
                "INSERT INTO performance_snapshots(id,publication_id,window_start,window_end,webmaster_json,metrika_json,captured_at) VALUES (?,?,?,?,?,?,?)",
                (record_id, payload["publication_id"], payload["window_start"], payload["window_end"], canonical_json(payload["webmaster"]), canonical_json(payload["metrika"]), payload.get("captured_at", utc_now())),
            )
        return {"id": record_id}

    def _record_action(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._required(payload, "publication_id", "action_type", "hypothesis", "success_metric", "evidence")
        record_id = str(payload.get("id") or uuid.uuid4())
        with self.transaction(immediate=True) as connection:
            publication = connection.execute(
                "SELECT request_hash FROM publications WHERE id=? AND target='site' AND status='verified'",
                (payload["publication_id"],),
            ).fetchone()
            if not publication:
                raise LedgerError("Optimization action requires a verified site publication")
            connection.execute(
                "INSERT INTO optimization_actions(id,publication_id,action_type,status,priority_score,hypothesis,success_metric,evidence_json,baseline_request_hash,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
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
                WHERE a.id=? AND a.status='claimed' AND a.claim_token=? AND a.claim_expires_at>=?""",
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
                "UPDATE optimization_actions SET status=?,result_evidence_json=?,claim_token=NULL,claim_expires_at=NULL,claim_run_id=NULL,completed_at=? WHERE id=?",
                (status, canonical_json(payload["evidence"]), now, payload["action_id"]),
            )
            self._audit(connection, "codex", "action.finished", "optimization_action", payload["action_id"], {"status": status})
        return {"id": payload["action_id"], "status": status}

    def backup(self, destination: str | Path) -> dict[str, Any]:
        target = Path(destination).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        if target == self.path:
            raise LedgerError("Backup destination must differ from the live database")
        with self.connect() as source, closing(sqlite3.connect(target)) as output:
            source.backup(output)
        checksum = hashlib.sha256(target.read_bytes()).hexdigest()
        return {"path": str(target), "size_bytes": target.stat().st_size, "sha256": checksum}

    @staticmethod
    def _audit(connection: sqlite3.Connection, actor: str, action: str, entity_type: str, entity_id: str | None, detail: Any) -> None:
        connection.execute(
            "INSERT INTO audit_events(occurred_at,actor,action,entity_type,entity_id,detail_json) VALUES (?,?,?,?,?,?)",
            (utc_now(), actor, action, entity_type, entity_id, canonical_json(detail)),
        )
