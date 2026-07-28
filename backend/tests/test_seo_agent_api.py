from __future__ import annotations

import hashlib
import io
import xml.etree.ElementTree as ET

from fastapi.testclient import TestClient
from PIL import Image

from vedicway_backend.admin_api import (
    ArticlePayload,
    _article_payload_hash,
    _media_payload_hash,
)
from vedicway_backend.content_store import ContentDatabase
from vedicway_backend.main import create_app
from vedicway_backend.store import Store

TOKEN = "seo-agent-test-token-with-at-least-32-characters"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def _app(tmp_path, monkeypatch):
    monkeypatch.setenv("VEDICWAY_SEO_AGENT_TOKEN", TOKEN)
    monkeypatch.setenv("VEDICWAY_SEO_MIN_ARTICLE_CHARS", "2000")
    monkeypatch.setenv("VEDICWAY_PUBLIC_ORIGIN", "https://vedicway.ru")
    database = ContentDatabase(f"sqlite:///{(tmp_path / 'content.sqlite3').as_posix()}")
    return create_app(store=Store(tmp_path / "runtime"), content_db=database)


def _cover() -> bytes:
    image = Image.new("RGB", (1200, 630), (39, 22, 12))
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def _article(cover_id: str, cover_url: str, body_id: str) -> dict[str, object]:
    content = (
        "## Как читать первый дом\n\n"
        "Первый дом описывает способ проявления человека и видимую манеру действия. " * 35
        + f"\n\n{{{{media:{body_id}}}}}\n\n"
        + "## Проверка трактовки\n\n"
        + "Сопоставьте знак, управителя дома и аспекты. " * 35
        + "\n\nПодробнее о расчете читайте в [натальной карте](/chart/new)."
    )
    return {
        "title": "Как читать первый дом натальной карты",
        "slug": "kak-chitat-pervyy-dom",
        "category": "Основы астрологии",
        "excerpt": "Практическая схема чтения первого дома с проверкой управителя, знака и аспектов натальной карты.",
        "content": content,
        "cover_media_id": cover_id,
        "body_media_ids": [body_id],
        "cover_image_url": cover_url,
        "cover_image_alt": "Первый дом натальной карты",
        "seo_title": "Первый дом натальной карты: как читать",
        "meta_description": "Разбираем первый дом натальной карты: знак, управитель, аспекты и порядок проверки трактовки на практическом примере.",
        "focus_keyphrase": "первый дом натальной карты",
        "canonical_url": "https://vedicway.ru/guide/kak-chitat-pervyy-dom",
        "author_name": "Редакция VedicWay",
        "status": "published",
    }


def _upload(
    client: TestClient, purpose: str, key: str, *, alt: str | None = None
) -> dict[str, object]:
    raw = _cover()
    digest = hashlib.sha256(raw).hexdigest()
    resolved_alt = alt or f"{purpose} image"
    request_hash = _media_payload_hash(digest, purpose, resolved_alt, "", "")
    response = client.post(
        "/internal/seo-agent/media",
        files={"file": (f"{purpose}.png", raw, "image/png")},
        data={"purpose": purpose, "alt": resolved_alt, "title": "", "caption": ""},
        headers={
            **AUTH,
            "Idempotency-Key": f"{key}:{request_hash[:32]}",
            "X-Content-SHA256": digest,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _article_headers(payload: dict[str, object], key: str) -> dict[str, str]:
    parsed = ArticlePayload.model_validate(payload)
    digest = _article_payload_hash(parsed)
    return {
        **AUTH,
        "Idempotency-Key": f"{key}:{digest[:32]}",
        "X-Content-SHA256": digest,
    }


def test_internal_agent_api_is_scoped_idempotent_and_revision_safe(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        assert client.get("/internal/seo-agent/health").status_code == 401
        assert client.get("/internal/seo-agent/health", headers=AUTH).json()["database_boundary"] == "content-api-only"

        cover = _upload(client, "cover", "media-cover-0001")
        replay = _upload(client, "cover", "media-cover-0001")
        assert replay["idempotent_replay"] is True
        assert replay["asset"]["id"] == cover["asset"]["id"]
        revised_alt = _upload(
            client, "cover", "media-cover-0001", alt="revised cover image"
        )
        assert revised_alt["idempotent_replay"] is False
        assert revised_alt["asset"]["id"] != cover["asset"]["id"]
        body = _upload(client, "body", "media-body-000001")

        payload = _article(
            str(cover["asset"]["id"]),
            str(cover["asset"]["url"]),
            str(body["asset"]["id"]),
        )
        path = f"/internal/seo-agent/articles/{payload['slug']}"
        created = client.put(path, json=payload, headers=_article_headers(payload, "article-create-001"))
        assert created.status_code == 200, created.text
        assert created.json()["idempotent_replay"] is False

        repeated = client.put(path, json=payload, headers=_article_headers(payload, "article-create-001"))
        assert repeated.status_code == 200
        assert repeated.json()["idempotent_replay"] is True

        changed = dict(payload)
        changed["title"] = "Как последовательно читать первый дом натальной карты"
        without_revision = client.put(path, json=changed, headers=_article_headers(changed, "article-update-001"))
        assert without_revision.status_code == 428
        revision = created.json()["article"]["revision"]
        reused_key = client.put(
            path,
            json=changed,
            headers={
                **_article_headers(changed, "article-update-001"),
                "Idempotency-Key": _article_headers(payload, "article-create-001")[
                    "Idempotency-Key"
                ],
                "If-Match": str(revision),
            },
        )
        assert reused_key.status_code == 400
        assert reused_key.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONTENT_MISMATCH"
        updated = client.put(
            path,
            json=changed,
            headers={**_article_headers(changed, "article-update-001"), "If-Match": str(revision)},
        )
        assert updated.status_code == 200
        assert updated.json()["article"]["title"] == changed["title"]

        page = client.get(f"/internal/seo/articles/{payload['slug']}/page")
        assert page.status_code == 200
        assert str(body["asset"]["url"]) in page.text
        assert 'href="https://vedicway.ru/chart/new"' in page.text
        assert "{{media:" not in page.text
        stored_payload = dict(changed)
        stored_payload["body_media_ids"] = [str(body["asset"]["id"])]
        expected_request_hash = _article_payload_hash(
            ArticlePayload.model_validate(stored_payload)
        )
        assert expected_request_hash in page.text

        feed = client.get("/api/v1/seo/dzen.xml")
        assert feed.status_code == 200
        assert feed.headers["content-type"].startswith("application/rss+xml")
        assert "<yandex:full-text>" in feed.text
        assert "<category>native-draft</category>" in feed.text
        assert "kak-chitat-pervyy-dom" in feed.text
        assert f"vedicway-request-sha256:{expected_request_hash}" in feed.text
        document = ET.fromstring(feed.content)
        item = document.find("./channel/item")
        assert item is not None
        assert item.findtext("guid") == "https://vedicway.ru/guide/kak-chitat-pervyy-dom"
        assert client.get("/api/v1/seo/dzen/status").json()["rss_ready"] is False


def test_internal_agent_rejects_wrong_hash_and_short_article(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        raw = _cover()
        wrong = client.post(
            "/internal/seo-agent/media",
            files={"file": ("cover.png", raw, "image/png")},
            data={"purpose": "cover", "alt": "cover", "title": "", "caption": ""},
            headers={**AUTH, "Idempotency-Key": "media-wrong-hash-01", "X-Content-SHA256": "0" * 64},
        )
        assert wrong.status_code == 400
        assert wrong.json()["error"]["code"] == "CONTENT_HASH_MISMATCH"

        payload = {
            "title": "Короткая статья",
            "slug": "korotkaya-statya",
            "category": "Основы",
            "excerpt": "Короткое описание материала, которого хватает для базовой проверки публикации на сайте.",
            "content": "Слишком коротко. " * 20,
            "cover_image_url": "https://vedicway.ru/cover.webp",
            "cover_image_alt": "Обложка",
            "meta_description": "Описание короткой статьи, которого достаточно для стандартной проверки метаданных публикации.",
            "status": "published",
        }
        response = client.put(
            "/internal/seo-agent/articles/korotkaya-statya",
            json=payload,
            headers=_article_headers(payload, "short-article-0001"),
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "ARTICLE_TOO_SHORT"
