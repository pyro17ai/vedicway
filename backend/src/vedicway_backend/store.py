from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet

from .errors import DomainError
from .schemas import (
    BirthInput,
    ChartEvent,
    ChartSnapshot,
    InterpretationBundle,
    JobStatus,
)


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

    _PUBLIC_BIRTH_PREFIX = "fernet:v1:"

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
            key = configured.encode("utf-8")
            if os.environ.get("VEDICWAY_ENV") == "production" and len(key) < 32:
                raise RuntimeError("VEDICWAY_SIGNING_KEY must contain at least 32 bytes in production")
            return key
        if os.environ.get("VEDICWAY_ENV") == "production":
            raise RuntimeError("VEDICWAY_SIGNING_KEY is required in production")
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
          created_at TEXT NOT NULL,
          deleted_at TEXT
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
          soft_deleted_at TEXT,
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
          payload_json TEXT,
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
          email_lookup_hmac TEXT,
          product_code TEXT NOT NULL DEFAULT 'full_report_v1',
          provider TEXT NOT NULL,
          provider_idempotency_key TEXT,
          provider_payment_id TEXT,
          checkout_url TEXT,
          status TEXT NOT NULL,
          provider_status TEXT,
          provider_payload_json TEXT,
          failure_code TEXT,
          amount_minor INTEGER NOT NULL,
          paid_amount_minor INTEGER,
          refunded_amount_minor INTEGER NOT NULL DEFAULT 0,
          currency TEXT NOT NULL,
          offer_version TEXT,
          last_reconciled_at TEXT,
          paid_at TEXT,
          canceled_at TEXT,
          receipt_registration TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(chart_id, idempotency_key)
        );
        CREATE TABLE IF NOT EXISTS payment_events (
          provider TEXT NOT NULL,
          provider_event_id TEXT NOT NULL,
          event_type TEXT,
          object_id TEXT,
          payload_checksum TEXT NOT NULL,
          received_at TEXT NOT NULL,
          PRIMARY KEY(provider, provider_event_id)
        );
        CREATE TABLE IF NOT EXISTS payment_incidents (
          id TEXT PRIMARY KEY,
          purchase_id TEXT REFERENCES purchases(id),
          category TEXT NOT NULL,
          detail_json TEXT NOT NULL,
          trace_id TEXT,
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS payment_incidents_purchase_idx
          ON payment_incidents(purchase_id, created_at);
        CREATE TABLE IF NOT EXISTS entitlements (
          id TEXT PRIMARY KEY,
          chart_id TEXT NOT NULL REFERENCES charts(id),
          product_code TEXT NOT NULL,
          purchase_id TEXT REFERENCES purchases(id),
          granted_at TEXT NOT NULL,
          revoked_at TEXT,
          revocation_reason TEXT,
          UNIQUE(chart_id, product_code)
        );
        CREATE TABLE IF NOT EXISTS refunds (
          id TEXT PRIMARY KEY,
          purchase_id TEXT NOT NULL REFERENCES purchases(id),
          idempotency_key TEXT NOT NULL,
          provider_idempotency_key TEXT NOT NULL,
          provider_refund_id TEXT,
          status TEXT NOT NULL,
          amount_minor INTEGER NOT NULL,
          currency TEXT NOT NULL,
          reason_ciphertext BLOB,
          actor_fingerprint TEXT NOT NULL,
          failure_code TEXT,
          receipt_registration TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(purchase_id, idempotency_key),
          UNIQUE(provider_idempotency_key),
          UNIQUE(provider_refund_id)
        );
        CREATE INDEX IF NOT EXISTS refunds_purchase_idx ON refunds(purchase_id, status, created_at);
        CREATE TABLE IF NOT EXISTS payment_operations (
          id TEXT PRIMARY KEY,
          action TEXT NOT NULL,
          purchase_id TEXT REFERENCES purchases(id),
          refund_id TEXT REFERENCES refunds(id),
          actor_fingerprint TEXT NOT NULL,
          source_ip TEXT NOT NULL,
          trace_id TEXT NOT NULL,
          reason_ciphertext BLOB,
          amount_minor INTEGER,
          result TEXT NOT NULL,
          detail_json TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS payment_operations_purchase_idx
          ON payment_operations(purchase_id, created_at);
        CREATE TABLE IF NOT EXISTS reports (
          id TEXT PRIMARY KEY,
          chart_id TEXT NOT NULL REFERENCES charts(id),
          status TEXT NOT NULL,
          path TEXT,
          checksum TEXT,
          size_bytes INTEGER,
          pages INTEGER,
          error_code TEXT,
          render_request_id TEXT,
          preferences_checksum TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(chart_id)
        );
        CREATE TABLE IF NOT EXISTS pdf_render_requests (
          id TEXT PRIMARY KEY,
          chart_id TEXT NOT NULL REFERENCES charts(id),
          job_id TEXT,
          preferences_json TEXT NOT NULL,
          preferences_checksum TEXT NOT NULL,
          status TEXT NOT NULL,
          path TEXT,
          checksum TEXT,
          size_bytes INTEGER,
          pages INTEGER,
          error_code TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS pdf_render_requests_chart_idx ON pdf_render_requests(chart_id, created_at DESC);
        CREATE TABLE IF NOT EXISTS rate_limit_events (
          bucket_key TEXT NOT NULL,
          occurred_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS rate_limit_events_bucket_idx
          ON rate_limit_events(bucket_key, occurred_at);
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
          render_request_id TEXT,
          expires_at TEXT NOT NULL,
          used_at TEXT,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS magic_link_confirmations (
          nonce_hash TEXT PRIMARY KEY,
          magic_token_hash TEXT NOT NULL REFERENCES magic_links(token_hash) ON DELETE CASCADE,
          csrf_token_hash TEXT NOT NULL,
          expires_at TEXT NOT NULL,
          used_at TEXT,
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS magic_link_confirmations_token_idx
          ON magic_link_confirmations(magic_token_hash, created_at DESC);
        CREATE TABLE IF NOT EXISTS privacy_requests (
          id TEXT PRIMARY KEY,
          request_type TEXT NOT NULL,
          email_lookup_hmac TEXT NOT NULL,
          email_ciphertext BLOB NOT NULL,
          status TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS privacy_requests_lookup_idx
          ON privacy_requests(email_lookup_hmac, created_at DESC);
        CREATE TABLE IF NOT EXISTS erasure_tombstones (
          chart_id TEXT PRIMARY KEY,
          reason TEXT NOT NULL,
          financial_records_retained INTEGER NOT NULL,
          report_paths_json TEXT NOT NULL,
          status TEXT NOT NULL,
          created_at TEXT NOT NULL,
          files_deleted_at TEXT,
          last_error_code TEXT
        );
        CREATE TABLE IF NOT EXISTS retention_runs (
          id TEXT PRIMARY KEY,
          mode TEXT NOT NULL,
          cutoff_at TEXT NOT NULL,
          candidates INTEGER NOT NULL,
          erased INTEGER NOT NULL,
          failed INTEGER NOT NULL,
          detail_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          finished_at TEXT
        );
        CREATE TABLE IF NOT EXISTS email_deliveries (
          id TEXT PRIMARY KEY,
          purpose TEXT NOT NULL,
          request_key TEXT NOT NULL UNIQUE,
          email_lookup_hmac TEXT,
          purchase_id TEXT REFERENCES purchases(id),
          chart_id TEXT REFERENCES charts(id),
          render_request_id TEXT,
          status TEXT NOT NULL,
          attempts INTEGER NOT NULL DEFAULT 0,
          scheduled_at TEXT NOT NULL,
          provider_message_id TEXT,
          error_code TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS email_deliveries_queue_idx
          ON email_deliveries(status, scheduled_at, created_at);
        """
        with self._lock, self._connection() as connection:
            connection.executescript(statements)
            self._ensure_columns(
                connection,
                "saved_questions",
                {"reflection_status": "TEXT NOT NULL DEFAULT 'saved'"},
            )
            self._ensure_columns(
                connection,
                "purchases",
                {
                    "email_lookup_hmac": "TEXT",
                    "product_code": "TEXT NOT NULL DEFAULT 'full_report_v1'",
                    "provider_idempotency_key": "TEXT",
                    "checkout_url": "TEXT",
                    "provider_status": "TEXT",
                    "provider_payload_json": "TEXT",
                    "failure_code": "TEXT",
                    "paid_amount_minor": "INTEGER",
                    "refunded_amount_minor": "INTEGER NOT NULL DEFAULT 0",
                    "offer_version": "TEXT",
                    "last_reconciled_at": "TEXT",
                    "paid_at": "TEXT",
                    "canceled_at": "TEXT",
                    "receipt_registration": "TEXT",
                },
            )
            self._ensure_columns(connection, "birth_profiles", {"deleted_at": "TEXT"})
            self._ensure_columns(connection, "charts", {"soft_deleted_at": "TEXT"})
            self._ensure_columns(connection, "magic_links", {"render_request_id": "TEXT"})
            self._ensure_columns(
                connection,
                "payment_events",
                {"event_type": "TEXT", "object_id": "TEXT"},
            )
            self._ensure_columns(
                connection,
                "entitlements",
                {"revoked_at": "TEXT", "revocation_reason": "TEXT"},
            )
            self._ensure_columns(
                connection,
                "jobs",
                {"payload_json": "TEXT"},
            )
            self._ensure_columns(
                connection,
                "reports",
                {"render_request_id": "TEXT", "preferences_checksum": "TEXT"},
            )
            self._ensure_columns(
                connection,
                "pdf_render_requests",
                {
                    "path": "TEXT",
                    "checksum": "TEXT",
                    "size_bytes": "INTEGER",
                    "pages": "INTEGER",
                    "error_code": "TEXT",
                },
            )
            connection.execute(
                """UPDATE pdf_render_requests
                   SET path = COALESCE(path, (SELECT reports.path FROM reports WHERE reports.render_request_id = pdf_render_requests.id)),
                       checksum = COALESCE(checksum, (SELECT reports.checksum FROM reports WHERE reports.render_request_id = pdf_render_requests.id)),
                       size_bytes = COALESCE(size_bytes, (SELECT reports.size_bytes FROM reports WHERE reports.render_request_id = pdf_render_requests.id)),
                       pages = COALESCE(pages, (SELECT reports.pages FROM reports WHERE reports.render_request_id = pdf_render_requests.id)),
                       error_code = COALESCE(error_code, (SELECT reports.error_code FROM reports WHERE reports.render_request_id = pdf_render_requests.id))
                   WHERE EXISTS (SELECT 1 FROM reports WHERE reports.render_request_id = pdf_render_requests.id)"""
            )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS purchases_provider_key_idx ON purchases(provider, provider_idempotency_key)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS purchases_active_idx ON purchases(chart_id, product_code, status, created_at)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS purchases_email_lookup_idx ON purchases(email_lookup_hmac)"
            )
            connection.execute(
                "INSERT OR IGNORE INTO chart_access (chart_id, session_id, granted_at) SELECT id, session_id, created_at FROM charts"
            )
            self._backfill_purchase_email_hmacs(connection)
            self._migrate_public_birth_payloads(connection)

    @staticmethod
    def _ensure_columns(
        connection: sqlite3.Connection,
        table: str,
        columns: dict[str, str],
    ) -> None:
        existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
        for name, definition in columns.items():
            if name not in existing:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def normalize_email(email: str) -> str:
        return email.strip().casefold()

    def email_lookup_hmac(self, email: str) -> str:
        normalized = self.normalize_email(email).encode("utf-8")
        return hmac.new(self._signing_key, b"email-lookup-v1:" + normalized, hashlib.sha256).hexdigest()

    def _backfill_purchase_email_hmacs(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            "SELECT id, email_ciphertext FROM purchases WHERE email_lookup_hmac IS NULL AND email_ciphertext IS NOT NULL"
        ).fetchall()
        for row in rows:
            try:
                email = str(self._decrypt(row["email_ciphertext"]).get("email") or "")
            except Exception:
                continue
            if email:
                connection.execute(
                    "UPDATE purchases SET email_lookup_hmac = ? WHERE id = ?",
                    (self.email_lookup_hmac(email), row["id"]),
                )

    def record_rate_limit_hit(self, bucket_key: str, limit: int, window_seconds: int) -> int:
        """Atomically record one hit and return retry seconds when the bucket is full."""
        now = time.time()
        cutoff = now - window_seconds
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "DELETE FROM rate_limit_events WHERE bucket_key = ? AND occurred_at <= ?",
                    (bucket_key, cutoff),
                )
                row = connection.execute(
                    """SELECT COUNT(*) AS hits, MIN(occurred_at) AS oldest
                       FROM rate_limit_events WHERE bucket_key = ?""",
                    (bucket_key,),
                ).fetchone()
                if row and int(row["hits"]) >= limit:
                    retry_after = max(1, int(float(row["oldest"]) + window_seconds - now) + 1)
                    connection.commit()
                    return retry_after
                connection.execute(
                    "INSERT INTO rate_limit_events (bucket_key, occurred_at) VALUES (?, ?)",
                    (bucket_key, now),
                )
                connection.commit()
                return 0
            except Exception:
                connection.rollback()
                raise

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

    def _encode_public_birth(self, value: Any) -> str:
        return self._PUBLIC_BIRTH_PREFIX + self._encrypt(value).decode("ascii")

    def _decode_public_birth(self, value: str | None) -> Any:
        if not value:
            return {}
        if value.startswith(self._PUBLIC_BIRTH_PREFIX):
            return self._decrypt(value.removeprefix(self._PUBLIC_BIRTH_PREFIX))
        # Compatibility path for databases created before public birth fields
        # were encrypted. Startup rewrites every such row in one transaction.
        return _json_load(value, {})

    def _migrate_public_birth_payloads(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute("SELECT id, birth_public_json FROM charts").fetchall()
        legacy = [row for row in rows if not str(row["birth_public_json"]).startswith(self._PUBLIC_BIRTH_PREFIX)]
        if not legacy:
            return
        connection.execute("BEGIN IMMEDIATE")
        try:
            for row in legacy:
                payload = _json_load(str(row["birth_public_json"]), {})
                connection.execute(
                    "UPDATE charts SET birth_public_json = ? WHERE id = ?",
                    (self._encode_public_birth(payload), row["id"]),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

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
        *,
        activate: bool = True,
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
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        chart_id,
                        session_id,
                        profile_id,
                        idempotency_key,
                        "accepted" if activate else "awaiting_consent",
                        self._encode_public_birth(public_birth),
                        now,
                        now,
                    ),
                )
                connection.execute(
                    "INSERT INTO chart_access (chart_id, session_id, granted_at) VALUES (?, ?, ?)",
                    (chart_id, session_id, now),
                )
                if activate:
                    self._enqueue(connection, chart_id, "instant_v1", priority=100)
                    self._emit(
                        connection,
                        chart_id,
                        "chart.accepted",
                        {"chart_id": chart_id, "accepted_at": now},
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return chart_id, True

    def activate_chart_after_consent(self, chart_id: str) -> bool:
        """Make a consent-pending chart visible to the calculation queue exactly once."""
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                chart = connection.execute(
                    "SELECT status FROM charts WHERE id = ?", (chart_id,)
                ).fetchone()
                if not chart:
                    raise RuntimeError("Consent-pending chart no longer exists")
                existing_job = connection.execute(
                    "SELECT 1 FROM jobs WHERE chart_id = ? AND job_type = 'instant_v1' LIMIT 1",
                    (chart_id,),
                ).fetchone()
                if chart["status"] == "awaiting_consent":
                    now = _iso()
                    connection.execute(
                        "UPDATE charts SET status = 'accepted', updated_at = ? WHERE id = ?",
                        (now, chart_id),
                    )
                    if not existing_job:
                        self._enqueue(connection, chart_id, "instant_v1", priority=100)
                        self._emit(
                            connection,
                            chart_id,
                            "chart.accepted",
                            {"chart_id": chart_id, "accepted_at": now},
                        )
                    connection.commit()
                    return True
                connection.commit()
                return False
            except Exception:
                connection.rollback()
                raise

    def discard_chart_awaiting_consent(
        self,
        chart_id: str,
        session_id: str,
        idempotency_key: str,
    ) -> bool:
        """Remove every runtime artifact for a chart that never passed consent audit."""
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                chart = connection.execute(
                    """SELECT birth_profile_id FROM charts
                       WHERE id = ? AND session_id = ? AND idempotency_key = ?
                         AND status = 'awaiting_consent'""",
                    (chart_id, session_id, idempotency_key),
                ).fetchone()
                if not chart:
                    connection.rollback()
                    return False
                connection.execute("DELETE FROM chart_access WHERE chart_id = ?", (chart_id,))
                connection.execute("DELETE FROM outbox_events WHERE chart_id = ?", (chart_id,))
                connection.execute("DELETE FROM jobs WHERE chart_id = ?", (chart_id,))
                connection.execute("DELETE FROM charts WHERE id = ?", (chart_id,))
                connection.execute(
                    "DELETE FROM birth_profiles WHERE id = ?", (chart["birth_profile_id"],)
                )
                connection.commit()
                return True
            except Exception:
                connection.rollback()
                raise

    def chart_owned_by(self, chart_id: str, session_id: str) -> bool:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                """SELECT 1 FROM chart_access
                   JOIN charts ON charts.id = chart_access.chart_id
                   WHERE chart_access.chart_id = ? AND chart_access.session_id = ?
                     AND charts.soft_deleted_at IS NULL""",
                (chart_id, session_id),
            ).fetchone()
            return row is not None

    def grant_chart_access(self, chart_id: str, session_id: str) -> None:
        with self._lock, self._connection() as connection:
            chart = connection.execute(
                "SELECT 1 FROM charts WHERE id = ? AND soft_deleted_at IS NULL", (chart_id,)
            ).fetchone()
            if chart:
                connection.execute(
                    "INSERT OR IGNORE INTO chart_access (chart_id, session_id, granted_at) VALUES (?, ?, ?)",
                    (chart_id, session_id, _iso()),
                )

    def get_birth(self, chart_id: str) -> BirthInput:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                """SELECT birth_profiles.encrypted_payload FROM charts
                   JOIN birth_profiles ON birth_profiles.id = charts.birth_profile_id
                   WHERE charts.id = ? AND charts.soft_deleted_at IS NULL""",
                (chart_id,),
            ).fetchone()
        if not row:
            raise LookupError(chart_id)
        return BirthInput.model_validate(self._decrypt(row["encrypted_payload"]))

    def _get_chart_row(self, chart_id: str) -> sqlite3.Row:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM charts WHERE id = ? AND soft_deleted_at IS NULL", (chart_id,)
            ).fetchone()
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
            "birth": self._decode_public_birth(row["birth_public_json"]),
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

    def _enqueue(
        self,
        connection: sqlite3.Connection,
        chart_id: str,
        job_type: str,
        priority: int = 10,
        payload: dict[str, Any] | None = None,
    ) -> str:
        now = _iso()
        job_id = self._new_id("job")
        connection.execute(
            """INSERT INTO jobs (id, chart_id, job_type, status, priority, payload_json, scheduled_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (job_id, chart_id, job_type, JobStatus.QUEUED.value, priority, _json_dump(payload) if payload else None, now, now, now),
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

    def enqueue_pdf_job(self, chart_id: str, preferences: dict[str, Any], priority: int = 60) -> tuple[str, str]:
        """Create an immutable preference snapshot for one explicit PDF render."""
        raw_preferences = _json_dump(preferences)
        checksum = f"sha256:{hashlib.sha256(raw_preferences.encode('utf-8')).hexdigest()}"
        now = _iso()
        request_id = self._new_id("pdfreq")
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """UPDATE pdf_render_requests
                       SET path = COALESCE(path, (SELECT reports.path FROM reports WHERE reports.render_request_id = pdf_render_requests.id)),
                           checksum = COALESCE(checksum, (SELECT reports.checksum FROM reports WHERE reports.render_request_id = pdf_render_requests.id)),
                           size_bytes = COALESCE(size_bytes, (SELECT reports.size_bytes FROM reports WHERE reports.render_request_id = pdf_render_requests.id)),
                           pages = COALESCE(pages, (SELECT reports.pages FROM reports WHERE reports.render_request_id = pdf_render_requests.id)),
                           error_code = COALESCE(error_code, (SELECT reports.error_code FROM reports WHERE reports.render_request_id = pdf_render_requests.id))
                       WHERE id = (SELECT render_request_id FROM reports WHERE chart_id = ?)""",
                    (chart_id,),
                )
                connection.execute(
                    """INSERT INTO pdf_render_requests
                       (id, chart_id, preferences_json, preferences_checksum, status, created_at, updated_at)
                       VALUES (?, ?, ?, ?, 'queued', ?, ?)""",
                    (request_id, chart_id, raw_preferences, checksum, now, now),
                )
                job_id = self._enqueue(
                    connection,
                    chart_id,
                    "pdf_v1",
                    priority,
                    {"render_request_id": request_id},
                )
                connection.execute(
                    "UPDATE pdf_render_requests SET job_id = ?, updated_at = ? WHERE id = ?",
                    (job_id, now, request_id),
                )
                connection.execute(
                    """INSERT INTO reports
                       (id, chart_id, status, render_request_id, preferences_checksum, created_at, updated_at)
                       VALUES (?, ?, 'generating', ?, ?, ?, ?)
                       ON CONFLICT(chart_id) DO UPDATE SET
                         status = 'generating', path = NULL, checksum = NULL, size_bytes = NULL,
                         pages = NULL, error_code = NULL, render_request_id = excluded.render_request_id,
                         preferences_checksum = excluded.preferences_checksum, updated_at = excluded.updated_at""",
                    (self._new_id("rpt"), chart_id, request_id, checksum, now, now),
                )
                self._emit(connection, chart_id, "pdf.started", {"render_request_id": request_id, "preferences": preferences})
                connection.commit()
                return job_id, request_id
            except Exception:
                connection.rollback()
                raise

    def get_pdf_render_request(self, request_id: str) -> dict[str, Any] | None:
        with self._lock, self._connection() as connection:
            row = connection.execute("SELECT * FROM pdf_render_requests WHERE id = ?", (request_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        result["preferences"] = _json_load(result.pop("preferences_json"), {})
        return result

    def update_pdf_render_request(self, request_id: str, status: str) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                "UPDATE pdf_render_requests SET status = ?, updated_at = ? WHERE id = ?",
                (status, _iso(), request_id),
            )

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

    def create_purchase(
        self,
        chart_id: str,
        idempotency_key: str,
        email: str | None,
        *,
        product_code: str = "full_report_v1",
        provider: str | None = None,
        offer_version: str | None = None,
        amount_minor: int = 99_000,
        currency: str = "RUB",
    ) -> tuple[dict[str, Any], bool]:
        """Create one durable checkout attempt before calling a payment provider.

        The client key deduplicates retries. A second key still reuses an unfinished
        attempt for the same chart and product, so a double click cannot create two
        YooKassa payments.
        """
        selected_provider = provider or (
            "test" if os.environ.get("VEDICWAY_TEST_PAYMENTS") == "1" else "pending_provider"
        )
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute(
                    "SELECT * FROM purchases WHERE chart_id = ? AND idempotency_key = ?",
                    (chart_id, idempotency_key),
                ).fetchone()
                if existing:
                    connection.commit()
                    return dict(existing), False
                active = connection.execute(
                    """SELECT * FROM purchases
                       WHERE chart_id = ? AND product_code = ? AND status IN ('created', 'pending', 'unknown')
                       ORDER BY created_at DESC LIMIT 1""",
                    (chart_id, product_code),
                ).fetchone()
                if active:
                    connection.commit()
                    return dict(active), False
                now = _iso()
                purchase = {
                    "id": self._new_id("pur"),
                    "chart_id": chart_id,
                    "idempotency_key": idempotency_key,
                    "product_code": product_code,
                    "provider": selected_provider,
                    "provider_idempotency_key": secrets.token_urlsafe(32),
                    "provider_payment_id": None,
                    "checkout_url": None,
                    "status": "created",
                    "provider_status": None,
                    "amount_minor": amount_minor,
                    "paid_amount_minor": None,
                    "refunded_amount_minor": 0,
                    "currency": currency.upper(),
                    "offer_version": offer_version,
                    "created_at": now,
                    "updated_at": now,
                }
                connection.execute(
                    """INSERT INTO purchases
                       (id, chart_id, idempotency_key, email_ciphertext, email_lookup_hmac, product_code, provider,
                        provider_idempotency_key, provider_payment_id, checkout_url, status,
                        provider_status, amount_minor, paid_amount_minor, refunded_amount_minor,
                        currency, offer_version, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        purchase["id"], chart_id, idempotency_key,
                        self._encrypt({"email": email}) if email else None,
                        self.email_lookup_hmac(email) if email else None,
                        product_code, selected_provider, purchase["provider_idempotency_key"], None,
                        None, purchase["status"], None, amount_minor, None, 0,
                        purchase["currency"], offer_version, now, now,
                    ),
                )
                self._emit(connection, chart_id, "payment.pending", {"purchase_id": purchase["id"]})
                connection.commit()
                return purchase, True
            except Exception:
                connection.rollback()
                raise

    def get_purchase(self, purchase_id: str) -> dict[str, Any] | None:
        with self._lock, self._connection() as connection:
            row = connection.execute("SELECT * FROM purchases WHERE id = ?", (purchase_id,)).fetchone()
            return dict(row) if row else None

    def get_purchase_email(self, purchase_id: str) -> str | None:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT email_ciphertext FROM purchases WHERE id = ?", (purchase_id,)
            ).fetchone()
        if not row:
            raise LookupError(purchase_id)
        if not row["email_ciphertext"]:
            return None
        return self._decrypt(row["email_ciphertext"]).get("email")

    def create_privacy_request(self, request_type: str, email: str) -> str:
        if request_type not in {"access", "erase", "withdraw"}:
            raise ValueError("unsupported privacy request type")
        request_id = self._new_id("privacy")
        now = _iso()
        with self._lock, self._connection() as connection:
            connection.execute(
                """INSERT INTO privacy_requests
                   (id, request_type, email_lookup_hmac, email_ciphertext, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'received', ?, ?)""",
                (
                    request_id,
                    request_type,
                    self.email_lookup_hmac(email),
                    self._encrypt({"email": self.normalize_email(email)}),
                    now,
                    now,
                ),
            )
        return request_id

    def enqueue_access_recovery(self, email: str) -> str:
        delivery_id = self._new_id("mail")
        now = _iso()
        with self._lock, self._connection() as connection:
            connection.execute(
                """INSERT INTO email_deliveries
                   (id, purpose, request_key, email_lookup_hmac, status, scheduled_at, created_at, updated_at)
                   VALUES (?, 'access_recovery', ?, ?, 'queued', ?, ?, ?)""",
                (
                    delivery_id,
                    f"access-recovery:{secrets.token_urlsafe(24)}",
                    self.email_lookup_hmac(email),
                    now,
                    now,
                    now,
                ),
            )
        return delivery_id

    def enqueue_purchase_ready_email(self, chart_id: str, render_request_id: str) -> str | None:
        now = _iso()
        with self._lock, self._connection() as connection:
            purchase = connection.execute(
                """SELECT id FROM purchases
                   WHERE chart_id = ? AND status IN ('succeeded', 'partially_refunded')
                     AND email_ciphertext IS NOT NULL
                   ORDER BY paid_at DESC, created_at DESC LIMIT 1""",
                (chart_id,),
            ).fetchone()
            if not purchase:
                return None
            delivery_id = self._new_id("mail")
            cursor = connection.execute(
                """INSERT OR IGNORE INTO email_deliveries
                   (id, purpose, request_key, purchase_id, chart_id, render_request_id,
                    status, scheduled_at, created_at, updated_at)
                   VALUES (?, 'purchase_ready', ?, ?, ?, ?, 'queued', ?, ?, ?)""",
                (
                    delivery_id,
                    f"purchase-ready:{purchase['id']}",
                    purchase["id"],
                    chart_id,
                    render_request_id,
                    now,
                    now,
                    now,
                ),
            )
            return delivery_id if cursor.rowcount else None

    def claim_next_email_delivery(self) -> dict[str, Any] | None:
        now = _utc_now()
        stale = _iso(now - timedelta(minutes=15))
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """UPDATE email_deliveries SET status = 'queued', updated_at = ?
                       WHERE status = 'sending' AND updated_at < ? AND attempts < 3""",
                    (_iso(now), stale),
                )
                row = connection.execute(
                    """SELECT * FROM email_deliveries
                       WHERE status = 'queued' AND scheduled_at <= ? AND attempts < 3
                       ORDER BY created_at, id LIMIT 1""",
                    (_iso(now),),
                ).fetchone()
                if not row:
                    connection.commit()
                    return None
                connection.execute(
                    """UPDATE email_deliveries
                       SET status = 'sending', attempts = attempts + 1, updated_at = ? WHERE id = ?""",
                    (_iso(now), row["id"]),
                )
                claimed = connection.execute(
                    "SELECT * FROM email_deliveries WHERE id = ?", (row["id"],)
                ).fetchone()
                connection.commit()
                return dict(claimed)
            except Exception:
                connection.rollback()
                raise

    def finish_email_delivery(
        self,
        delivery_id: str,
        *,
        status: str,
        provider_message_id: str | None = None,
        error_code: str | None = None,
        retryable: bool = False,
    ) -> None:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT attempts FROM email_deliveries WHERE id = ?", (delivery_id,)
            ).fetchone()
            if not row:
                return
            attempts = int(row["attempts"])
            if retryable and attempts < 3:
                next_status = "queued"
                scheduled_at = _iso(_utc_now() + timedelta(seconds=min(900, 60 * (2 ** attempts))))
            else:
                next_status = status
                scheduled_at = _iso()
            connection.execute(
                """UPDATE email_deliveries
                   SET status = ?, scheduled_at = ?, provider_message_id = ?, error_code = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    next_status,
                    scheduled_at,
                    provider_message_id,
                    error_code,
                    _iso(),
                    delivery_id,
                ),
            )

    def recovery_targets(self, email_lookup_hmac: str) -> list[dict[str, Any]]:
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                """SELECT p.id AS purchase_id, p.chart_id, p.email_ciphertext,
                          r.id AS render_request_id
                   FROM purchases p
                   JOIN charts c ON c.id = p.chart_id AND c.soft_deleted_at IS NULL
                   JOIN entitlements e ON e.chart_id = p.chart_id
                     AND e.product_code = 'report_full' AND e.revoked_at IS NULL
                   LEFT JOIN pdf_render_requests r ON r.id = (
                     SELECT pr.id FROM pdf_render_requests pr
                     WHERE pr.chart_id = p.chart_id AND pr.status = 'ready' AND pr.path IS NOT NULL
                     ORDER BY pr.updated_at DESC, pr.created_at DESC LIMIT 1
                   )
                   WHERE p.email_lookup_hmac = ?
                     AND p.status IN ('succeeded', 'partially_refunded')
                   ORDER BY p.paid_at DESC, p.created_at DESC""",
                (email_lookup_hmac,),
            ).fetchall()
        targets: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            chart_id = str(row["chart_id"])
            if chart_id in seen or not row["email_ciphertext"]:
                continue
            seen.add(chart_id)
            email = str(self._decrypt(row["email_ciphertext"]).get("email") or "")
            if email:
                targets.append(
                    {
                        "purchase_id": str(row["purchase_id"]),
                        "chart_id": chart_id,
                        "email": email,
                        "render_request_id": str(row["render_request_id"])
                        if row["render_request_id"]
                        else None,
                    }
                )
        return targets

    def purchase_ready_target(self, purchase_id: str, render_request_id: str) -> dict[str, Any] | None:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                """SELECT p.chart_id, p.email_ciphertext
                   FROM purchases p
                   JOIN charts c ON c.id = p.chart_id AND c.soft_deleted_at IS NULL
                   JOIN entitlements e ON e.chart_id = p.chart_id
                     AND e.product_code = 'report_full' AND e.revoked_at IS NULL
                   JOIN pdf_render_requests r ON r.id = ? AND r.chart_id = p.chart_id
                     AND r.status = 'ready' AND r.path IS NOT NULL
                   WHERE p.id = ? AND p.status IN ('succeeded', 'partially_refunded')""",
                (render_request_id, purchase_id),
            ).fetchone()
        if not row or not row["email_ciphertext"]:
            return None
        email = str(self._decrypt(row["email_ciphertext"]).get("email") or "")
        if not email:
            return None
        return {
            "purchase_id": purchase_id,
            "chart_id": str(row["chart_id"]),
            "email": email,
            "render_request_id": render_request_id,
        }

    def set_provider_payment(
        self,
        purchase_id: str,
        provider: str,
        provider_payment_id: str | None,
        *,
        status: str = "pending",
        checkout_url: str | None = None,
        provider_status: str | None = None,
        redacted_payload: dict[str, Any] | None = None,
        failure_code: str | None = None,
        receipt_registration: str | None = None,
    ) -> None:
        with self._lock, self._connection() as connection:
            cursor = connection.execute(
                """UPDATE purchases
                   SET provider = ?, provider_payment_id = COALESCE(?, provider_payment_id),
                       checkout_url = COALESCE(?, checkout_url), status = ?,
                       provider_status = ?, provider_payload_json = COALESCE(?, provider_payload_json), failure_code = ?,
                       receipt_registration = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    provider, provider_payment_id, checkout_url, status,
                    provider_status or status,
                    _json_dump(redacted_payload) if redacted_payload is not None else None,
                    failure_code, receipt_registration, _iso(), purchase_id,
                ),
            )
            if cursor.rowcount == 0:
                raise LookupError(purchase_id)

    def get_purchase_by_provider_payment_id(self, provider: str, provider_payment_id: str) -> dict[str, Any] | None:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM purchases WHERE provider = ? AND provider_payment_id = ?",
                (provider, provider_payment_id),
            ).fetchone()
            return dict(row) if row else None

    def payment_event_exists(self, provider: str, provider_event_id: str) -> bool:
        with self._lock, self._connection() as connection:
            return connection.execute(
                "SELECT 1 FROM payment_events WHERE provider = ? AND provider_event_id = ?",
                (provider, provider_event_id),
            ).fetchone() is not None

    def claim_purchase_reconciliation(self, purchase_id: str, cooldown_seconds: int = 5) -> bool:
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT last_reconciled_at FROM purchases WHERE id = ?", (purchase_id,)
                ).fetchone()
                if not row:
                    connection.rollback()
                    raise LookupError(purchase_id)
                now = _utc_now()
                previous = row["last_reconciled_at"]
                if previous:
                    elapsed = (now - datetime.fromisoformat(str(previous))).total_seconds()
                    if elapsed < cooldown_seconds:
                        connection.commit()
                        return False
                connection.execute(
                    "UPDATE purchases SET last_reconciled_at = ?, updated_at = ? WHERE id = ?",
                    (_iso(now), _iso(now), purchase_id),
                )
                connection.commit()
                return True
            except Exception:
                connection.rollback()
                raise

    def record_payment_incident(
        self,
        purchase_id: str | None,
        category: str,
        detail: dict[str, Any],
        trace_id: str | None = None,
    ) -> str:
        incident_id = self._new_id("inc")
        with self._lock, self._connection() as connection:
            connection.execute(
                """INSERT INTO payment_incidents
                   (id, purchase_id, category, detail_json, trace_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (incident_id, purchase_id, category, _json_dump(detail), trace_id, _iso()),
            )
        return incident_id

    def payment_incidents(self, purchase_id: str) -> list[dict[str, Any]]:
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM payment_incidents WHERE purchase_id = ? ORDER BY created_at, id",
                (purchase_id,),
            ).fetchall()
        return [
            {
                **dict(row),
                "detail": _json_load(row["detail_json"], {}),
            }
            for row in rows
        ]

    @staticmethod
    def _payment_mismatch(message: str, detail: dict[str, object] | None = None) -> DomainError:
        return DomainError(
            "PAYMENT_MISMATCH",
            message,
            recoverable=False,
            status_code=409,
            detail=detail,
        )

    def apply_payment_event(
        self,
        purchase_id: str,
        *,
        provider_event_id: str,
        event_type: str,
        object_id: str,
        payload_checksum: str,
        status: str,
        provider_status: str,
        provider_payment_id: str,
        amount_minor: int,
        currency: str,
        metadata: dict[str, Any] | None = None,
        failure_code: str | None = None,
        receipt_registration: str | None = None,
    ) -> dict[str, Any]:
        """Apply a verified provider state after checking immutable order data."""
        metadata = metadata or {}
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                purchase = connection.execute("SELECT * FROM purchases WHERE id = ?", (purchase_id,)).fetchone()
                if not purchase:
                    connection.rollback()
                    raise LookupError(purchase_id)
                duplicate = connection.execute(
                    "SELECT 1 FROM payment_events WHERE provider = ? AND provider_event_id = ?",
                    (purchase["provider"], provider_event_id),
                ).fetchone()
                if duplicate:
                    connection.commit()
                    return {
                        "duplicate": True,
                        "chart_id": str(purchase["chart_id"]),
                        "status": str(purchase["status"]),
                        "entitlement_changed": False,
                    }

                expected_payment_id = purchase["provider_payment_id"]
                if expected_payment_id and expected_payment_id != provider_payment_id:
                    raise self._payment_mismatch("Идентификатор платежа не совпадает с заказом.")
                if object_id != provider_payment_id:
                    raise self._payment_mismatch("Идентификатор объекта уведомления не совпадает с платежом.")
                if int(purchase["amount_minor"]) != amount_minor:
                    raise self._payment_mismatch(
                        "Сумма платежа не совпадает с суммой заказа.",
                        {"expected_amount_minor": int(purchase["amount_minor"])},
                    )
                if str(purchase["currency"]).upper() != currency.upper():
                    raise self._payment_mismatch("Валюта платежа не совпадает с валютой заказа.")
                expected_metadata = {
                    "purchase_id": str(purchase["id"]),
                    "chart_id": str(purchase["chart_id"]),
                    "product_code": str(purchase["product_code"]),
                }
                for key, expected in expected_metadata.items():
                    actual = metadata.get(key)
                    if actual is not None and str(actual) != expected:
                        raise self._payment_mismatch(
                            f"Поле metadata.{key} не совпадает с заказом.",
                            {"field": key},
                        )

                now = _iso()
                connection.execute(
                    """INSERT INTO payment_events
                       (provider, provider_event_id, event_type, object_id, payload_checksum, received_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (purchase["provider"], provider_event_id, event_type, object_id, payload_checksum, now),
                )
                normalized = "cancelled" if status in {"cancelled", "canceled"} else status
                entitlement_changed = False
                current_status = str(purchase["status"])

                if normalized == "succeeded":
                    connection.execute(
                        """UPDATE purchases
                           SET provider_payment_id = ?, status = 'succeeded', provider_status = ?,
                               paid_amount_minor = ?, failure_code = NULL, paid_at = COALESCE(paid_at, ?),
                               last_reconciled_at = ?, receipt_registration = COALESCE(?, receipt_registration),
                               updated_at = ? WHERE id = ?""",
                        (
                            provider_payment_id, provider_status, amount_minor, now, now,
                            receipt_registration, now, purchase_id,
                        ),
                    )
                    entitlement = connection.execute(
                        """SELECT * FROM entitlements
                           WHERE chart_id = ? AND product_code = 'report_full'""",
                        (purchase["chart_id"],),
                    ).fetchone()
                    if not entitlement or entitlement["revoked_at"] is not None:
                        connection.execute(
                            """INSERT INTO entitlements
                               (id, chart_id, product_code, purchase_id, granted_at, revoked_at, revocation_reason)
                               VALUES (?, ?, 'report_full', ?, ?, NULL, NULL)
                               ON CONFLICT(chart_id, product_code) DO UPDATE SET
                                 purchase_id = excluded.purchase_id,
                                 granted_at = excluded.granted_at,
                                 revoked_at = NULL,
                                 revocation_reason = NULL""",
                            (self._new_id("ent"), purchase["chart_id"], purchase_id, now),
                        )
                        self._emit(connection, purchase["chart_id"], "entitlement.granted", {"product": "report_full"})
                        self._enqueue(connection, purchase["chart_id"], "paid_report_v1", priority=90)
                        entitlement_changed = True
                elif normalized == "cancelled" and current_status not in {"succeeded", "partially_refunded", "refunded"}:
                    connection.execute(
                        """UPDATE purchases
                           SET provider_payment_id = ?, status = 'cancelled', provider_status = ?,
                               failure_code = ?, canceled_at = COALESCE(canceled_at, ?),
                               last_reconciled_at = ?, updated_at = ? WHERE id = ?""",
                        (provider_payment_id, provider_status, failure_code, now, now, now, purchase_id),
                    )
                    self._emit(
                        connection,
                        purchase["chart_id"],
                        "payment.cancelled",
                        {"purchase_id": purchase_id, "reason": failure_code},
                    )
                else:
                    next_status = normalized if current_status not in {"succeeded", "partially_refunded", "refunded"} else current_status
                    connection.execute(
                        """UPDATE purchases
                           SET provider_payment_id = ?, status = ?, provider_status = ?, failure_code = ?,
                               last_reconciled_at = ?, updated_at = ? WHERE id = ?""",
                        (provider_payment_id, next_status, provider_status, failure_code, now, now, purchase_id),
                    )
                final = connection.execute("SELECT status FROM purchases WHERE id = ?", (purchase_id,)).fetchone()
                connection.commit()
                return {
                    "duplicate": False,
                    "chart_id": str(purchase["chart_id"]),
                    "status": str(final["status"]),
                    "entitlement_changed": entitlement_changed,
                }
            except Exception:
                connection.rollback()
                raise

    def confirm_purchase(self, purchase_id: str, provider_event_id: str) -> str | None:
        """Idempotent payment transition used only by a verified provider webhook/test adapter."""
        purchase = self.get_purchase(purchase_id)
        if not purchase:
            return None
        provider_payment_id = str(purchase["provider_payment_id"] or f"test_{purchase_id}")
        self.apply_payment_event(
            purchase_id,
            provider_event_id=provider_event_id,
            event_type="payment.succeeded",
            object_id=provider_payment_id,
            payload_checksum=hashlib.sha256(provider_event_id.encode("utf-8")).hexdigest(),
            status="succeeded",
            provider_status="succeeded",
            provider_payment_id=provider_payment_id,
            amount_minor=int(purchase["amount_minor"]),
            currency=str(purchase["currency"]),
            metadata={
                "purchase_id": purchase_id,
                "chart_id": str(purchase["chart_id"]),
                "product_code": str(purchase["product_code"]),
            },
        )
        return str(purchase["chart_id"])

    def create_refund(
        self,
        purchase_id: str,
        *,
        idempotency_key: str,
        amount_minor: int,
        reason: str,
        actor_fingerprint: str,
    ) -> tuple[dict[str, Any], bool]:
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute(
                    "SELECT * FROM refunds WHERE purchase_id = ? AND idempotency_key = ?",
                    (purchase_id, idempotency_key),
                ).fetchone()
                if existing:
                    connection.commit()
                    return dict(existing), False
                purchase = connection.execute("SELECT * FROM purchases WHERE id = ?", (purchase_id,)).fetchone()
                if not purchase:
                    raise DomainError("PURCHASE_NOT_FOUND", "Заказ не найден.", status_code=404)
                if purchase["status"] not in {"succeeded", "partially_refunded"}:
                    raise DomainError(
                        "REFUND_NOT_ALLOWED",
                        "Возврат доступен только для успешно оплаченного заказа.",
                        recoverable=False,
                        status_code=409,
                    )
                paid_amount = int(purchase["paid_amount_minor"] or purchase["amount_minor"])
                reserved_row = connection.execute(
                    """SELECT COALESCE(SUM(amount_minor), 0) AS total FROM refunds
                       WHERE purchase_id = ? AND status IN ('created', 'pending', 'unknown', 'succeeded')""",
                    (purchase_id,),
                ).fetchone()
                reserved = int(reserved_row["total"])
                remaining = paid_amount - reserved
                remainder_after = remaining - amount_minor
                if amount_minor < 100 or amount_minor > remaining or (remainder_after != 0 and remainder_after < 100):
                    raise DomainError(
                        "REFUND_AMOUNT_INVALID",
                        "Сумма возврата недопустима: остаток должен быть нулевым или не меньше одного рубля.",
                        recoverable=False,
                        status_code=422,
                        detail={"available_amount_minor": remaining},
                    )
                now = _iso()
                refund = {
                    "id": self._new_id("ref"),
                    "purchase_id": purchase_id,
                    "idempotency_key": idempotency_key,
                    "provider_idempotency_key": secrets.token_urlsafe(32),
                    "provider_refund_id": None,
                    "status": "created",
                    "amount_minor": amount_minor,
                    "currency": str(purchase["currency"]),
                    "actor_fingerprint": actor_fingerprint,
                    "created_at": now,
                    "updated_at": now,
                }
                connection.execute(
                    """INSERT INTO refunds
                       (id, purchase_id, idempotency_key, provider_idempotency_key, provider_refund_id,
                        status, amount_minor, currency, reason_ciphertext, actor_fingerprint,
                        created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        refund["id"], purchase_id, idempotency_key, refund["provider_idempotency_key"],
                        None, refund["status"], amount_minor, refund["currency"],
                        self._encrypt({"reason": reason}), actor_fingerprint, now, now,
                    ),
                )
                connection.commit()
                return refund, True
            except Exception:
                connection.rollback()
                raise

    def get_refund(self, refund_id: str) -> dict[str, Any] | None:
        with self._lock, self._connection() as connection:
            row = connection.execute("SELECT * FROM refunds WHERE id = ?", (refund_id,)).fetchone()
            return dict(row) if row else None

    def get_refund_by_provider_refund_id(self, provider_refund_id: str) -> dict[str, Any] | None:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM refunds WHERE provider_refund_id = ?", (provider_refund_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_refund_reason(self, refund_id: str) -> str | None:
        with self._lock, self._connection() as connection:
            row = connection.execute("SELECT reason_ciphertext FROM refunds WHERE id = ?", (refund_id,)).fetchone()
        if not row:
            raise LookupError(refund_id)
        return self._decrypt(row["reason_ciphertext"]).get("reason") if row["reason_ciphertext"] else None

    def set_provider_refund(
        self,
        refund_id: str,
        *,
        provider_refund_id: str | None,
        status: str,
        receipt_registration: str | None = None,
        failure_code: str | None = None,
    ) -> None:
        with self._lock, self._connection() as connection:
            cursor = connection.execute(
                """UPDATE refunds SET provider_refund_id = ?, status = ?, receipt_registration = ?,
                   failure_code = ?, updated_at = ? WHERE id = ?""",
                (provider_refund_id, status, receipt_registration, failure_code, _iso(), refund_id),
            )
            if cursor.rowcount == 0:
                raise LookupError(refund_id)

    def apply_refund_event(
        self,
        refund_id: str,
        *,
        provider_event_id: str,
        event_type: str,
        object_id: str,
        payload_checksum: str,
        status: str,
        provider_payment_id: str,
        amount_minor: int,
        currency: str,
        failure_code: str | None = None,
        receipt_registration: str | None = None,
    ) -> dict[str, Any]:
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    """SELECT refunds.*, purchases.chart_id, purchases.provider,
                              purchases.provider_payment_id, purchases.paid_amount_minor,
                              purchases.amount_minor AS purchase_amount_minor,
                              purchases.currency AS purchase_currency
                       FROM refunds JOIN purchases ON purchases.id = refunds.purchase_id
                       WHERE refunds.id = ?""",
                    (refund_id,),
                ).fetchone()
                if not row:
                    connection.rollback()
                    raise LookupError(refund_id)
                duplicate = connection.execute(
                    "SELECT 1 FROM payment_events WHERE provider = ? AND provider_event_id = ?",
                    (row["provider"], provider_event_id),
                ).fetchone()
                if duplicate:
                    connection.commit()
                    return {
                        "duplicate": True,
                        "chart_id": str(row["chart_id"]),
                        "status": str(row["status"]),
                        "entitlement_changed": False,
                    }
                if str(row["provider_payment_id"]) != provider_payment_id:
                    raise self._payment_mismatch("Возврат относится к другому платежу.")
                if row["provider_refund_id"] and str(row["provider_refund_id"]) != object_id:
                    raise self._payment_mismatch("Идентификатор возврата не совпадает с операцией.")
                if int(row["amount_minor"]) != amount_minor:
                    raise self._payment_mismatch("Сумма возврата не совпадает с созданной операцией.")
                if str(row["purchase_currency"]).upper() != currency.upper():
                    raise self._payment_mismatch("Валюта возврата не совпадает с валютой платежа.")

                now = _iso()
                connection.execute(
                    """INSERT INTO payment_events
                       (provider, provider_event_id, event_type, object_id, payload_checksum, received_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (row["provider"], provider_event_id, event_type, object_id, payload_checksum, now),
                )
                normalized = "cancelled" if status in {"cancelled", "canceled"} else status
                connection.execute(
                    """UPDATE refunds SET provider_refund_id = ?, status = ?, failure_code = ?,
                       receipt_registration = COALESCE(?, receipt_registration), updated_at = ? WHERE id = ?""",
                    (object_id, normalized, failure_code, receipt_registration, now, refund_id),
                )
                entitlement_changed = False
                if normalized == "succeeded":
                    total_row = connection.execute(
                        "SELECT COALESCE(SUM(amount_minor), 0) AS total FROM refunds WHERE purchase_id = ? AND status = 'succeeded'",
                        (row["purchase_id"],),
                    ).fetchone()
                    refunded_total = int(total_row["total"])
                    paid_total = int(row["paid_amount_minor"] or row["purchase_amount_minor"])
                    if refunded_total > paid_total:
                        raise self._payment_mismatch("Сумма подтвержденных возвратов превышает сумму платежа.")
                    purchase_status = "refunded" if refunded_total == paid_total else "partially_refunded"
                    connection.execute(
                        """UPDATE purchases SET status = ?, refunded_amount_minor = ?,
                           updated_at = ? WHERE id = ?""",
                        (purchase_status, refunded_total, now, row["purchase_id"]),
                    )
                    if purchase_status == "refunded":
                        active = connection.execute(
                            """SELECT id FROM entitlements WHERE chart_id = ? AND product_code = 'report_full'
                               AND revoked_at IS NULL""",
                            (row["chart_id"],),
                        ).fetchone()
                        if active:
                            connection.execute(
                                """UPDATE entitlements SET revoked_at = ?, revocation_reason = 'full_refund'
                                   WHERE id = ?""",
                                (now, active["id"]),
                            )
                            self._emit(
                                connection,
                                row["chart_id"],
                                "entitlement.revoked",
                                {"product": "report_full", "reason": "full_refund"},
                            )
                            entitlement_changed = True
                connection.commit()
                return {
                    "duplicate": False,
                    "chart_id": str(row["chart_id"]),
                    "status": normalized,
                    "entitlement_changed": entitlement_changed,
                }
            except Exception:
                connection.rollback()
                raise

    def record_payment_operation(
        self,
        *,
        action: str,
        purchase_id: str | None,
        refund_id: str | None,
        actor_fingerprint: str,
        source_ip: str,
        trace_id: str,
        reason: str | None,
        amount_minor: int | None,
        result: str,
        detail: dict[str, Any] | None = None,
    ) -> str:
        operation_id = self._new_id("op")
        with self._lock, self._connection() as connection:
            connection.execute(
                """INSERT INTO payment_operations
                   (id, action, purchase_id, refund_id, actor_fingerprint, source_ip,
                    trace_id, reason_ciphertext, amount_minor, result, detail_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    operation_id, action, purchase_id, refund_id, actor_fingerprint, source_ip,
                    trace_id, self._encrypt({"reason": reason}) if reason else None,
                    amount_minor, result, _json_dump(detail or {}), _iso(),
                ),
            )
        return operation_id

    def payment_operations(self, purchase_id: str) -> list[dict[str, Any]]:
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM payment_operations WHERE purchase_id = ? ORDER BY created_at, id",
                (purchase_id,),
            ).fetchall()
        return [
            {
                **dict(row),
                "reason": self._decrypt(row["reason_ciphertext"]).get("reason")
                if row["reason_ciphertext"]
                else None,
                "detail": _json_load(row["detail_json"], {}),
            }
            for row in rows
        ]

    def has_entitlement(self, chart_id: str) -> bool:
        with self._lock, self._connection() as connection:
            return connection.execute(
                """SELECT 1 FROM entitlements WHERE chart_id = ? AND product_code = 'report_full'
                   AND revoked_at IS NULL""",
                (chart_id,),
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

    def erase_chart_personal_data(
        self,
        chart_id: str,
        *,
        reason: str = "user_request",
    ) -> dict[str, Any]:
        """Atomically redact a chart, then finish bounded file deletion from its tombstone."""
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                chart = connection.execute(
                    "SELECT id, session_id, birth_profile_id, soft_deleted_at FROM charts WHERE id = ?",
                    (chart_id,),
                ).fetchone()
                if not chart:
                    connection.commit()
                    retried = self._finish_tombstone_files(chart_id)
                    return {"found": False, "chart_id": chart_id, **retried}
                if chart["soft_deleted_at"]:
                    connection.commit()
                    retried = self._finish_tombstone_files(chart_id)
                    return {
                        "found": True,
                        "chart_id": chart_id,
                        "already_erased": True,
                        **retried,
                    }
                active = connection.execute(
                    """SELECT 1 FROM jobs WHERE chart_id = ?
                       AND status IN ('running', 'validating') LIMIT 1""",
                    (chart_id,),
                ).fetchone()
                if active:
                    raise DomainError(
                        "ERASURE_JOB_ACTIVE",
                        "Дождитесь завершения текущего расчёта и повторите удаление.",
                        recoverable=True,
                        status_code=409,
                    )
                paths = sorted(
                    {
                        str(row["path"])
                        for row in connection.execute(
                            """SELECT path FROM reports WHERE chart_id = ? AND path IS NOT NULL
                               UNION SELECT path FROM pdf_render_requests
                               WHERE chart_id = ? AND path IS NOT NULL""",
                            (chart_id, chart_id),
                        ).fetchall()
                    }
                )
                retains_financial_records = connection.execute(
                    "SELECT 1 FROM purchases WHERE chart_id = ? LIMIT 1",
                    (chart_id,),
                ).fetchone() is not None
                now = _iso()
                connection.execute(
                    """INSERT INTO erasure_tombstones
                       (chart_id, reason, financial_records_retained, report_paths_json,
                        status, created_at)
                       VALUES (?, ?, ?, ?, 'pending_files', ?)
                       ON CONFLICT(chart_id) DO UPDATE SET
                         reason = excluded.reason,
                         financial_records_retained = excluded.financial_records_retained,
                         report_paths_json = excluded.report_paths_json,
                         status = 'pending_files',
                         last_error_code = NULL""",
                    (
                        chart_id,
                        reason[:80],
                        int(retains_financial_records),
                        _json_dump(paths),
                        now,
                    ),
                )
                lookup_hashes = [
                    str(row["email_lookup_hmac"])
                    for row in connection.execute(
                        """SELECT DISTINCT email_lookup_hmac FROM purchases
                           WHERE chart_id = ? AND email_lookup_hmac IS NOT NULL""",
                        (chart_id,),
                    ).fetchall()
                ]
                connection.execute("DELETE FROM email_deliveries WHERE chart_id = ?", (chart_id,))
                for lookup_hash in lookup_hashes:
                    connection.execute(
                        "DELETE FROM email_deliveries WHERE email_lookup_hmac = ?", (lookup_hash,)
                    )
                for table in (
                    "agent_runs",
                    "pdf_render_requests",
                    "reports",
                    "saved_questions",
                    "magic_links",
                    "outbox_events",
                    "chart_access",
                    "jobs",
                ):
                    connection.execute(f"DELETE FROM {table} WHERE chart_id = ?", (chart_id,))
                if retains_financial_records:
                    connection.execute(
                        """UPDATE entitlements SET revoked_at = ?, revocation_reason = 'personal_data_erasure'
                           WHERE chart_id = ? AND revoked_at IS NULL""",
                        (now, chart_id),
                    )
                    purchase_ids = [
                        str(row["id"])
                        for row in connection.execute(
                            "SELECT id FROM purchases WHERE chart_id = ?", (chart_id,)
                        ).fetchall()
                    ]
                    for purchase_id in purchase_ids:
                        connection.execute(
                            """UPDATE payment_operations SET source_ip = 'erased', reason_ciphertext = NULL
                               WHERE purchase_id = ?""",
                            (purchase_id,),
                        )
                        connection.execute(
                            "UPDATE refunds SET reason_ciphertext = NULL WHERE purchase_id = ?",
                            (purchase_id,),
                        )
                    connection.execute(
                        """UPDATE purchases SET email_ciphertext = NULL, email_lookup_hmac = NULL,
                           checkout_url = NULL, provider_payload_json = NULL, updated_at = ?
                           WHERE chart_id = ?""",
                        (now, chart_id),
                    )
                    connection.execute(
                        """UPDATE charts SET status = 'erased', birth_public_json = ?, snapshot_json = NULL,
                           evidence_json = NULL, free_bundle_json = NULL, paid_bundle_json = NULL,
                           soft_deleted_at = ?, updated_at = ? WHERE id = ?""",
                        (self._encode_public_birth({"erased": True}), now, now, chart_id),
                    )
                    connection.execute(
                        """UPDATE birth_profiles SET encrypted_payload = ?, deleted_at = ? WHERE id = ?""",
                        (self._encrypt({"erased": True}), now, chart["birth_profile_id"]),
                    )
                else:
                    purchase_ids = [
                        str(row["id"])
                        for row in connection.execute(
                            "SELECT id FROM purchases WHERE chart_id = ?", (chart_id,)
                        ).fetchall()
                    ]
                    for purchase_id in purchase_ids:
                        connection.execute("DELETE FROM payment_operations WHERE purchase_id = ?", (purchase_id,))
                        connection.execute("DELETE FROM payment_incidents WHERE purchase_id = ?", (purchase_id,))
                        connection.execute("DELETE FROM refunds WHERE purchase_id = ?", (purchase_id,))
                    connection.execute("DELETE FROM entitlements WHERE chart_id = ?", (chart_id,))
                    connection.execute("DELETE FROM purchases WHERE chart_id = ?", (chart_id,))
                    connection.execute("DELETE FROM charts WHERE id = ?", (chart_id,))
                    connection.execute(
                        """DELETE FROM birth_profiles WHERE id = ?
                           AND NOT EXISTS (SELECT 1 FROM charts WHERE birth_profile_id = ?)""",
                        (chart["birth_profile_id"], chart["birth_profile_id"]),
                    )
                    connection.execute(
                        """DELETE FROM anonymous_sessions WHERE id = ?
                           AND NOT EXISTS (SELECT 1 FROM charts WHERE session_id = ?)
                           AND NOT EXISTS (SELECT 1 FROM birth_profiles WHERE session_id = ?)""",
                        (chart["session_id"], chart["session_id"], chart["session_id"]),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        file_result = self._finish_tombstone_files(chart_id)
        return {
            "found": True,
            "chart_id": chart_id,
            "hard_deleted": not retains_financial_records,
            "financial_records_retained": retains_financial_records,
            **file_result,
        }

    def _finish_tombstone_files(self, chart_id: str) -> dict[str, Any]:
        with self._lock, self._connection() as connection:
            tombstone = connection.execute(
                "SELECT * FROM erasure_tombstones WHERE chart_id = ?", (chart_id,)
            ).fetchone()
        if not tombstone:
            return {"report_files_deleted": 0, "file_cleanup_pending": False}
        paths = _json_load(tombstone["report_paths_json"], [])
        reports_root = self.reports_dir.resolve()
        deleted = 0
        failures: list[str] = []
        for value in paths:
            try:
                path = Path(str(value)).resolve()
                if not path.is_relative_to(reports_root):
                    failures.append("UNSAFE_REPORT_PATH")
                    continue
                existed = path.exists()
                path.unlink(missing_ok=True)
                deleted += int(existed)
            except OSError:
                failures.append("REPORT_UNLINK_FAILED")
        with self._lock, self._connection() as connection:
            connection.execute(
                """UPDATE erasure_tombstones
                   SET status = ?, files_deleted_at = ?, last_error_code = ? WHERE chart_id = ?""",
                (
                    "pending_files" if failures else "complete",
                    None if failures else _iso(),
                    failures[0] if failures else None,
                    chart_id,
                ),
            )
        return {
            "report_files_deleted": deleted,
            "file_cleanup_pending": bool(failures),
        }

    def erase_expired_unpaid_charts(self, *, older_than_days: int = 30) -> int:
        if older_than_days < 1:
            raise ValueError("older_than_days must be positive")
        cutoff = _iso(_utc_now() - timedelta(days=older_than_days))
        with self._lock, self._connection() as connection:
            chart_ids = [
                str(row["id"])
                for row in connection.execute(
                    """SELECT id FROM charts
                       WHERE created_at < ? AND soft_deleted_at IS NULL
                       AND NOT EXISTS (
                         SELECT 1 FROM purchases WHERE purchases.chart_id = charts.id
                         AND purchases.status IN ('succeeded', 'partially_refunded', 'refunded')
                       )""",
                    (cutoff,),
                ).fetchall()
            ]
        for expired_chart_id in chart_ids:
            self.erase_chart_personal_data(expired_chart_id, reason="retention_expired")
        return len(chart_ids)

    def retention_plan(self, *, anonymous_chart_days: int, report_days: int) -> dict[str, Any]:
        if anonymous_chart_days < 1 or report_days < 1:
            raise ValueError("retention periods must be positive")
        chart_cutoff = _iso(_utc_now() - timedelta(days=anonymous_chart_days))
        report_cutoff = _iso(_utc_now() - timedelta(days=report_days))
        with self._lock, self._connection() as connection:
            chart_ids = [
                str(row["id"])
                for row in connection.execute(
                    """SELECT id FROM charts
                       WHERE created_at < ? AND soft_deleted_at IS NULL
                       AND NOT EXISTS (
                         SELECT 1 FROM purchases WHERE purchases.chart_id = charts.id
                         AND purchases.status IN ('succeeded', 'partially_refunded', 'refunded')
                       ) ORDER BY created_at, id""",
                    (chart_cutoff,),
                ).fetchall()
            ]
            report_rows = [
                dict(row)
                for row in connection.execute(
                    """SELECT id, chart_id, path FROM pdf_render_requests
                       WHERE status = 'ready' AND path IS NOT NULL AND updated_at < ?
                       ORDER BY updated_at, id""",
                    (report_cutoff,),
                ).fetchall()
            ]
            pending_tombstones = [
                str(row["chart_id"])
                for row in connection.execute(
                    "SELECT chart_id FROM erasure_tombstones WHERE status = 'pending_files'"
                ).fetchall()
            ]
        return {
            "chart_cutoff": chart_cutoff,
            "report_cutoff": report_cutoff,
            "anonymous_chart_ids": chart_ids,
            "expired_reports": report_rows,
            "pending_tombstone_chart_ids": pending_tombstones,
        }

    def apply_retention_plan(
        self,
        plan: dict[str, Any],
        *,
        security_log_days: int,
    ) -> dict[str, Any]:
        if security_log_days < 1:
            raise ValueError("security_log_days must be positive")
        run_id = self._new_id("retention")
        now = _iso()
        erased = 0
        failed = 0
        expired_reports = 0
        with self._lock, self._connection() as connection:
            connection.execute(
                """INSERT INTO retention_runs
                   (id, mode, cutoff_at, candidates, erased, failed, detail_json, created_at)
                   VALUES (?, 'apply', ?, ?, 0, 0, ?, ?)""",
                (
                    run_id,
                    str(plan["chart_cutoff"]),
                    len(plan["anonymous_chart_ids"]),
                    _json_dump({"report_cutoff": plan["report_cutoff"]}),
                    now,
                ),
            )
        for chart_id in plan["anonymous_chart_ids"]:
            try:
                result = self.erase_chart_personal_data(chart_id, reason="retention_expired")
                erased += int(bool(result.get("found")))
            except Exception:
                failed += 1
        reports_root = self.reports_dir.resolve()
        for report in plan["expired_reports"]:
            try:
                path = Path(str(report["path"])).resolve()
                if not path.is_relative_to(reports_root):
                    failed += 1
                    continue
                path.unlink(missing_ok=True)
                with self._lock, self._connection() as connection:
                    connection.execute(
                        """UPDATE pdf_render_requests
                           SET status = 'failed', path = NULL, checksum = NULL, size_bytes = NULL,
                               pages = NULL, error_code = 'PDF_EXPIRED', updated_at = ? WHERE id = ?""",
                        (_iso(), report["id"]),
                    )
                    connection.execute(
                        """UPDATE reports SET status = 'failed', path = NULL, checksum = NULL,
                           size_bytes = NULL, pages = NULL, error_code = 'PDF_EXPIRED', updated_at = ?
                           WHERE render_request_id = ?""",
                        (_iso(), report["id"]),
                    )
                expired_reports += 1
            except OSError:
                failed += 1
        for chart_id in plan["pending_tombstone_chart_ids"]:
            retry = self._finish_tombstone_files(chart_id)
            failed += int(bool(retry["file_cleanup_pending"]))
        cutoff_epoch = (_utc_now() - timedelta(days=security_log_days)).timestamp()
        with self._lock, self._connection() as connection:
            connection.execute("DELETE FROM rate_limit_events WHERE occurred_at < ?", (cutoff_epoch,))
            detail = {
                "expired_reports": expired_reports,
                "pending_tombstones_retried": len(plan["pending_tombstone_chart_ids"]),
            }
            connection.execute(
                """UPDATE retention_runs SET erased = ?, failed = ?, detail_json = ?, finished_at = ?
                   WHERE id = ?""",
                (erased, failed, _json_dump(detail), _iso(), run_id),
            )
        return {
            "run_id": run_id,
            "erased_anonymous_charts": erased,
            "expired_reports": expired_reports,
            "failed": failed,
        }

    def upsert_report(
        self,
        chart_id: str,
        status: str,
        path: str | None = None,
        checksum: str | None = None,
        size_bytes: int | None = None,
        pages: int | None = None,
        error_code: str | None = None,
        render_request_id: str | None = None,
        preferences_checksum: str | None = None,
    ) -> None:
        now = _iso()
        with self._lock, self._connection() as connection:
            connection.execute(
                """INSERT INTO reports (id, chart_id, status, path, checksum, size_bytes, pages, error_code, render_request_id, preferences_checksum, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(chart_id) DO UPDATE SET status = excluded.status, path = excluded.path, checksum = excluded.checksum,
                   size_bytes = excluded.size_bytes, pages = excluded.pages, error_code = excluded.error_code,
                   render_request_id = excluded.render_request_id, preferences_checksum = excluded.preferences_checksum,
                   updated_at = excluded.updated_at""",
                (self._new_id("rpt"), chart_id, status, path, checksum, size_bytes, pages, error_code, render_request_id, preferences_checksum, now, now),
            )

    def commit_report_event(self, chart_id: str, status: str, payload: dict[str, Any], **report: Any) -> None:
        now = _iso()
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """INSERT INTO reports (id, chart_id, status, path, checksum, size_bytes, pages, error_code, render_request_id, preferences_checksum, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(chart_id) DO UPDATE SET status = excluded.status, path = excluded.path, checksum = excluded.checksum,
                       size_bytes = excluded.size_bytes, pages = excluded.pages, error_code = excluded.error_code,
                       preferences_checksum = excluded.preferences_checksum, updated_at = excluded.updated_at
                       WHERE reports.render_request_id = excluded.render_request_id""",
                    (
                        self._new_id("rpt"), chart_id, status, report.get("path"), report.get("checksum"), report.get("size_bytes"),
                        report.get("pages"), report.get("error_code"), report.get("render_request_id"),
                        report.get("preferences_checksum"), now, now,
                    ),
                )
                if report.get("render_request_id"):
                    connection.execute(
                        """UPDATE pdf_render_requests
                           SET status = ?, path = ?, checksum = ?, size_bytes = ?, pages = ?, error_code = ?, updated_at = ?
                           WHERE id = ? AND chart_id = ?""",
                        (
                            status,
                            report.get("path"),
                            report.get("checksum"),
                            report.get("size_bytes"),
                            report.get("pages"),
                            report.get("error_code"),
                            now,
                            report["render_request_id"],
                            chart_id,
                        ),
                    )
                self._emit(connection, chart_id, "pdf.ready" if status == "ready" else "job.failed", payload)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        if status == "ready":
            self._prune_pdf_render_files(chart_id)

    def _prune_pdf_render_files(self, chart_id: str, keep: int = 3) -> None:
        """Keep a small retry window without retaining personal reports indefinitely."""
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                """SELECT id, path FROM pdf_render_requests
                   WHERE chart_id = ? AND status = 'ready' AND path IS NOT NULL
                   ORDER BY updated_at DESC, created_at DESC""",
                (chart_id,),
            ).fetchall()
            expired = rows[max(1, keep):]
            for row in expired:
                try:
                    Path(row["path"]).unlink(missing_ok=True)
                except OSError:
                    continue
                connection.execute(
                    """UPDATE pdf_render_requests
                       SET status = 'failed', path = NULL, checksum = NULL, size_bytes = NULL,
                           pages = NULL, error_code = 'PDF_EXPIRED', updated_at = ?
                       WHERE id = ?""",
                    (_iso(), row["id"]),
                )

    def get_report(self, chart_id: str) -> dict[str, Any]:
        with self._lock, self._connection() as connection:
            row = connection.execute("SELECT * FROM reports WHERE chart_id = ?", (chart_id,)).fetchone()
            render_request = connection.execute(
                "SELECT preferences_json FROM pdf_render_requests WHERE id = ?",
                (row["render_request_id"],),
            ).fetchone() if row and row["render_request_id"] else None
        if not row:
            return {"status": "locked" if not self.has_entitlement(chart_id) else "generating"}
        return {
            "status": row["status"],
            "pages": row["pages"],
            "size_bytes": row["size_bytes"],
            "error_code": row["error_code"],
            "render_request_id": row["render_request_id"],
            "render_preferences": _json_load(render_request["preferences_json"], {}) if render_request else None,
            "download_url": None,
        }

    def report_file_path(self, chart_id: str, render_request_id: str | None = None) -> Path | None:
        with self._lock, self._connection() as connection:
            if render_request_id:
                row = connection.execute(
                    """SELECT path FROM pdf_render_requests
                       WHERE id = ? AND chart_id = ? AND status = 'ready'""",
                    (render_request_id, chart_id),
                ).fetchone()
            else:
                row = connection.execute("SELECT path FROM reports WHERE chart_id = ? AND status = 'ready'", (chart_id,)).fetchone()
        return Path(row["path"]) if row and row["path"] else None

    def issue_download_token(self, chart_id: str, render_request_id: str, ttl_minutes: int = 10) -> str:
        expires = int((_utc_now() + timedelta(minutes=ttl_minutes)).timestamp())
        payload = f"{chart_id}.{render_request_id}.{expires}".encode()
        signature = hmac.new(self._signing_key, payload, hashlib.sha256).hexdigest()
        return base64.urlsafe_b64encode(payload + b"." + signature.encode("ascii")).decode("ascii")

    def validate_download_token(self, token: str, chart_id: str, render_request_id: str) -> bool:
        try:
            decoded = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
            encoded_payload, signature = decoded.rsplit(".", 1)
            token_chart_id, token_render_request_id, expires = encoded_payload.rsplit(".", 2)
            expected = hmac.new(self._signing_key, encoded_payload.encode("utf-8"), hashlib.sha256).hexdigest()
            return (
                token_chart_id == chart_id
                and token_render_request_id == render_request_id
                and int(expires) >= int(_utc_now().timestamp())
                and hmac.compare_digest(signature, expected)
            )
        except (ValueError, UnicodeDecodeError):
            return False

    def create_magic_link(
        self,
        chart_id: str,
        ttl_hours: int = 1,
        *,
        scope: str = "read_chart",
        render_request_id: str | None = None,
    ) -> str:
        if scope not in {"read_chart", "download_pdf"}:
            raise ValueError("unsupported magic-link scope")
        if scope == "download_pdf" and not render_request_id:
            raise ValueError("render_request_id is required for download_pdf")
        token = secrets.token_urlsafe(32)
        expires = _utc_now() + timedelta(hours=ttl_hours)
        with self._lock, self._connection() as connection:
            chart = connection.execute(
                "SELECT 1 FROM charts WHERE id = ? AND soft_deleted_at IS NULL", (chart_id,)
            ).fetchone()
            if not chart:
                raise LookupError(chart_id)
            if render_request_id:
                rendered = connection.execute(
                    """SELECT 1 FROM pdf_render_requests
                       WHERE id = ? AND chart_id = ? AND status = 'ready' AND path IS NOT NULL""",
                    (render_request_id, chart_id),
                ).fetchone()
                if not rendered:
                    raise LookupError(render_request_id)
            connection.execute(
                """INSERT INTO magic_links
                   (token_hash, chart_id, scope, render_request_id, expires_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    self._token_hash(token),
                    chart_id,
                    scope,
                    render_request_id,
                    _iso(expires),
                    _iso(),
                ),
            )
        return token

    def begin_magic_link_confirmation(
        self,
        token: str,
        *,
        ttl_minutes: int = 10,
    ) -> tuple[str, str] | None:
        if ttl_minutes <= 0 or ttl_minutes > 30:
            raise ValueError("magic-link confirmation TTL must be between 1 and 30 minutes")
        token_hash = self._token_hash(token)
        nonce = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        now = _utc_now()
        expires_at = now + timedelta(minutes=ttl_minutes)
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM magic_links WHERE token_hash = ?", (token_hash,)
            ).fetchone()
            if not row or row["used_at"] or datetime.fromisoformat(row["expires_at"]) < now:
                connection.commit()
                return None
            chart = connection.execute(
                "SELECT 1 FROM charts WHERE id = ? AND soft_deleted_at IS NULL",
                (row["chart_id"],),
            ).fetchone()
            if not chart:
                connection.commit()
                return None
            connection.execute(
                "DELETE FROM magic_link_confirmations WHERE expires_at < ? OR used_at IS NOT NULL",
                (_iso(now),),
            )
            connection.execute(
                """INSERT INTO magic_link_confirmations
                   (nonce_hash, magic_token_hash, csrf_token_hash, expires_at, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    self._token_hash(nonce),
                    token_hash,
                    self._token_hash(csrf_token),
                    _iso(expires_at),
                    _iso(now),
                ),
            )
            connection.commit()
        return nonce, csrf_token

    def consume_magic_link_confirmation(
        self,
        nonce: str,
        csrf_token: str,
    ) -> tuple[dict[str, Any], str] | None:
        nonce_hash = self._token_hash(nonce)
        csrf_hash = self._token_hash(csrf_token)
        now = _utc_now()
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            confirmation = connection.execute(
                "SELECT * FROM magic_link_confirmations WHERE nonce_hash = ?",
                (nonce_hash,),
            ).fetchone()
            if (
                not confirmation
                or confirmation["used_at"]
                or datetime.fromisoformat(confirmation["expires_at"]) < now
                or not hmac.compare_digest(str(confirmation["csrf_token_hash"]), csrf_hash)
            ):
                connection.commit()
                return None
            link = connection.execute(
                "SELECT * FROM magic_links WHERE token_hash = ?",
                (confirmation["magic_token_hash"],),
            ).fetchone()
            if not link or link["used_at"] or datetime.fromisoformat(link["expires_at"]) < now:
                connection.commit()
                return None
            chart = connection.execute(
                "SELECT id FROM charts WHERE id = ? AND soft_deleted_at IS NULL",
                (link["chart_id"],),
            ).fetchone()
            if not chart:
                connection.commit()
                return None

            session_id = self._new_id("ses")
            session_token = secrets.token_urlsafe(32)
            now_iso = _iso(now)
            connection.execute(
                """INSERT INTO anonymous_sessions
                   (id, token_hash, created_at, last_seen_at) VALUES (?, ?, ?, ?)""",
                (session_id, self._token_hash(session_token), now_iso, now_iso),
            )
            connection.execute(
                "INSERT INTO chart_access (chart_id, session_id, granted_at) VALUES (?, ?, ?)",
                (chart["id"], session_id, now_iso),
            )
            connection.execute(
                "UPDATE magic_link_confirmations SET used_at = ? WHERE nonce_hash = ?",
                (now_iso, nonce_hash),
            )
            connection.execute(
                "UPDATE magic_links SET used_at = ? WHERE token_hash = ?",
                (now_iso, link["token_hash"]),
            )
            connection.commit()
            return (
                {
                    "chart_id": str(chart["id"]),
                    "scope": str(link["scope"]),
                    "render_request_id": str(link["render_request_id"])
                    if link["render_request_id"]
                    else None,
                },
                session_token,
            )

    def revoke_magic_links(self, tokens: list[str]) -> None:
        if not tokens:
            return
        hashes = [self._token_hash(token) for token in tokens]
        placeholders = ",".join("?" for _ in hashes)
        with self._lock, self._connection() as connection:
            connection.execute(
                f"DELETE FROM magic_links WHERE token_hash IN ({placeholders})", hashes
            )
