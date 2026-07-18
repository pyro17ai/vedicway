from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from cryptography.fernet import Fernet

from .schemas import BirthInput, ChartEvent, ChartSnapshot, InterpretationBundle, JobStatus, SectionStatus


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _iso(value: datetime | None = None) -> str:
    return (value or _utc_now()).isoformat()


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _json_load(value: str | None, fallback: Any) -> Any:
    return json.loads(value) if value else fallback


class Store:
    """Durable local runtime store.

    PostgreSQL DDL lives in migrations for deployment. SQLite keeps the same resource
    boundaries and lets the complete BFF flow run locally without a service dependency.
    """

    def __init__(self, data_dir: str | Path | None = None) -> None:
        default_dir = Path(__file__).resolve().parents[2] / ".data"
        self.data_dir = Path(data_dir or os.environ.get("VEDICWAY_DATA_DIR", default_dir)).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir = self.data_dir / "reports"
        self.reports_dir.mkdir(exist_ok=True)
        self.db_path = self.data_dir / "vedicway.sqlite3"
        self._lock = threading.RLock()
        self._fernet = Fernet(self._load_key())
        self._signing_key = self._load_signing_key()
        self._initialize()

    def _load_key(self) -> bytes:
        configured = os.environ.get("VEDICWAY_DATA_KEY")
        if configured:
            return configured.encode("utf-8")
        if os.environ.get("VEDICWAY_ENV") == "production":
            raise RuntimeError("VEDICWAY_DATA_KEY is required in production")
        key_file = self.data_dir / "development-fernet.key"
        if key_file.exists():
            return key_file.read_bytes().strip()
        key = Fernet.generate_key()
        key_file.write_bytes(key)
        return key

    def _load_signing_key(self) -> bytes:
        configured = os.environ.get("VEDICWAY_SIGNING_KEY")
        if configured:
            return configured.encode("utf-8")
        key_file = self.data_dir / "development-signing.key"
        if key_file.exists():
            return key_file.read_bytes()
        key = secrets.token_bytes(32)
        key_file.write_bytes(key)
        return key

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, timeout=15, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        statements = """
        CREATE TABLE IF NOT EXISTS anonymous_sessions (
          id TEXT PRIMARY KEY,
          token_hash TEXT UNIQUE NOT NULL,
          created_at TEXT NOT NULL,
          last_seen_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS birth_profiles (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL REFERENCES anonymous_sessions(id),
          encrypted_payload BLOB NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS charts (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL REFERENCES anonymous_sessions(id),
          birth_profile_id TEXT NOT NULL REFERENCES birth_profiles(id),
          idempotency_key TEXT NOT NULL,
          status TEXT NOT NULL,
          birth_public_json TEXT NOT NULL,
          snapshot_json TEXT,
          evidence_json TEXT,
          free_bundle_json TEXT,
          paid_bundle_json TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(session_id, idempotency_key)
        );
        CREATE TABLE IF NOT EXISTS chart_access (
          chart_id TEXT NOT NULL REFERENCES charts(id),
          session_id TEXT NOT NULL REFERENCES anonymous_sessions(id),
          granted_at TEXT NOT NULL,
          PRIMARY KEY(chart_id, session_id)
        );
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY,
          chart_id TEXT NOT NULL REFERENCES charts(id),
          job_type TEXT NOT NULL,
          status TEXT NOT NULL,
          priority INTEGER NOT NULL,
          attempts INTEGER NOT NULL DEFAULT 0,
          input_checksum TEXT,
          error_json TEXT,
          scheduled_at TEXT NOT NULL,
          started_at TEXT,
          finished_at TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS jobs_queue_idx ON jobs(status, priority DESC, scheduled_at, created_at);
        CREATE TABLE IF NOT EXISTS outbox_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          chart_id TEXT NOT NULL REFERENCES charts(id),
          event TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS outbox_chart_idx ON outbox_events(chart_id, id);
        CREATE TABLE IF NOT EXISTS agent_runs (
          id TEXT PRIMARY KEY,
          chart_id TEXT NOT NULL REFERENCES charts(id),
          job_id TEXT NOT NULL REFERENCES jobs(id),
          provider TEXT NOT NULL,
          prompt_version TEXT NOT NULL,
          input_checksum TEXT NOT NULL,
          output_checksum TEXT,
          status TEXT NOT NULL,
          created_at TEXT NOT NULL,
          finished_at TEXT
        );
        CREATE TABLE IF NOT EXISTS purchases (
          id TEXT PRIMARY KEY,
          chart_id TEXT NOT NULL REFERENCES charts(id),
          idempotency_key TEXT NOT NULL,
          email_ciphertext BLOB,
          provider TEXT NOT NULL,
          provider_payment_id TEXT,
          status TEXT NOT NULL,
          amount_minor INTEGER NOT NULL,
          currency TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(chart_id, idempotency_key)
        );
        CREATE TABLE IF NOT EXISTS payment_events (
          provider TEXT NOT NULL,
          provider_event_id TEXT NOT NULL,
          payload_checksum TEXT NOT NULL,
          received_at TEXT NOT NULL,
          PRIMARY KEY(provider, provider_event_id)
        );
        CREATE TABLE IF NOT EXISTS entitlements (
          id TEXT PRIMARY KEY,
          chart_id TEXT NOT NULL REFERENCES charts(id),
          product_code TEXT NOT NULL,
          purchase_id TEXT REFERENCES purchases(id),
          granted_at TEXT NOT NULL,
          UNIQUE(chart_id, product_code)
        );
        CREATE TABLE IF NOT EXISTS reports (
          id TEXT PRIMARY KEY,
          chart_id TEXT NOT NULL REFERENCES charts(id),
          status TEXT NOT NULL,
          path TEXT,
          checksum TEXT,
          size_bytes INTEGER,
          pages INTEGER,
          error_code TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(chart_id)
        );
        CREATE TABLE IF NOT EXISTS saved_questions (
          chart_id TEXT NOT NULL REFERENCES charts(id),
          question_id TEXT NOT NULL,
          saved INTEGER NOT NULL DEFAULT 0,
          reflection_status TEXT NOT NULL DEFAULT 'saved',
          note_ciphertext BLOB,
          updated_at TEXT NOT NULL,
          PRIMARY KEY(chart_id, question_id)
        );
        CREATE TABLE IF NOT EXISTS magic_links (
          token_hash TEXT PRIMARY KEY,
          chart_id TEXT NOT NULL REFERENCES charts(id),
          scope TEXT NOT NULL,
          expires_at TEXT NOT NULL,
          used_at TEXT,
          created_at TEXT NOT NULL
        );
        """
        with self._lock, self._connection() as connection:
            connection.executescript(statements)
            question_columns = {row["name"] for row in connection.execute("PRAGMA table_info(saved_questions)").fetchall()}
            if "reflection_status" not in question_columns:
                connection.execute("ALTER TABLE saved_questions ADD COLUMN reflection_status TEXT NOT NULL DEFAULT 'saved'")
            connection.execute(
                "INSERT OR IGNORE INTO chart_access (chart_id, session_id, granted_at) SELECT id, session_id, created_at FROM charts"
            )

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}_{secrets.token_urlsafe(18)}"

    def _encrypt(self, value: Any) -> bytes:
        return self._fernet.encrypt(_json_dump(value).encode("utf-8"))

    def _decrypt(self, value: bytes | str | None) -> Any:
        if value is None:
            raise LookupError("Encrypted value is missing")
        raw = value.encode("utf-8") if isinstance(value, str) else value
        return json.loads(self._fernet.decrypt(raw).decode("utf-8"))

    def create_session(self) -> tuple[str, str]:
        session_id = self._new_id("ses")
        token = secrets.token_urlsafe(32)
        now = _iso()
        with self._lock, self._connection() as connection:
            connection.execute(
                "INSERT INTO anonymous_sessions (id, token_hash, created_at, last_seen_at) VALUES (?, ?, ?, ?)",
                (session_id, self._token_hash(token), now, now),
            )
        return session_id, token

    def session_for_token(self, token: str | None) -> str | None:
        if not token:
            return None
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT id FROM anonymous_sessions WHERE token_hash = ?", (self._token_hash(token),)
            ).fetchone()
            if not row:
                return None
            connection.execute("UPDATE anonymous_sessions SET last_seen_at = ? WHERE id = ?", (_iso(), row["id"]))
            return str(row["id"])

    def ensure_session(self, token: str | None) -> tuple[str, str | None]:
        existing = self.session_for_token(token)
        if existing:
            return existing, None
        return self.create_session()

    def create_chart(
        self,
        session_id: str,
        birth: BirthInput,
        idempotency_key: str,
    ) -> tuple[str, bool]:
        with self._lock, self._connection() as connection:
            existing = connection.execute(
                "SELECT id FROM charts WHERE session_id = ? AND idempotency_key = ?",
                (session_id, idempotency_key),
            ).fetchone()
            if existing:
                return str(existing["id"]), False
            chart_id = self._new_id("chart")
            profile_id = self._new_id("birth")
            now = _iso()
            public_birth = {
                "local_date": birth.local_datetime.date().isoformat(),
                "local_time": birth.local_datetime.time().isoformat(timespec="minutes"),
                "place": birth.place.display_name,
                "tzid": birth.place.tzid,
                "utc_offset_seconds": birth.resolved_time.utc_offset_seconds,
                "time_accuracy": birth.time_accuracy.value,
            }
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "INSERT INTO birth_profiles (id, session_id, encrypted_payload, created_at) VALUES (?, ?, ?, ?)",
                    (profile_id, session_id, self._encrypt(birth.model_dump(mode="json")), now),
                )
                connection.execute(
                    """INSERT INTO charts
                    (id, session_id, birth_profile_id, idempotency_key, status, birth_public_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'accepted', ?, ?, ?)""",
                    (chart_id, session_id, profile_id, idempotency_key, _json_dump(public_birth), now, now),
                )
                connection.execute(
                    "INSERT INTO chart_access (chart_id, session_id, granted_at) VALUES (?, ?, ?)",
                    (chart_id, session_id, now),
                )
                self._enqueue(connection, chart_id, "instant_v1", priority=100)
                self._emit(connection, chart_id, "chart.accepted", {"chart_id": chart_id, "accepted_at": now})
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return chart_id, True

    def chart_owned_by(self, chart_id: str, session_id: str) -> bool:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT 1 FROM chart_access WHERE chart_id = ? AND session_id = ?", (chart_id, session_id)
            ).fetchone()
            return row is not None

    def grant_chart_access(self, chart_id: str, session_id: str) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO chart_access (chart_id, session_id, granted_at) VALUES (?, ?, ?)",
                (chart_id, session_id, _iso()),
            )

    def get_birth(self, chart_id: str) -> BirthInput:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                """SELECT birth_profiles.encrypted_payload FROM charts
                   JOIN birth_profiles ON birth_profiles.id = charts.birth_profile_id WHERE charts.id = ?""",
                (chart_id,),
            ).fetchone()
        if not row:
            raise LookupError(chart_id)
        return BirthInput.model_validate(self._decrypt(row["encrypted_payload"]))

    def _get_chart_row(self, chart_id: str) -> sqlite3.Row:
        with self._lock, self._connection() as connection:
            row = connection.execute("SELECT * FROM charts WHERE id = ?", (chart_id,)).fetchone()
        if not row:
            raise LookupError(chart_id)
        return row

    def get_snapshot(self, chart_id: str) -> ChartSnapshot | None:
        row = self._get_chart_row(chart_id)
        if not row["snapshot_json"]:
            return None
        return ChartSnapshot.model_validate(_json_load(row["snapshot_json"], {}))

    def save_snapshot(self, chart_id: str, snapshot: ChartSnapshot) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                "UPDATE charts SET snapshot_json = ?, status = 'partial_ready', updated_at = ? WHERE id = ?",
                (_json_dump(snapshot.model_dump(mode="json")), _iso(), chart_id),
            )

    def commit_snapshot_events(
        self,
        chart_id: str,
        snapshot: ChartSnapshot,
        events: list[tuple[str, dict[str, Any]]],
        status: str = "partial_ready",
    ) -> None:
        """Persist a state transition and its outbox records in one transaction."""
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "UPDATE charts SET snapshot_json = ?, status = ?, updated_at = ? WHERE id = ?",
                    (_json_dump(snapshot.model_dump(mode="json")), status, _iso(), chart_id),
                )
                for event, payload in events:
                    self._emit(connection, chart_id, event, payload)
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def merge_sections(self, chart_id: str, updates: dict[str, dict[str, Any]]) -> ChartSnapshot:
        snapshot = self.get_snapshot(chart_id)
        if snapshot is None:
            raise LookupError(f"Snapshot missing for {chart_id}")
        data = snapshot.model_dump(mode="json")
        data["sections"].update(updates)
        result = ChartSnapshot.model_validate(data)
        self.save_snapshot(chart_id, result)
        return result

    def save_evidence(self, chart_id: str, facts: list[dict[str, Any]], packets: list[dict[str, Any]]) -> None:
        payload = {"facts": facts, "packets": packets}
        with self._lock, self._connection() as connection:
            connection.execute(
                "UPDATE charts SET evidence_json = ?, updated_at = ? WHERE id = ?",
                (_json_dump(payload), _iso(), chart_id),
            )

    def commit_evidence_events(
        self,
        chart_id: str,
        snapshot: ChartSnapshot,
        facts: list[dict[str, Any]],
        packets: list[dict[str, Any]],
        events: list[tuple[str, dict[str, Any]]],
    ) -> None:
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "UPDATE charts SET snapshot_json = ?, evidence_json = ?, status = 'partial_ready', updated_at = ? WHERE id = ?",
                    (
                        _json_dump(snapshot.model_dump(mode="json")),
                        _json_dump({"facts": facts, "packets": packets}),
                        _iso(),
                        chart_id,
                    ),
                )
                for event, payload in events:
                    self._emit(connection, chart_id, event, payload)
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def get_evidence(self, chart_id: str) -> dict[str, Any] | None:
        row = self._get_chart_row(chart_id)
        return _json_load(row["evidence_json"], None)

    def save_bundle(self, chart_id: str, bundle: InterpretationBundle, paid: bool) -> None:
        field = "paid_bundle_json" if paid else "free_bundle_json"
        with self._lock, self._connection() as connection:
            connection.execute(
                f"UPDATE charts SET {field} = ?, status = 'ready', updated_at = ? WHERE id = ?",
                (_json_dump(bundle.model_dump(mode="json")), _iso(), chart_id),
            )

    def commit_bundle_events(
        self,
        chart_id: str,
        bundle: InterpretationBundle,
        paid: bool,
        events: list[tuple[str, dict[str, Any]]],
    ) -> None:
        field = "paid_bundle_json" if paid else "free_bundle_json"
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    f"UPDATE charts SET {field} = ?, status = 'ready', updated_at = ? WHERE id = ?",
                    (_json_dump(bundle.model_dump(mode="json")), _iso(), chart_id),
                )
                for event, payload in events:
                    self._emit(connection, chart_id, event, payload)
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def get_bundle(self, chart_id: str, paid: bool = False) -> InterpretationBundle | None:
        row = self._get_chart_row(chart_id)
        field = "paid_bundle_json" if paid else "free_bundle_json"
        value = row[field]
        return InterpretationBundle.model_validate(_json_load(value, {})) if value else None

    def get_chart_resource(self, chart_id: str, include_paid: bool = False) -> dict[str, Any]:
        row = self._get_chart_row(chart_id)
        snapshot = _json_load(row["snapshot_json"], None)
        sections = snapshot.get("sections", {}) if snapshot else {}
        entitled = self.has_entitlement(chart_id)
        paid_bundle = _json_load(row["paid_bundle_json"], None) if include_paid and entitled else None
        bundle = paid_bundle or _json_load(row["free_bundle_json"], None)
        report = self.get_report(chart_id)
        evidence = _json_load(row["evidence_json"], None)
        section_statuses = {key: value.get("status", "queued") for key, value in sections.items()}
        # Interpretation and reflection questions are persisted separately from the
        # immutable calculation snapshot. Publish their concrete readiness beside
        # the calculation sections so each tab can expose its own state.
        section_statuses.setdefault("interpretation", "ready" if bundle else "queued")
        section_statuses.setdefault("questions", "ready" if bundle else "queued")
        return {
            "chart_id": chart_id,
            "status": row["status"],
            "birth": _json_load(row["birth_public_json"], {}),
            "snapshot_id": snapshot.get("snapshot_id") if snapshot else None,
            "sections": section_statuses,
            "interpretation": bundle,
            "evidence": evidence,
            "entitlement": {"report_full": entitled},
            "pdf": report,
        }

    def mark_chart_status(self, chart_id: str, status: str) -> None:
        with self._lock, self._connection() as connection:
            connection.execute("UPDATE charts SET status = ?, updated_at = ? WHERE id = ?", (status, _iso(), chart_id))

    def get_section(self, chart_id: str, section: str, include_paid: bool = False) -> dict[str, Any] | None:
        if section in {"interpretation", "questions"}:
            bundle = self.get_bundle(chart_id, paid=include_paid and self.has_entitlement(chart_id))
            if bundle is None and include_paid and self.has_entitlement(chart_id):
                bundle = self.get_bundle(chart_id, paid=False)
            if bundle is None:
                return None
            if section == "questions":
                return {"section": "questions", "status": "ready", "data": {"questions": bundle.model_dump(mode="json")["questions"]}}
            payload = bundle.model_dump(mode="json")
            payload.pop("questions", None)
            return {"section": "interpretation", "status": "ready", "data": payload}
        snapshot = self.get_snapshot(chart_id)
        if snapshot is None:
            return None
        return snapshot.sections.get(section)

    def _enqueue(self, connection: sqlite3.Connection, chart_id: str, job_type: str, priority: int = 10) -> str:
        now = _iso()
        job_id = self._new_id("job")
        connection.execute(
            """INSERT INTO jobs (id, chart_id, job_type, status, priority, scheduled_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (job_id, chart_id, job_type, JobStatus.QUEUED.value, priority, now, now, now),
        )
        return job_id

    def enqueue_job(self, chart_id: str, job_type: str, priority: int = 10) -> str:
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute(
                    """SELECT id FROM jobs WHERE chart_id = ? AND job_type = ?
                       AND status IN ('queued', 'running', 'validating', 'succeeded') ORDER BY created_at DESC LIMIT 1""",
                    (chart_id, job_type),
                ).fetchone()
                if existing:
                    connection.commit()
                    return str(existing["id"])
                job_id = self._enqueue(connection, chart_id, job_type, priority)
                connection.commit()
                return job_id
            except Exception:
                connection.rollback()
                raise

    def claim_next_job(self) -> dict[str, Any] | None:
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    """SELECT * FROM jobs WHERE status = 'queued' AND scheduled_at <= ?
                       ORDER BY priority DESC, created_at ASC LIMIT 1""",
                    (_iso(),),
                ).fetchone()
                if not row:
                    connection.commit()
                    return None
                now = _iso()
                connection.execute(
                    """UPDATE jobs SET status = ?, attempts = attempts + 1, started_at = ?, updated_at = ? WHERE id = ?""",
                    (JobStatus.RUNNING.value, now, now, row["id"]),
                )
                connection.commit()
                return {**dict(row), "status": JobStatus.RUNNING.value, "attempts": int(row["attempts"]) + 1}
            except Exception:
                connection.rollback()
                raise

    def update_job_status(self, job_id: str, status: JobStatus, error: dict[str, Any] | None = None) -> None:
        finished = _iso() if status in {JobStatus.SUCCEEDED, JobStatus.FAILED_RETRYABLE, JobStatus.FAILED_TERMINAL} else None
        with self._lock, self._connection() as connection:
            connection.execute(
                "UPDATE jobs SET status = ?, error_json = ?, finished_at = ?, updated_at = ? WHERE id = ?",
                (status.value, _json_dump(error) if error else None, finished, _iso(), job_id),
            )

    def get_job(self, chart_id: str, job_type: str) -> dict[str, Any] | None:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE chart_id = ? AND job_type = ? ORDER BY created_at DESC LIMIT 1",
                (chart_id, job_type),
            ).fetchone()
            return dict(row) if row else None

    def start_agent_run(
        self,
        chart_id: str,
        job_id: str,
        provider: str,
        prompt_version: str,
        input_checksum: str,
    ) -> str:
        run_id = self._new_id("agent")
        with self._lock, self._connection() as connection:
            connection.execute(
                """INSERT INTO agent_runs (id, chart_id, job_id, provider, prompt_version, input_checksum, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'running', ?)""",
                (run_id, chart_id, job_id, provider, prompt_version, input_checksum, _iso()),
            )
        return run_id

    def finish_agent_run(self, run_id: str, status: str, output_checksum: str | None = None) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                "UPDATE agent_runs SET status = ?, output_checksum = ?, finished_at = ? WHERE id = ?",
                (status, output_checksum, _iso(), run_id),
            )

    def retry_job(self, chart_id: str, job_type: str) -> str | None:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE chart_id = ? AND job_type = ? ORDER BY created_at DESC LIMIT 1",
                (chart_id, job_type),
            ).fetchone()
            if not row or row["status"] != JobStatus.FAILED_RETRYABLE.value:
                return None
            now = _iso()
            connection.execute(
                "UPDATE jobs SET status = 'queued', error_json = NULL, scheduled_at = ?, updated_at = ? WHERE id = ?",
                (now, now, row["id"]),
            )
            return str(row["id"])

    def _emit(self, connection: sqlite3.Connection, chart_id: str, event: str, payload: dict[str, Any]) -> int:
        cursor = connection.execute(
            "INSERT INTO outbox_events (chart_id, event, payload_json, created_at) VALUES (?, ?, ?, ?)",
            (chart_id, event, _json_dump(payload), _iso()),
        )
        return int(cursor.lastrowid)

    def emit(self, chart_id: str, event: str, payload: dict[str, Any]) -> int:
        with self._lock, self._connection() as connection:
            return self._emit(connection, chart_id, event, payload)

    def events_since(self, chart_id: str, last_id: int = 0) -> list[ChartEvent]:
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM outbox_events WHERE chart_id = ? AND id > ? ORDER BY id ASC",
                (chart_id, last_id),
            ).fetchall()
        return [
            ChartEvent(
                id=int(row["id"]),
                event=str(row["event"]),
                data=_json_load(row["payload_json"], {}),
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def create_purchase(self, chart_id: str, idempotency_key: str, email: str | None) -> tuple[dict[str, Any], bool]:
        with self._lock, self._connection() as connection:
            existing = connection.execute(
                "SELECT * FROM purchases WHERE chart_id = ? AND idempotency_key = ?", (chart_id, idempotency_key)
            ).fetchone()
            if existing:
                return dict(existing), False
            now = _iso()
            purchase = {
                "id": self._new_id("pur"),
                "chart_id": chart_id,
                "idempotency_key": idempotency_key,
                "provider": "test" if os.environ.get("VEDICWAY_TEST_PAYMENTS") == "1" else "pending_provider",
                "provider_payment_id": None,
                "status": "pending",
                "amount_minor": 99000,
                "currency": "RUB",
                "created_at": now,
                "updated_at": now,
            }
            connection.execute(
                """INSERT INTO purchases
                   (id, chart_id, idempotency_key, email_ciphertext, provider, provider_payment_id, status, amount_minor, currency, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    purchase["id"], chart_id, idempotency_key, self._encrypt({"email": email}) if email else None,
                    purchase["provider"], None, purchase["status"], purchase["amount_minor"], purchase["currency"], now, now,
                ),
            )
            self._emit(connection, chart_id, "payment.pending", {"purchase_id": purchase["id"]})
            return purchase, True

    def get_purchase(self, purchase_id: str) -> dict[str, Any] | None:
        with self._lock, self._connection() as connection:
            row = connection.execute("SELECT * FROM purchases WHERE id = ?", (purchase_id,)).fetchone()
            return dict(row) if row else None

    def set_provider_payment(self, purchase_id: str, provider: str, provider_payment_id: str | None) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                "UPDATE purchases SET provider = ?, provider_payment_id = ?, updated_at = ? WHERE id = ?",
                (provider, provider_payment_id, _iso(), purchase_id),
            )

    def confirm_purchase(self, purchase_id: str, provider_event_id: str) -> str | None:
        """Idempotent payment transition used only by a verified provider webhook/test adapter."""
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                purchase = connection.execute("SELECT * FROM purchases WHERE id = ?", (purchase_id,)).fetchone()
                if not purchase:
                    connection.rollback()
                    return None
                event_checksum = hashlib.sha256(provider_event_id.encode("utf-8")).hexdigest()
                duplicate = connection.execute(
                    "SELECT 1 FROM payment_events WHERE provider = ? AND provider_event_id = ?",
                    (purchase["provider"], provider_event_id),
                ).fetchone()
                if duplicate:
                    connection.commit()
                    return str(purchase["chart_id"])
                now = _iso()
                connection.execute(
                    "INSERT INTO payment_events (provider, provider_event_id, payload_checksum, received_at) VALUES (?, ?, ?, ?)",
                    (purchase["provider"], provider_event_id, event_checksum, now),
                )
                connection.execute("UPDATE purchases SET status = 'paid', updated_at = ? WHERE id = ?", (now, purchase_id))
                connection.execute(
                    """INSERT OR IGNORE INTO entitlements (id, chart_id, product_code, purchase_id, granted_at)
                       VALUES (?, ?, 'report_full', ?, ?)""",
                    (self._new_id("ent"), purchase["chart_id"], purchase_id, now),
                )
                self._emit(connection, purchase["chart_id"], "entitlement.granted", {"product": "report_full"})
                self._enqueue(connection, purchase["chart_id"], "paid_report_v1", priority=90)
                connection.commit()
                return str(purchase["chart_id"])
            except Exception:
                connection.rollback()
                raise

    def has_entitlement(self, chart_id: str) -> bool:
        with self._lock, self._connection() as connection:
            return connection.execute(
                "SELECT 1 FROM entitlements WHERE chart_id = ? AND product_code = 'report_full'", (chart_id,)
            ).fetchone() is not None

    def save_question(self, chart_id: str, question_id: str, saved: bool, note: str | None, reflection_status: str = "saved") -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                """INSERT INTO saved_questions (chart_id, question_id, saved, reflection_status, note_ciphertext, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(chart_id, question_id) DO UPDATE SET saved = excluded.saved, reflection_status = excluded.reflection_status, note_ciphertext = excluded.note_ciphertext, updated_at = excluded.updated_at""",
                (chart_id, question_id, int(saved), reflection_status, self._encrypt({"note": note}) if note else None, _iso()),
            )

    def saved_questions(self, chart_id: str) -> list[dict[str, Any]]:
        with self._lock, self._connection() as connection:
            rows = connection.execute("SELECT * FROM saved_questions WHERE chart_id = ?", (chart_id,)).fetchall()
        return [
            {
                "question_id": row["question_id"],
                "saved": bool(row["saved"]),
                "reflection_status": row["reflection_status"] or "saved",
                "note": self._decrypt(row["note_ciphertext"]).get("note") if row["note_ciphertext"] else None,
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def upsert_report(
        self,
        chart_id: str,
        status: str,
        path: str | None = None,
        checksum: str | None = None,
        size_bytes: int | None = None,
        pages: int | None = None,
        error_code: str | None = None,
    ) -> None:
        now = _iso()
        with self._lock, self._connection() as connection:
            connection.execute(
                """INSERT INTO reports (id, chart_id, status, path, checksum, size_bytes, pages, error_code, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(chart_id) DO UPDATE SET status = excluded.status, path = excluded.path, checksum = excluded.checksum,
                   size_bytes = excluded.size_bytes, pages = excluded.pages, error_code = excluded.error_code, updated_at = excluded.updated_at""",
                (self._new_id("rpt"), chart_id, status, path, checksum, size_bytes, pages, error_code, now, now),
            )

    def commit_report_event(self, chart_id: str, status: str, payload: dict[str, Any], **report: Any) -> None:
        now = _iso()
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """INSERT INTO reports (id, chart_id, status, path, checksum, size_bytes, pages, error_code, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(chart_id) DO UPDATE SET status = excluded.status, path = excluded.path, checksum = excluded.checksum,
                       size_bytes = excluded.size_bytes, pages = excluded.pages, error_code = excluded.error_code, updated_at = excluded.updated_at""",
                    (
                        self._new_id("rpt"), chart_id, status, report.get("path"), report.get("checksum"), report.get("size_bytes"),
                        report.get("pages"), report.get("error_code"), now, now,
                    ),
                )
                self._emit(connection, chart_id, "pdf.ready" if status == "ready" else "job.failed", payload)
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def get_report(self, chart_id: str) -> dict[str, Any]:
        with self._lock, self._connection() as connection:
            row = connection.execute("SELECT * FROM reports WHERE chart_id = ?", (chart_id,)).fetchone()
        if not row:
            return {"status": "locked" if not self.has_entitlement(chart_id) else "generating"}
        return {
            "status": row["status"],
            "pages": row["pages"],
            "size_bytes": row["size_bytes"],
            "error_code": row["error_code"],
            "download_url": None,
        }

    def report_file_path(self, chart_id: str) -> Path | None:
        with self._lock, self._connection() as connection:
            row = connection.execute("SELECT path FROM reports WHERE chart_id = ? AND status = 'ready'", (chart_id,)).fetchone()
        return Path(row["path"]) if row and row["path"] else None

    def issue_download_token(self, chart_id: str, ttl_minutes: int = 10) -> str:
        expires = int((_utc_now() + timedelta(minutes=ttl_minutes)).timestamp())
        payload = f"{chart_id}.{expires}".encode("utf-8")
        signature = hmac.new(self._signing_key, payload, hashlib.sha256).hexdigest()
        return base64.urlsafe_b64encode(payload + b"." + signature.encode("ascii")).decode("ascii")

    def validate_download_token(self, token: str, chart_id: str) -> bool:
        try:
            decoded = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
            encoded_payload, signature = decoded.rsplit(".", 1)
            token_chart_id, expires = encoded_payload.rsplit(".", 1)
            expected = hmac.new(self._signing_key, encoded_payload.encode("utf-8"), hashlib.sha256).hexdigest()
            return token_chart_id == chart_id and int(expires) >= int(_utc_now().timestamp()) and hmac.compare_digest(signature, expected)
        except (ValueError, UnicodeDecodeError):
            return False

    def create_magic_link(self, chart_id: str, ttl_hours: int = 24) -> str:
        token = secrets.token_urlsafe(32)
        expires = _utc_now() + timedelta(hours=ttl_hours)
        with self._lock, self._connection() as connection:
            connection.execute(
                "INSERT INTO magic_links (token_hash, chart_id, scope, expires_at, created_at) VALUES (?, ?, 'read_chart', ?, ?)",
                (self._token_hash(token), chart_id, _iso(expires), _iso()),
            )
        return token

    def redeem_magic_link(self, token: str) -> str | None:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM magic_links WHERE token_hash = ?", (self._token_hash(token),)
            ).fetchone()
            if not row or row["used_at"] or datetime.fromisoformat(row["expires_at"]) < _utc_now():
                return None
            chart = connection.execute("SELECT id FROM charts WHERE id = ?", (row["chart_id"],)).fetchone()
            if not chart:
                return None
            connection.execute("UPDATE magic_links SET used_at = ? WHERE token_hash = ?", (_iso(), row["token_hash"]))
            return str(chart["id"])
