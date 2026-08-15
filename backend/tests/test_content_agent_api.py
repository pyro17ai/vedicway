from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from vedicway_backend.content_api import (
    ContentArticlePayload,
    _article_values,
    _content_payload_hash,
)
from vedicway_backend.content_store import ContentDatabase
from vedicway_backend.guide_catalog import GUIDE_ARTICLE_SLOTS, GUIDE_SLOT_BY_SLUG
from vedicway_backend.main import create_app
from vedicway_backend.store import Store

TOKEN = "content-agent-test-token-with-at-least-32-characters"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
GUIDE_SLUG = "kak-chitat-natalnuyu-kartu"


def _app(tmp_path, monkeypatch):
    monkeypatch.setenv("VEDICWAY_SEO_AGENT_TOKEN", TOKEN)
    monkeypatch.setenv("VEDICWAY_SEO_MIN_ARTICLE_CHARS", "600")
    monkeypatch.setenv("VEDICWAY_PUBLIC_ORIGIN", "https://vedicway.ru")
    database = ContentDatabase()
    return create_app(store=Store(tmp_path / "runtime"), content_db=database)


def _html(marker: str = "") -> str:
    paragraph = (
        "Натальная карта читается последовательно: сначала асцендент, затем управитель "
        "первого дома и только после этого аспекты планет."
    )
    return (
        "<h2>От общего рисунка к деталям</h2>"
        f"<p>{paragraph * 6}</p>"
        "<blockquote><p>Одна позиция не описывает человека целиком.</p></blockquote>"
        f"{marker}"
        "<h3>Порядок проверки</h3>"
        "<ol><li>Найдите асцендент.</li><li>Проверьте управителя.</li></ol>"
        f"<p>{paragraph * 6}</p>"
    )


def _payload(
    *,
    section: str,
    slug: str,
    title: str | None = None,
    difficulty: str | None = None,
    category: str | None = None,
    content_html: str | None = None,
) -> dict[str, object]:
    slot = GUIDE_SLOT_BY_SLUG.get(slug) if section == "guide" else None
    resolved_title = title or (slot.label if slot else "Как читать натальную карту")
    resolved_difficulty = difficulty or (slot.difficulty if slot else "beginner")
    resolved_category = category or (slot.category if slot else "Основы астрологии")
    return {
        "section": section,
        "difficulty": resolved_difficulty,
        "title": resolved_title,
        "slug": slug,
        "category": resolved_category,
        "excerpt": (
            "Последовательный разбор натальной карты: асцендент, управитель первого "
            "дома и проверка выводов по аспектам."
        ),
        "content_html": content_html or _html(),
        "cover_image_url": "/assets/results-space-v2.png",
        "cover_image_alt": "Натальная карта с отмеченными домами",
        "seo_title": f"{resolved_title}: практический порядок чтения",
        "meta_description": (
            "Разбираем порядок чтения натальной карты от асцендента до аспектов, "
            "чтобы выводы оставались связными и проверяемыми."
        ),
        "focus_keyphrase": "как читать натальную карту",
        "tags": ["натальная карта", "основы"],
        "schema_extra": {
            "about": {"@type": "Thing", "name": "Натальная карта"},
            "learningResourceType": "Практическое руководство",
        },
        "author_name": "Редакция VedicWay",
    }


def _headers(payload: dict[str, object], key: str) -> dict[str, str]:
    parsed = ContentArticlePayload.model_validate(payload)
    digest = _content_payload_hash(parsed)
    return {
        **AUTH,
        "Idempotency-Key": f"{key}:{digest[:32]}",
        "X-Content-SHA256": digest,
    }


def _publish(
    client: TestClient,
    payload: dict[str, object],
    *,
    key: str,
    revision: int | None = None,
):
    section = str(payload["section"])
    slug = str(payload["slug"])
    headers = _headers(payload, key)
    if revision is not None:
        headers["If-Match"] = str(revision)
    return client.put(
        f"/internal/content-agent/{section}/articles/{slug}",
        json=payload,
        headers=headers,
    )


def test_html_gate_sanitizes_content_and_renders_complete_article_seo(
    tmp_path, monkeypatch
) -> None:
    app = _app(tmp_path, monkeypatch)
    unsafe = _html(
        '<aside data-kind="note"><p onclick="alert(1)">Проверяйте время рождения.</p></aside>'
        '<script>alert("xss")</script>'
        '<p><a href="javascript:alert(1)">опасная ссылка</a></p>'
        '<p><a href="//tracker.example/path">ссылка без схемы</a></p>'
        '<img src="https://tracker.example/pixel.png" alt="Внешний пиксель">'
        '<img src="/assets/results-space-light.png" alt="Локальная схема" width="1672" height="941">'
    )
    payload = _payload(section="guide", slug=GUIDE_SLUG, content_html=unsafe)

    with TestClient(app) as client:
        assert client.get("/internal/content-agent/health").status_code == 401
        created = _publish(client, payload, key="guide-html-create-0001")
        assert created.status_code == 200, created.text
        article = created.json()["article"]
        assert article["section"] == "guide"
        assert article["difficulty"] == "beginner"
        assert article["canonical_url"] == f"https://vedicway.ru/guide/{GUIDE_SLUG}"
        assert "onclick" not in article["content_html"]
        assert "<script" not in article["content_html"]
        assert "javascript:" not in article["content_html"]
        assert "//tracker.example" not in article["content_html"]
        assert '<aside data-kind="note">' in article["content_html"]
        assert "tracker.example" not in article["content_html"]
        assert 'src="/assets/results-space-light.png"' in article["content_html"]
        assert len(article["content_sections"]) == 2

        public = client.get(f"/api/v1/content/guide/articles/{GUIDE_SLUG}")
        assert public.status_code == 200
        assert public.json()["difficulty_label"] == "Новичок"

        page = client.get(f"/internal/seo/guide/articles/{GUIDE_SLUG}/page")
        assert page.status_code == 200
        assert page.text.count('data-content-cta="calculate-chart"') == 2
        assert 'data-reading-progress="true"' in page.text
        assert f'<link rel="canonical" href="https://vedicway.ru/guide/{GUIDE_SLUG}"' in page.text
        assert '"@type":"Article"' in page.text
        assert '"@type":"BreadcrumbList"' in page.text
        assert '"educationalLevel":"Beginner"' in page.text
        assert '"isAccessibleForFree":true' in page.text
        assert '"wordCount":' in page.text
        assert 'property="article:published_time"' in page.text
        assert 'data-vedicway-seo-schema="ssr"' in page.text
        assert 'id="vedicway-seo-bootstrap"' in page.text
        assert '"kind":"article"' in page.text
        assert 'href="/about">Редакция VedicWay</a>' in page.text
        assert "Источники и редакция" in page.text
        assert "<script>alert" not in page.text


def test_article_seo_title_branding_respects_60_character_limit(
    tmp_path, monkeypatch
) -> None:
    app = _app(tmp_path, monkeypatch)
    short_title = "A" * 49
    long_title = "B" * 50
    short_payload = _payload(section="blog", slug="short-seo-title")
    short_payload["seo_title"] = short_title
    long_payload = _payload(section="blog", slug="long-seo-title")
    long_payload["seo_title"] = long_title

    with TestClient(app) as client:
        assert _publish(client, short_payload, key="short-seo-title-0001").status_code == 200
        assert _publish(client, long_payload, key="long-seo-title-00001").status_code == 200

        short_page = client.get("/internal/seo/blog/articles/short-seo-title/page")
        branded_short_title = f"{short_title} | VedicWay"
        assert len(branded_short_title) == 60
        assert f"<title>{branded_short_title}</title>" in short_page.text
        assert short_page.text.count(f'content="{branded_short_title}"') == 2

        long_page = client.get("/internal/seo/blog/articles/long-seo-title/page")
        assert f"<title>{long_title}</title>" in long_page.text
        assert f"{long_title} | VedicWay" not in long_page.text
        assert long_page.text.count(f'content="{long_title}"') == 2


def test_guide_has_code_owned_slots_while_blog_accepts_new_slugs(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    unknown = _payload(section="guide", slug="neodobrennyy-adres")

    with TestClient(app) as client:
        rejected = _publish(client, unknown, key="unknown-guide-slot-001")
        assert rejected.status_code == 409
        assert rejected.json()["error"]["code"] == "GUIDE_SLOT_NOT_ALLOWED"

        mismatch = _payload(
            section="guide",
            slug=GUIDE_SLUG,
            category="Основы астрологии",
        )
        mismatch_rejected = _publish(
            client,
            mismatch,
            key="guide-catalog-mismatch-001",
        )
        assert mismatch_rejected.status_code == 409
        assert (
            mismatch_rejected.json()["error"]["code"]
            == "GUIDE_CATALOG_METADATA_MISMATCH"
        )

        blog = {**unknown, "section": "blog"}
        accepted = _publish(client, blog, key="new-blog-article-0001")
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["article"]["canonical_url"] == (
            "https://vedicway.ru/blog/neodobrennyy-adres"
        )
        page = client.get("/internal/seo/blog/articles/neodobrennyy-adres/page")
        assert '"@type":"BlogPosting"' in page.text

        assert client.get("/api/v1/admin/me").status_code == 404
        assert client.post("/api/v1/admin/articles", json={}).status_code == 404


def test_complete_guide_catalog_gives_each_article_three_distinct_recommendations(
    tmp_path, monkeypatch
) -> None:
    app = _app(tmp_path, monkeypatch)

    with TestClient(app) as client:
        health = client.get("/internal/content-agent/health", headers=AUTH)
        assert health.json()["guide_slots"] == 202
        assert health.json()["guide_categories"] == 4
        assert len(GUIDE_ARTICLE_SLOTS) == 202
        for index, slot in enumerate(GUIDE_ARTICLE_SLOTS):
            payload = _payload(
                section="guide",
                slug=slot.slug,
            )
            response = _publish(client, payload, key=f"guide-related-{index:04d}")
            assert response.status_code == 200, response.text

        for slot in GUIDE_ARTICLE_SLOTS:
            article = client.get(f"/api/v1/content/guide/articles/{slot.slug}").json()
            related = article["related"]
            assert len(related) == 3
            assert len({item["slug"] for item in related}) == 3
            assert all(item["slug"] != slot.slug for item in related)


def test_schema_extra_rejects_fields_outside_the_supported_contract(
    tmp_path, monkeypatch
) -> None:
    app = _app(tmp_path, monkeypatch)
    payload = _payload(section="guide", slug=GUIDE_SLUG)
    payload["schema_extra"] = {"@id": "https://untrusted.example/article"}

    with TestClient(app) as client:
        response = client.put(
            f"/internal/content-agent/guide/articles/{GUIDE_SLUG}",
            json=payload,
            headers={
                **AUTH,
                "Idempotency-Key": "invalid-schema-extra-0001",
                "X-Content-SHA256": "0" * 64,
            },
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "REQUEST_INVALID"

    with pytest.raises(ValidationError, match="Schema.org"):
        ContentArticlePayload.model_validate(payload)


def test_legacy_guide_rows_outside_code_catalog_stay_private(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    payload = ContentArticlePayload.model_validate(
        _payload(section="guide", slug="staryy-ruchnoy-material")
    )

    with TestClient(app) as client:
        database = app.state.content_db
        database.save_article(_article_values(payload, database))

        listing = client.get("/api/v1/content/guide/articles")
        assert listing.json() == {"items": [], "total": 0}
        assert (
            client.get("/api/v1/content/guide/articles/staryy-ruchnoy-material").status_code == 404
        )
        assert "staryy-ruchnoy-material" not in client.get("/sitemap.xml").text
        assert "staryy-ruchnoy-material" not in client.get("/feed/dzen.xml").text


def test_search_difficulty_and_three_related_articles_are_deterministic(
    tmp_path, monkeypatch
) -> None:
    app = _app(tmp_path, monkeypatch)
    payloads = [
        _payload(
            section="blog",
            slug=f"razbor-karty-{index}",
            title=f"Разбор карты {index}",
            difficulty="beginner" if index < 2 else "expert",
        )
        for index in range(4)
    ]

    with TestClient(app) as client:
        for index, payload in enumerate(payloads):
            response = _publish(client, payload, key=f"blog-related-{index:04d}")
            assert response.status_code == 200, response.text

        filtered = client.get(
            "/api/v1/content/blog/articles",
            params={
                "q": "карты 1",
                "difficulty": "beginner",
                "category": "Основы астрологии",
            },
        )
        assert [item["slug"] for item in filtered.json()["items"]] == ["razbor-karty-1"]
        wrong_category = client.get(
            "/api/v1/content/blog/articles",
            params={"difficulty": "beginner", "category": "Время и циклы"},
        )
        assert wrong_category.json() == {"items": [], "total": 0}

        article = client.get("/api/v1/content/blog/articles/razbor-karty-0").json()
        related = article["related"]
        assert len(related) == 3
        assert len({item["id"] for item in related}) == 3
        assert all(item["id"] != article["id"] for item in related)
        repeated = client.get("/api/v1/content/blog/articles/razbor-karty-0").json()
        assert [item["id"] for item in repeated["related"]] == [item["id"] for item in related]


def test_every_reader_can_add_plain_text_comments_without_html_execution(
    tmp_path, monkeypatch
) -> None:
    app = _app(tmp_path, monkeypatch)
    payload = _payload(section="guide", slug=GUIDE_SLUG)

    with TestClient(app) as client:
        assert _publish(client, payload, key="guide-comments-create-01").status_code == 200
        empty = client.get(f"/api/v1/content/guide/articles/{GUIDE_SLUG}/comments")
        assert empty.json() == {"items": []}

        created = client.post(
            f"/api/v1/content/guide/articles/{GUIDE_SLUG}/comments",
            json={
                "display_name": "Анна",
                "body": "<img src=x onerror=alert(1)> Спасибо за порядок чтения!",
                "website": "",
            },
            headers={"Origin": "http://testserver"},
        )
        assert created.status_code == 201, created.text
        assert created.json()["display_name"] == "Анна"
        assert created.json()["body"].startswith("<img")

        comments = client.get(f"/api/v1/content/guide/articles/{GUIDE_SLUG}/comments").json()[
            "items"
        ]
        assert len(comments) == 1
        page = client.get(f"/internal/seo/guide/articles/{GUIDE_SLUG}/page")
        assert "&lt;img src=x onerror=alert(1)&gt;" in page.text
        assert "<img src=x onerror" not in page.text

        honeypot = client.post(
            f"/api/v1/content/guide/articles/{GUIDE_SLUG}/comments",
            json={
                "display_name": "Bot",
                "body": "Спам-сообщение достаточной длины.",
                "website": "https://spam.example",
            },
            headers={"Origin": "http://testserver"},
        )
        assert honeypot.status_code == 201
        assert (
            len(client.get(f"/api/v1/content/guide/articles/{GUIDE_SLUG}/comments").json()["items"])
            == 1
        )
        blank = client.post(
            f"/api/v1/content/guide/articles/{GUIDE_SLUG}/comments",
            json={"display_name": "  ", "body": "        ", "website": ""},
            headers={"Origin": "http://testserver"},
        )
        assert blank.status_code == 400
        assert blank.json()["error"]["code"] == "REQUEST_INVALID"


def test_empty_hubs_are_noindex_and_absent_from_sitemap(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)

    with TestClient(app) as client:
        guide_hub = client.get("/internal/seo/guide/page")
        blog_hub = client.get("/internal/seo/blog/page")
        assert '<meta name="robots" content="noindex, follow" />' in guide_hub.text
        assert '<meta name="robots" content="noindex, follow" />' in blog_hub.text

        empty_sitemap = client.get("/sitemap.xml")
        assert "https://vedicway.ru/guide</loc>" not in empty_sitemap.text
        assert "https://vedicway.ru/blog</loc>" not in empty_sitemap.text
        assert "https://vedicway.ru/about</loc>" in empty_sitemap.text

        guide = _payload(section="guide", slug=GUIDE_SLUG)
        assert _publish(client, guide, key="conditional-guide-hub-0001").status_code == 200

        published_guide_hub = client.get("/internal/seo/guide/page")
        assert (
            '<meta name="robots" content="index, follow, max-image-preview:large" />'
            in published_guide_hub.text
        )
        sitemap = client.get("/sitemap.xml")
        assert "https://vedicway.ru/guide</loc>" in sitemap.text
        assert "https://vedicway.ru/blog</loc>" not in sitemap.text
        assert f"https://vedicway.ru/guide/{GUIDE_SLUG}</loc>" in sitemap.text


def test_generated_seo_surfaces_support_head_requests(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    guide = _payload(section="guide", slug=GUIDE_SLUG)

    with TestClient(app) as client:
        assert _publish(client, guide, key="head-guide-article-0001").status_code == 200

        targets = (
            "/internal/seo/guide/page",
            f"/internal/seo/guide/articles/{GUIDE_SLUG}/page",
            "/sitemap.xml",
            "/api/v1/seo/sitemap.xml",
            "/feed/dzen.xml",
            "/api/v1/seo/dzen.xml",
        )
        for target in targets:
            response = client.head(target)
            assert response.status_code == 200, target
            assert response.content == b"", target


def test_sitemap_keeps_hubs_and_both_article_sections(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    guide = _payload(section="guide", slug=GUIDE_SLUG)
    blog = _payload(section="blog", slug="prognoz-na-retrogradnyy-period")

    with TestClient(app) as client:
        assert _publish(client, guide, key="sitemap-guide-0001").status_code == 200
        assert _publish(client, blog, key="sitemap-blog-00001").status_code == 200
        guide_hub = client.get("/internal/seo/guide/page")
        assert guide_hub.status_code == 200
        assert f'href="/guide/{GUIDE_SLUG}"' in guide_hub.text
        assert '"@type":"CollectionPage"' in guide_hub.text
        assert '"@type":"ItemList"' in guide_hub.text
        assert '"numberOfItems":1' in guide_hub.text
        assert 'data-vedicway-seo-schema="ssr"' in guide_hub.text
        assert 'id="vedicway-seo-bootstrap"' in guide_hub.text
        assert '"kind":"hub"' in guide_hub.text
        assert 'class="guide-atlas-hero"' in guide_hub.text
        assert 'id="guide-route"' in guide_hub.text
        assert 'aria-valuenow="1"' in guide_hub.text
        assert "Четыре раздела, единая библиотека" in guide_hub.text
        assert "Основы астрологии" in guide_hub.text
        assert "Практика чтения карты" in guide_hub.text
        assert "prognoz-na-retrogradnyy-period" not in guide_hub.text

        blog_hub = client.get("/internal/seo/blog/page")
        assert blog_hub.status_code == 200
        assert (
            '<meta name="robots" content="index, follow, max-image-preview:large" />'
            in blog_hub.text
        )
        assert 'href="/blog/prognoz-na-retrogradnyy-period"' in blog_hub.text
        assert 'class="content-hub__hero"' in blog_hub.text
        assert 'id="guide-route"' not in blog_hub.text
        assert GUIDE_SLUG not in blog_hub.text

        sitemap = client.get("/sitemap.xml")
        assert sitemap.status_code == 200
        root = json.loads(json.dumps(sitemap.text))
        assert "https://vedicway.ru/guide</loc>" in root
        assert "https://vedicway.ru/blog</loc>" in root
        assert "https://vedicway.ru/about</loc>" in root
        assert "https://vedicway.ru/methodology</loc>" in root
        assert "https://vedicway.ru/editorial-policy</loc>" in root
        assert f"https://vedicway.ru/guide/{GUIDE_SLUG}" in root
        assert "https://vedicway.ru/blog/prognoz-na-retrogradnyy-period" in root

        feed = client.get("/feed/dzen.xml")
        assert feed.status_code == 200
        assert "<link>https://vedicway.ru/</link>" in feed.text
