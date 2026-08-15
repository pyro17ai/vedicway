from __future__ import annotations

import hashlib

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from vedicway_backend.content_store import (
    CONTENT_SCHEMA_REVISION,
    ConsentRecord,
    ContentDatabase,
    fingerprint_hash,
)
from vedicway_backend.legal_config import LEGAL_DOCUMENT_VERSIONS
from vedicway_backend.main import create_app
from vedicway_backend.store import Store


def _app(tmp_path, monkeypatch):
    monkeypatch.setenv("VEDICWAY_ENV", "development")
    monkeypatch.setattr(
        "vedicway_backend.main.warm_instant_runtime",
        lambda: None,
    )
    database = ContentDatabase()
    return create_app(store=Store(tmp_path / "runtime"), content_db=database), database


def test_chart_requires_separate_versioned_consents(tmp_path, monkeypatch) -> None:
    app, _ = _app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/charts",
            json={
                "local_date": "1998-09-15",
                "local_time": "17:28",
                "place_id": "ru-moscow-524901",
            },
            headers={"Idempotency-Key": "without-consent"},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "PERSONAL_DATA_CONSENT_REQUIRED"


def test_consent_audit_is_versioned_and_idempotent(tmp_path, monkeypatch) -> None:
    app, database = _app(tmp_path, monkeypatch)
    payload = {
        "local_date": "1998-09-15",
        "local_time": "17:28",
        "place_id": "ru-moscow-524901",
        "legal": {
            "personal_data": True,
            "personal_data_version": LEGAL_DOCUMENT_VERSIONS["personal_data_consent"],
            "terms": True,
            "terms_version": LEGAL_DOCUMENT_VERSIONS["terms"],
        },
    }
    with TestClient(app) as client:
        first = client.post(
            "/api/v1/charts",
            json=payload,
            headers={"Idempotency-Key": "consent-audit"},
        )
        second = client.post(
            "/api/v1/charts",
            json=payload,
            headers={"Idempotency-Key": "consent-audit"},
        )
        assert first.status_code == 202
        assert second.status_code == 202
        assert first.json()["chart_id"] == second.json()["chart_id"]
    with database.session() as session:
        records = list(session.scalars(select(ConsentRecord)))
    assert {record.consent_type for record in records} == {
        "personal_data",
        "terms",
    }
    assert len(records) == 2


def test_consent_audit_failure_removes_pending_chart_and_personal_data(
    tmp_path, monkeypatch
) -> None:
    app, database = _app(tmp_path, monkeypatch)
    original_add = database._add_consent_record

    def fail_during_terms(database_session, **values):
        original_add(database_session, **values)
        if values["consent_type"] == "terms":
            raise RuntimeError("consent database unavailable")

    monkeypatch.setattr(database, "_add_consent_record", fail_during_terms)
    payload = {
        "local_date": "1998-09-15",
        "local_time": "17:28",
        "place_id": "ru-moscow-524901",
        "legal": {
            "personal_data": True,
            "personal_data_version": LEGAL_DOCUMENT_VERSIONS["personal_data_consent"],
            "terms": True,
            "terms_version": LEGAL_DOCUMENT_VERSIONS["terms"],
        },
    }

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/charts",
            json=payload,
            headers={"Idempotency-Key": "consent-storage-failure"},
        )
        assert response.status_code == 500

    with database.session() as session:
        assert list(session.scalars(select(ConsentRecord))) == []
    with app.state.store._connection() as connection:
        for table in (
            "birth_profiles",
            "charts",
            "chart_access",
            "jobs",
            "outbox_events",
        ):
            assert (
                connection.execute(
                    f"SELECT COUNT(*) AS count FROM {table}"
                ).fetchone()["count"]
                == 0
            )


def test_content_database_rejects_non_postgresql_url(tmp_path, monkeypatch) -> None:
    with pytest.raises(RuntimeError, match="must use PostgreSQL"):
        ContentDatabase("unsupported-database-url")


def test_production_readiness_rejects_placeholders(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VEDICWAY_ENV", "development")
    monkeypatch.setenv("VEDICWAY_DATA_KEY", Fernet.generate_key().decode("ascii"))
    monkeypatch.setattr(
        "vedicway_backend.main.validate_instant_runtime",
        lambda: "test-runtime-fingerprint",
    )
    app = create_app(store=Store(tmp_path / "runtime"), content_db=ContentDatabase())
    monkeypatch.setenv("VEDICWAY_ENV", "production")
    with TestClient(app) as client:
        response = client.get("/api/v1/health/ready")
        assert response.status_code == 503
        reasons = response.json()["reasons"]
        assert "missing:VEDICWAY_LEGAL_OPERATOR_NAME" in reasons


def test_content_database_requires_current_alembic_revision(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VEDICWAY_ENV", "development")
    database = ContentDatabase()
    database.ping(require_migrations=True)

    try:
        with database.engine.begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num = 'stale_revision'"))
        with pytest.raises(RuntimeError):
            database.ping(require_migrations=True)
    finally:
        with database.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE alembic_version SET version_num = "
                    f"'{CONTENT_SCHEMA_REVISION}'"
                )
            )


def test_low_entropy_fingerprints_are_secret_keyed_and_domain_separated(
    monkeypatch,
) -> None:
    monkeypatch.setenv("VEDICWAY_ENV", "development")
    monkeypatch.setenv(
        "VEDICWAY_SIGNING_KEY",
        "development-signing-key-that-is-long-enough",
    )
    ip = "203.0.113.42"
    plain_sha = hashlib.sha256(ip.encode("utf-8")).hexdigest()

    comment_hash = fingerprint_hash(ip, "article-comment-ip")

    assert comment_hash != plain_sha
    assert comment_hash == fingerprint_hash(ip, "article-comment-ip")
    assert comment_hash != fingerprint_hash(ip, "consent-ip")

    monkeypatch.setenv("VEDICWAY_ENV", "production")
    monkeypatch.delenv("VEDICWAY_SIGNING_KEY")
    monkeypatch.delenv("VEDICWAY_PRIVACY_PEPPER", raising=False)
    with pytest.raises(RuntimeError, match="required for fingerprints"):
        fingerprint_hash(ip, "consent-ip")
