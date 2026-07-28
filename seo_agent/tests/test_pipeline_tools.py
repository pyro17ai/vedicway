from __future__ import annotations

import hashlib
import json
import sys
import tomllib
from copy import deepcopy
from pathlib import Path

import httpx
import pytest
from PIL import Image

from seo_agent.db import AgentLedger, LedgerError, canonical_json, utc_now
from seo_agent.media import generate_cover
from seo_agent.quality_gate import evaluate
from seo_agent.scheduler import MCP_CONFIG_OVERRIDES, build_codex_command, due_jobs, preflight
from seo_agent.site_client import publish_bundle


def _content() -> str:
    paragraphs = [
        "Дома в натальной карте показывают, в какой жизненной области проявляется планета, знак и ее управитель. "
        "Читатель получит последовательный порядок разбора и сможет проверить трактовку по собственной карте."
    ]
    for index in range(1, 18):
        paragraphs.append(
            f"## Шаг {index}: проверка показателей\n\n"
            f"На шаге {index} сначала найдите знак на куспиде, затем положение управителя и только после этого аспекты. "
            "Запишите наблюдение простыми словами и сверьте его с повторяющимися темами карты. "
            "Один показатель не дает надежного вывода: смысл подтверждает связка дома, планеты и контекста вопроса. "
            f"Контрольный номер этого фрагмента {index} помогает сохранить самостоятельность каждого раздела."
        )
    paragraphs.extend(
        [
            "Рассчитайте исходные положения в [натальной карте](/chart/new), затем вернитесь к схеме разбора.",
            "Смежные определения собраны в [гиде по астрологии](/guide).",
            "Методические основания сверяйте с [документацией Swiss Ephemeris](https://www.astro.com/swisseph/) и "
            "[описанием часовых поясов IANA](https://www.iana.org/time-zones).",
        ]
    )
    return "\n\n".join(paragraphs)


def _manifest(cover: Path) -> dict[str, object]:
    content = _content()
    return {
        "schema_version": "1.0",
        "draft_id": "draft-test-001",
        "claim_token": "claimed-draft-token-with-enough-length",
        "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "article": {
            "title": "Дома в натальной карте: последовательный разбор",
            "slug": "doma-v-natalnoy-karte",
            "category": "Основы астрологии",
            "excerpt": "Практический порядок чтения домов натальной карты с проверкой знака, управителя и аспектов.",
            "content": content,
            "seo_title": "Дома в натальной карте: как читать",
            "meta_description": "Разбираем дома в натальной карте по шагам: знак на куспиде, управитель, планеты и аспекты без оторванных трактовок.",
            "focus_keyphrase": "дома в натальной карте",
            "canonical_url": "https://vedicway.ru/guide/doma-v-natalnoy-karte",
            "author_name": "Редакция VedicWay",
            "status": "published",
        },
        "media": [
            {
                "purpose": "cover",
                "local_path": str(cover),
                "alt_text": "Схема домов в натальной карте",
                "source_kind": "generated",
                "license_note": "Generated locally for VedicWay",
            }
        ],
    }


def _authorize_manifest(manifest: dict[str, object]) -> None:
    ledger = AgentLedger()
    ledger.initialize()
    article = manifest["article"]
    assert isinstance(article, dict)
    now = utc_now()
    with ledger.transaction(immediate=True) as connection:
        connection.execute(
            "INSERT INTO keyword_clusters(id,slug,title,intent,status,created_at,updated_at) VALUES ('cluster-test','cluster-test','Cluster','informational','briefed',?,?)",
            (now, now),
        )
        connection.execute(
            "INSERT INTO content_briefs(id,cluster_id,status,title,primary_query,audience_problem,search_intent,outline_json,evidence_json,internal_links_json,prohibited_claims_json,checksum,created_at) VALUES ('brief-test','cluster-test','consumed','Brief','query','problem','informational','[]','[]','[]','[]','brief-hash',?)",
            (now,),
        )
        connection.execute(
            """INSERT INTO article_drafts(
            id,brief_id,slug,status,title,excerpt,content_markdown,seo_title,meta_description,
            focus_keyphrase,category,author_name,content_hash,quality_report_json,claim_token,
            claim_expires_at,created_at,updated_at,approved_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                manifest["draft_id"],
                "brief-test",
                article["slug"],
                "publishing",
                article["title"],
                article["excerpt"],
                article["content"],
                article["seo_title"],
                article["meta_description"],
                article["focus_keyphrase"],
                article["category"],
                article["author_name"],
                manifest["content_hash"],
                canonical_json({"passed": True, "content_hash": manifest["content_hash"]}),
                manifest["claim_token"],
                "2099-01-01T00:00:00.000Z",
                now,
                now,
                now,
            ),
        )
    media = manifest["media"]
    assert isinstance(media, list)
    for item in media:
        assert isinstance(item, dict)
        source = Path(str(item["local_path"]))
        ledger.write_record(
            "media",
            {
                "draft_id": manifest["draft_id"],
                **item,
                "checksum": hashlib.sha256(source.read_bytes()).hexdigest(),
            },
        )


def test_quality_gate_accepts_complete_article_and_rejects_prohibited_heading(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path / "cover.webp")
    report = evaluate(manifest)
    assert report["passed"] is True
    assert report["metrics"]["characters"] >= 4500

    rejected = deepcopy(manifest)
    rejected["article"]["content"] += "\n\n## Заключение"  # type: ignore[index]
    report = evaluate(rejected)
    assert report["passed"] is False
    assert report["violations"] == ["filler_heading"]


def test_cover_and_publication_manifest_stay_inside_agent_data(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "seo-data"
    monkeypatch.setenv("VEDICWAY_SEO_DATA_DIR", str(data))
    monkeypatch.setenv("VEDICWAY_SEO_DB", str(data / "vedicway_seo_agent.sqlite3"))
    cover = data / "media" / "cover.webp"
    generated = generate_cover("Дома в натальной карте", "Основы астрологии", cover)
    assert generated["width"] == 1200
    assert generated["height"] == 630
    with Image.open(cover) as image:
        assert image.format == "WEBP"
        assert image.size == (1200, 630)

    manifest_path = data / "manifests" / "article.json"
    manifest_path.parent.mkdir(parents=True)
    manifest = _manifest(cover)
    _authorize_manifest(manifest)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    preview = publish_bundle(manifest_path, dry_run=True)
    assert preview == {
        "dry_run": True,
        "slug": "doma-v-natalnoy-karte",
        "draft_id": "draft-test-001",
        "media_count": 1,
        "target": "site+dzen-rss",
    }

    with pytest.raises(LedgerError, match="must stay inside"):
        generate_cover("Чужой файл", "Тест", tmp_path / "outside.webp")


def test_publisher_rejects_a_cover_below_the_agent_quality_threshold(
    tmp_path: Path, monkeypatch
) -> None:
    data = tmp_path / "seo-data"
    monkeypatch.setenv("VEDICWAY_SEO_DATA_DIR", str(data))
    monkeypatch.setenv("VEDICWAY_SEO_DB", str(data / "vedicway_seo_agent.sqlite3"))
    cover = data / "media" / "narrow.webp"
    cover.parent.mkdir(parents=True)
    Image.new("RGB", (800, 630), (245, 238, 225)).save(cover, "WEBP")
    manifest = _manifest(cover)
    _authorize_manifest(manifest)
    manifest_path = data / "manifests" / "narrow.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(LedgerError, match="at least 1200 pixels"):
        publish_bundle(manifest_path, dry_run=True)


def test_scheduler_reclaims_a_run_after_its_heartbeat_expires(
    tmp_path: Path, monkeypatch
) -> None:
    ledger = AgentLedger(data_dir=tmp_path)
    ledger.initialize()
    stale = ledger.start_run("article_content_production", "2026-07-21T00:00")
    with ledger.transaction(immediate=True) as connection:
        now = utc_now()
        connection.execute(
            "INSERT INTO keyword_clusters(id,slug,title,intent,status,created_at,updated_at) VALUES ('stale-owned','stale-owned','Stale owned','informational','ready',?,?)",
            (now, now),
        )
        connection.execute(
            "UPDATE cron_runs SET heartbeat_at='2000-01-01T00:00:00.000Z' WHERE id=?",
            (stale["run_id"],),
        )
    monkeypatch.setenv("VEDICWAY_SEO_RUN_ID", stale["run_id"])
    assert ledger.claim("cluster") is not None
    jobs = {"article_content_production": {"interval_minutes": 60}}

    assert due_jobs(ledger, jobs, stale_after_seconds=300) == [
        "article_content_production"
    ]
    replacement = ledger.start_run(
        "article_content_production", "2026-07-21T01:00", stale_after_seconds=300
    )
    with ledger.connect() as connection:
        old_status = connection.execute(
            "SELECT status,error_code FROM cron_runs WHERE id=?", (stale["run_id"],)
        ).fetchone()
        released = connection.execute(
            "SELECT status,claim_run_id FROM keyword_clusters WHERE id='stale-owned'"
        ).fetchone()
    assert tuple(old_status) == ("failed", "STALE_LEASE")
    assert tuple(released) == ("ready", None)
    assert replacement["run_id"] != stale["run_id"]


def test_production_scheduler_rejects_a_shared_codex_home(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("VEDICWAY_ENV", "production")
    monkeypatch.setenv("VEDICWAY_SEO_AGENT_ENABLED", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("VEDICWAY_SEO_AGENT_TOKEN", "test-internal-token")
    monkeypatch.setenv("VEDICWAY_CODEX_EXECUTABLE", sys.executable)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "shared-codex-home"))
    monkeypatch.setenv("VEDICWAY_SEO_CODEX_HOME", str(tmp_path / "seo-codex-home"))
    job = {"name": "article_site_publish"}

    assert any("dedicated VEDICWAY_SEO_CODEX_HOME" in error for error in preflight(job))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "seo-codex-home"))
    assert preflight(job) == []


def test_scheduler_injects_only_the_four_vedicway_mcp_servers(tmp_path: Path) -> None:
    servers = {}
    for override in MCP_CONFIG_OVERRIDES:
        servers.update(tomllib.loads(override)["mcp_servers"])
    assert set(servers) == {
        "vedicway-yandex-search",
        "vedicway-yandex-wordstat",
        "vedicway-yandex-webmaster",
        "vedicway-yandex-metrika",
    }
    assert all(
        server["args"][:2] == ["-m", "seo_agent.mcp_launcher"]
        for server in servers.values()
    )
    assert not any(
        variable.startswith("YANDEX_")
        for server in servers.values()
        for variable in server["env_vars"]
    )
    command = build_codex_command(
        {"model": "gpt-5.6-luna", "reasoning_effort": "medium"},
        executable="codex",
        workdir=tmp_path,
        data_dir=tmp_path / "seo-data",
    )
    assert command.count("--config") == 6
    assert all(override in command for override in MCP_CONFIG_OVERRIDES)
    assert command.index("--ignore-user-config") < command.index("--config")


def test_site_client_publishes_and_verifies_public_evidence(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "backend" / "src"))
    data = tmp_path / "seo-data"
    monkeypatch.setenv("VEDICWAY_SEO_DATA_DIR", str(data))
    monkeypatch.setenv("VEDICWAY_SEO_DB", str(data / "vedicway_seo_agent.sqlite3"))
    monkeypatch.setenv("VEDICWAY_SEO_AGENT_TOKEN", "test-token-with-more-than-thirty-two-characters")
    monkeypatch.setenv("VEDICWAY_SEO_AGENT_BASE_URL", "http://backend:8000")
    monkeypatch.setenv("VEDICWAY_PUBLIC_ORIGIN", "https://vedicway.ru")
    cover = data / "media" / "cover.webp"
    generate_cover("Дома в натальной карте", "Основы астрологии", cover)
    manifest_path = data / "manifests" / "article.json"
    manifest_path.parent.mkdir(parents=True)
    manifest = _manifest(cover)
    _authorize_manifest(manifest)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    article_url = "https://vedicway.ru/guide/doma-v-natalnoy-karte"
    asset_id = "11111111-1111-4111-8111-111111111111"
    observed_request_hash = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal observed_request_hash
        authorization = request.headers.get("authorization")
        if request.url.path.startswith("/internal/seo-agent"):
            assert authorization == "Bearer test-token-with-more-than-thirty-two-characters"
        if request.method == "GET" and request.url.path == "/internal/seo-agent/health":
            return httpx.Response(200, json={"status": "ready"})
        if request.method == "POST" and request.url.path == "/internal/seo-agent/media":
            assert len(request.headers["idempotency-key"]) >= 16
            return httpx.Response(
                201,
                json={"asset": {"id": asset_id, "url": f"/media/articles/{asset_id}/1200.webp"}},
            )
        if request.method == "GET" and request.url.path == "/api/v1/content/articles/doma-v-natalnoy-karte":
            return httpx.Response(404, json={"error": {"code": "ARTICLE_NOT_FOUND"}})
        if request.method == "PUT" and request.url.path == "/internal/seo-agent/articles/doma-v-natalnoy-karte":
            payload = json.loads(request.content)
            assert payload["cover_media_id"] == asset_id
            assert payload["cover_image_alt"] == "Схема домов в натальной карте"
            assert len(request.headers["x-content-sha256"]) == 64
            observed_request_hash = request.headers["x-content-sha256"]
            return httpx.Response(200, json={"article": payload, "idempotent_replay": False})
        if request.method == "GET" and request.url.path == "/guide/doma-v-natalnoy-karte":
            html = (
                f'<link rel="canonical" href="{article_url}">'
                f'<meta name="vedicway-article-request-sha256" content="{observed_request_hash}">'
                '<script type="application/ld+json">{"@type":"Article"}</script>'
                "Дома в натальной карте: последовательный разбор"
            )
            return httpx.Response(200, text=html)
        if request.method == "GET" and request.url.path == "/sitemap.xml":
            return httpx.Response(200, text=article_url)
        if request.method == "GET" and request.url.path == "/feed/dzen.xml":
            return httpx.Response(
                200,
                text=f"{article_url} vedicway-request-sha256:{observed_request_hash}",
            )
        if request.method == "GET" and request.url.path.endswith("/1200.webp"):
            return httpx.Response(200, content=b"webp", headers={"content-type": "image/webp"})
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    result = publish_bundle(manifest_path, transport=httpx.MockTransport(handler))
    assert result["public_url"] == article_url
    assert all(result["evidence"]["checks"].values())
    assert result["uploaded_media"] == [
        {
            "id": asset_id,
            "url": f"/media/articles/{asset_id}/1200.webp",
            "sha256": result["uploaded_media"][0]["sha256"],
        }
    ]
