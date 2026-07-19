from __future__ import annotations

import hashlib
import io

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select, text

from vedicway_backend.content_store import (
    PASSWORD_HASH,
    ConsentRecord,
    ContentDatabase,
    User,
    fingerprint_hash,
)
from vedicway_backend.main import create_app
from vedicway_backend.store import Store

ORIGIN_HEADERS = {"Origin": "http://testserver", "X-Admin-Request": "1"}


def _app(tmp_path, monkeypatch):
    monkeypatch.setenv("VEDICWAY_BOOTSTRAP_ADMIN_EMAIL", "admin@example.ru")
    monkeypatch.setenv("VEDICWAY_BOOTSTRAP_ADMIN_PASSWORD", "very-long-test-password")
    database = ContentDatabase(f"sqlite:///{(tmp_path / 'content.sqlite3').as_posix()}")
    return create_app(store=Store(tmp_path / "runtime"), content_db=database), database


def _login(client: TestClient) -> str:
    response = client.post(
        "/api/v1/admin/auth/login",
        json={"email": "admin@example.ru", "password": "very-long-test-password"},
        headers=ORIGIN_HEADERS,
    )
    assert response.status_code == 200
    assert "HttpOnly" in response.headers.get("set-cookie", "")
    assert "SameSite=strict" in response.headers.get("set-cookie", "")
    token = client.cookies.get("vw_admin_csrf")
    assert token
    return token


def _edit_headers(csrf: str, revision: int) -> dict[str, str]:
    return {
        "Origin": "http://testserver",
        "X-CSRF-Token": csrf,
        "If-Match": f'"{revision}"',
    }


def _article(
    cover: str | None = None, cover_id: str | None = None, status: str = "draft"
) -> dict[str, object]:
    return {
        "title": "Как читать первый дом",
        "slug": "kak-chitat-pervyy-dom",
        "category": "Основы астрологии",
        "excerpt": "Разбираем первый дом и учимся связывать знак, планеты и жизненный контекст.",
        "content": "Первый дом описывает способ проявления человека. " * 8,
        "cover_media_id": cover_id,
        "body_media_ids": [],
        "cover_image_url": cover,
        "cover_image_alt": "Круг натальной карты" if cover else "",
        "seo_title": "Как читать первый дом натальной карты",
        "meta_description": "Подробное объяснение первого дома натальной карты: знак, планеты, управитель и правила последовательного чтения карты.",
        "focus_keyphrase": "первый дом натальной карты",
        "canonical_url": "https://vedicway.ru/guide/kak-chitat-pervyy-dom",
        "author_name": "Редакция VedicWay",
        "status": status,
    }


def test_admin_auth_rbac_article_and_media_flow(tmp_path, monkeypatch) -> None:
    app, database = _app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        assert client.get("/api/v1/admin/me").status_code == 401
        csrf = _login(client)
        assert client.get("/api/v1/admin/me").json()["user"]["role"] == "admin"

        missing_csrf = client.post(
            "/api/v1/admin/articles", json=_article(), headers={"Origin": "http://testserver"}
        )
        assert missing_csrf.status_code == 403

        mismatched_csrf = client.post(
            "/api/v1/admin/articles",
            json=_article(),
            headers={"Origin": "http://testserver", "X-CSRF-Token": "wrong-token"},
        )
        assert mismatched_csrf.status_code == 403

        cross_origin = client.post(
            "/api/v1/admin/articles",
            json=_article(),
            headers={"Origin": "https://attacker.example", "X-CSRF-Token": csrf},
        )
        assert cross_origin.status_code == 403

        source = Image.new("RGB", (1200, 630), (29, 15, 8))
        buffer = io.BytesIO()
        source.save(buffer, "PNG")
        media = client.post(
            "/api/v1/admin/media",
            files={"file": ("cover.png", buffer.getvalue(), "image/png")},
            data={"purpose": "cover", "alt": "Круг натальной карты", "title": "", "caption": ""},
            headers={"Origin": "http://testserver", "X-CSRF-Token": csrf},
        )
        assert media.status_code == 201
        asset = media.json()["asset"]
        assert asset["width"] == 1200
        assert [item["width"] for item in asset["sources"]] == [640, 960, 1200]
        cover = asset["url"]
        assert client.get(cover).status_code == 404

        draft = client.post(
            "/api/v1/admin/articles",
            json=_article(cover=cover, cover_id=asset["id"]),
            headers={"Origin": "http://testserver", "X-CSRF-Token": csrf},
        )
        assert draft.status_code == 201
        assert client.get(cover).status_code == 404
        assert client.get("/api/v1/content/articles").json()["items"] == []
        assert "kak-chitat-pervyy-dom" not in client.get("/sitemap.xml").text

        published_payload = _article(cover=cover, cover_id=asset["id"], status="published")
        published = client.put(
            f"/api/v1/admin/articles/{draft.json()['id']}",
            json=published_payload,
            headers=_edit_headers(csrf, draft.json()["revision"]),
        )
        assert published.status_code == 200
        published_media = client.get(cover)
        assert published_media.status_code == 200
        assert published_media.headers["content-type"] == "image/webp"
        assert published_media.headers["cache-control"] == "public, max-age=300"
        assert client.get(cover.replace("1200.webp", "960.webp")).status_code == 200
        assert client.get(cover.replace("1200.webp", "9999.webp")).status_code == 404
        public = client.get("/api/v1/content/articles").json()["items"]
        assert public[0]["cover_image_url"] == cover
        assert public[0]["coverImage"]["id"] == asset["id"]
        assert client.get("/api/v1/content/articles/kak-chitat-pervyy-dom").status_code == 200
        sitemap = client.get("/api/v1/seo/sitemap.xml")
        assert sitemap.status_code == 200
        assert "https://vedicway.ru/guide/kak-chitat-pervyy-dom" in sitemap.text
        assert sitemap.text.count("kak-chitat-pervyy-dom") == 1

        renamed_payload = dict(published_payload)
        renamed_payload["slug"] = "novyy-adres"
        renamed_payload["canonical_url"] = "https://vedicway.ru/guide/novyy-adres"
        renamed = client.put(
            f"/api/v1/admin/articles/{draft.json()['id']}",
            json=renamed_payload,
            headers=_edit_headers(csrf, published.json()["revision"]),
        )
        assert renamed.status_code == 409
        assert renamed.json()["error"]["code"] == "ARTICLE_SLUG_IMMUTABLE"

        unpublished_payload = dict(published_payload)
        unpublished_payload["status"] = "draft"
        unpublished = client.put(
            f"/api/v1/admin/articles/{draft.json()['id']}",
            json=unpublished_payload,
            headers=_edit_headers(csrf, published.json()["revision"]),
        )
        assert unpublished.status_code == 200
        assert unpublished.json()["published_at"] is not None
        assert client.get(cover).status_code == 404
        stale_payload = dict(unpublished_payload)
        stale_payload["title"] = "Устаревшая правка"
        stale = client.put(
            f"/api/v1/admin/articles/{draft.json()['id']}",
            json=stale_payload,
            headers=_edit_headers(csrf, published.json()["revision"]),
        )
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "ARTICLE_REVISION_CONFLICT"
        rename_after_unpublish = dict(unpublished_payload)
        rename_after_unpublish["slug"] = "obhod-posle-snyatiya"
        rename_after_unpublish["canonical_url"] = "https://vedicway.ru/guide/obhod-posle-snyatiya"
        blocked_after_unpublish = client.put(
            f"/api/v1/admin/articles/{draft.json()['id']}",
            json=rename_after_unpublish,
            headers=_edit_headers(csrf, unpublished.json()["revision"]),
        )
        assert blocked_after_unpublish.status_code == 409

        external_canonical = dict(_article())
        external_canonical["slug"] = "vneshniy-canonical"
        external_canonical["canonical_url"] = "https://example.org/guide/vneshniy-canonical"
        assert client.post(
            "/api/v1/admin/articles",
            json=external_canonical,
            headers={"Origin": "http://testserver", "X-CSRF-Token": csrf},
        ).status_code == 400

        in_use = client.delete(
            f"/api/v1/admin/media/{asset['id']}",
            headers={"Origin": "http://testserver", "X-CSRF-Token": csrf},
        )
        assert in_use.status_code == 409

        removed_article = client.delete(
            f"/api/v1/admin/articles/{draft.json()['id']}",
            headers={"Origin": "http://testserver", "X-CSRF-Token": csrf},
        )
        assert removed_article.status_code == 204
        removed_media = client.delete(
            f"/api/v1/admin/media/{asset['id']}",
            headers={"Origin": "http://testserver", "X-CSRF-Token": csrf},
        )
        assert removed_media.status_code == 204
        assert client.get(cover).status_code == 404

        logout = client.post(
            "/api/v1/admin/auth/logout",
            headers={"Origin": "http://testserver", "X-CSRF-Token": csrf},
        )
        assert logout.status_code == 204
        assert client.get("/api/v1/admin/me").status_code == 401

    with database.session() as session:
        user = User(
            email="reader@example.ru",
            display_name="Читатель",
            password_hash=PASSWORD_HASH.hash("another-long-password"),
            role="user",
        )
        session.add(user)
        session.flush()
        user_id = user.id
    with database.session() as session:
        regular_user = session.get(User, user_id)
        assert regular_user is not None
        session_token, _ = database.create_admin_session(regular_user, None, None)
    with TestClient(app) as reader:
        reader.cookies.set("vw_admin", session_token)
        assert reader.get("/api/v1/admin/me").status_code == 403


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
            "personal_data_version": "2026-07-19",
            "terms": True,
            "terms_version": "2026-07-19",
        },
    }
    with TestClient(app) as client:
        first = client.post(
            "/api/v1/charts", json=payload, headers={"Idempotency-Key": "consent-audit"}
        )
        second = client.post(
            "/api/v1/charts", json=payload, headers={"Idempotency-Key": "consent-audit"}
        )
        assert first.status_code == 202
        assert second.status_code == 202
        assert first.json()["chart_id"] == second.json()["chart_id"]
    with database.session() as session:
        records = list(session.scalars(select(ConsentRecord)))
    assert {record.consent_type for record in records} == {"personal_data", "terms"}
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
            "personal_data_version": "2026-07-19",
            "terms": True,
            "terms_version": "2026-07-19",
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
        for table in ("birth_profiles", "charts", "chart_access", "jobs", "outbox_events"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_production_readiness_rejects_placeholders_and_sqlite(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VEDICWAY_ENV", "development")
    monkeypatch.setenv("VEDICWAY_DATA_KEY", Fernet.generate_key().decode("ascii"))
    monkeypatch.delenv("VEDICWAY_BOOTSTRAP_ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("VEDICWAY_BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    database = ContentDatabase(f"sqlite:///{(tmp_path / 'content.sqlite3').as_posix()}")
    app = create_app(store=Store(tmp_path / "runtime"), content_db=database)
    monkeypatch.setenv("VEDICWAY_ENV", "production")
    with TestClient(app) as client:
        response = client.get("/api/v1/health/ready")
        assert response.status_code == 503
        reasons = response.json()["reasons"]
        assert "database:postgresql_required" in reasons
        assert "missing:VEDICWAY_LEGAL_OPERATOR_NAME" in reasons


def test_content_database_requires_current_alembic_revision(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VEDICWAY_ENV", "development")
    database = ContentDatabase(f"sqlite:///{(tmp_path / 'schema.sqlite3').as_posix()}")
    database.initialize()
    with pytest.raises(RuntimeError):
        database.ping(require_migrations=True)

    with database.engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(text("INSERT INTO alembic_version (version_num) VALUES ('20260719_01')"))
    database.ping(require_migrations=True)

    with database.engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = 'stale_revision'"))
    with pytest.raises(RuntimeError):
        database.ping(require_migrations=True)


def test_low_entropy_fingerprints_are_secret_keyed_and_domain_separated(monkeypatch) -> None:
    monkeypatch.setenv("VEDICWAY_ENV", "development")
    monkeypatch.setenv("VEDICWAY_SIGNING_KEY", "development-signing-key-that-is-long-enough")
    ip = "203.0.113.42"
    plain_sha = hashlib.sha256(ip.encode("utf-8")).hexdigest()

    admin_hash = fingerprint_hash(ip, "admin-ip")

    assert admin_hash != plain_sha
    assert admin_hash == fingerprint_hash(ip, "admin-ip")
    assert admin_hash != fingerprint_hash(ip, "consent-ip")

    monkeypatch.setenv("VEDICWAY_ENV", "production")
    monkeypatch.delenv("VEDICWAY_SIGNING_KEY")
    monkeypatch.delenv("VEDICWAY_PRIVACY_PEPPER", raising=False)
    with pytest.raises(RuntimeError, match="required for fingerprints"):
        fingerprint_hash(ip, "consent-ip")
