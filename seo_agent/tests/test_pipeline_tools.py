from __future__ import annotations

import hashlib
import json
import sys
import tomllib
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from PIL import Image

from seo_agent.browser_mcp_launcher import build_browser_mcp_command
from seo_agent.db import AgentLedger, LedgerError, canonical_json, utc_now
from seo_agent.quality_gate import evaluate
from seo_agent.scheduler import (
    MCP_CONFIG_OVERRIDES,
    bootstrap_seed_data_enabled,
    build_codex_command,
    build_prompt,
    due_jobs,
    job_environment,
    load_jobs,
    mcp_overrides_for_job,
    preflight,
)
from seo_agent.site_client import _manifest_from_active_run_claim, publish_bundle
from seo_agent.tests.media_fixture import generate_cover


def _write_cover(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1200, 630), (55, 32, 79)).save(path, "WEBP")


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
            "Рассчитайте исходные положения на [главной странице](/), затем вернитесь к схеме разбора.",
            "Смежные определения собраны в [гиде по астрологии](/guide).",
            "Методические основания сверяйте с [документацией Swiss Ephemeris](https://www.astro.com/swisseph/) и "
            "[описанием часовых поясов IANA](https://www.iana.org/time-zones).",
        ]
    )
    return "\n\n".join(paragraphs)


def _manifest(cover: Path) -> dict[str, object]:
    content = _content()
    return {
        "schema_version": "2.0",
        "draft_id": "draft-test-001",
        "claim_token": "claimed-draft-token-with-enough-length",
        "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "article": {
            "section": "blog",
            "difficulty": "beginner",
            "title": "Дома в натальной карте: последовательный разбор",
            "slug": "doma-v-natalnoy-karte",
            "category": "Основы астрологии",
            "excerpt": "Практический порядок чтения домов натальной карты с проверкой знака, управителя и аспектов.",
            "content_markdown": content,
            "cover_image_alt": "Схема домов в натальной карте",
            "seo_title": "Дома в натальной карте: как читать",
            "meta_description": "Разбираем дома в натальной карте по шагам: знак на куспиде, управитель, планеты и аспекты без оторванных трактовок.",
            "focus_keyphrase": "дома в натальной карте",
            "tags": ["дома", "натальная карта"],
            "schema_extra": {"learningResourceType": "Практическое руководство"},
            "author_name": "Редакция VedicWay",
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
            "INSERT INTO keyword_clusters(id,slug,title,intent,status,created_at,updated_at) VALUES ('cluster-test','cluster-test','Cluster','informational','briefed',%s,%s)",
            (now, now),
        )
        connection.execute(
            "INSERT INTO content_briefs(id,cluster_id,status,title,primary_query,audience_problem,search_intent,outline_json,evidence_json,internal_links_json,prohibited_claims_json,checksum,created_at) VALUES ('brief-test','cluster-test','consumed','Brief','query','problem','informational','[]','[]','[]','[]','brief-hash',%s)",
            (now,),
        )
        connection.execute(
            """INSERT INTO article_drafts(
            id,brief_id,slug,status,title,excerpt,content_markdown,seo_title,meta_description,
            focus_keyphrase,category,author_name,content_hash,quality_report_json,claim_token,
            claim_expires_at,created_at,updated_at,approved_at
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                manifest["draft_id"],
                "brief-test",
                article["slug"],
                "publishing",
                article["title"],
                article["excerpt"],
                article["content_markdown"],
                article["seo_title"],
                article["meta_description"],
                article["focus_keyphrase"],
                article["category"],
                article["author_name"],
                manifest["content_hash"],
                canonical_json(
                    {"passed": True, "content_hash": manifest["content_hash"]}
                ),
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


def test_quality_gate_accepts_complete_article_and_rejects_prohibited_heading(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path / "cover.webp")
    report = evaluate(manifest)
    assert report["passed"] is True
    assert report["metrics"]["characters"] >= 4500

    inflected = deepcopy(manifest)
    inflected["article"]["focus_keyphrase"] = "натальная карта"  # type: ignore[index]
    assert evaluate(inflected)["passed"] is True

    rejected = deepcopy(manifest)
    rejected["article"]["content_markdown"] += "\n\n## Заключение"  # type: ignore[index]
    report = evaluate(rejected)
    assert report["passed"] is False
    assert report["violations"] == ["filler_heading"]


def test_cover_and_publication_manifest_stay_inside_agent_data(
    tmp_path: Path, monkeypatch
) -> None:
    data = tmp_path / "seo-data"
    monkeypatch.setenv("VEDICWAY_SEO_DATA_DIR", str(data))
    monkeypatch.setenv("VEDICWAY_SEO_DATA_DIR", str(data))
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
    manifest["media"] = [{"media_role": "cover"}]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    preview = publish_bundle(manifest_path, dry_run=True)
    assert preview == {
        "dry_run": True,
        "slug": "doma-v-natalnoy-karte",
        "draft_id": "draft-test-001",
        "media_count": 1,
        "target": "site",
    }

    with pytest.raises(LedgerError, match="must stay inside"):
        generate_cover("Чужой файл", "Тест", tmp_path / "outside.webp")


def test_publisher_rejects_a_cover_below_the_agent_quality_threshold(
    tmp_path: Path, monkeypatch
) -> None:
    data = tmp_path / "seo-data"
    monkeypatch.setenv("VEDICWAY_SEO_DATA_DIR", str(data))
    monkeypatch.setenv("VEDICWAY_SEO_DATA_DIR", str(data))
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
            "INSERT INTO keyword_clusters(id,slug,title,intent,status,created_at,updated_at) VALUES ('stale-owned','stale-owned','Stale owned','informational','ready',%s,%s)",
            (now, now),
        )
        expired_heartbeat = (datetime.now(UTC) - timedelta(seconds=301)).isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z")
        connection.execute(
            "UPDATE cron_runs SET heartbeat_at=%s WHERE id=%s",
            (expired_heartbeat, stale["run_id"]),
        )


    monkeypatch.setenv("VEDICWAY_SEO_RUN_ID", stale["run_id"])
    assert ledger.claim("cluster") is not None
    jobs = {"article_content_production": {"interval_minutes": 60}}

    assert due_jobs(ledger, jobs) == [
        "article_content_production"
    ]
    replacement = ledger.start_run(
        "article_content_production", "2026-07-21T01:00", stale_after_seconds=300
    )
    with ledger.connect() as connection:
        old_status = connection.execute(
            "SELECT status,error_code FROM cron_runs WHERE id=%s", (stale["run_id"],)
        ).fetchone()
        released = connection.execute(
            "SELECT status,claim_run_id FROM keyword_clusters WHERE id='stale-owned'"
        ).fetchone()
    assert (old_status["status"], old_status["error_code"]) == ("failed", "STALE_LEASE")
    assert (released["status"], released["claim_run_id"]) == ("ready", None)
    assert replacement["run_id"] != stale["run_id"]


def test_site_manifest_uses_the_active_run_claim_as_canonical_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "seo-data"
    monkeypatch.setenv("VEDICWAY_SEO_DATA_DIR", str(data))
    cover = data / "media" / "cover.webp"
    generate_cover("Дома в натальной карте", "Основы астрологии", cover)
    manifest = _manifest(cover)
    _authorize_manifest(manifest)
    ledger = AgentLedger()
    run = ledger.start_run("article_site_publish", "canonical-manifest-test")
    monkeypatch.setenv("VEDICWAY_SEO_RUN_ID", run["run_id"])
    with ledger.transaction(immediate=True) as connection:
        connection.execute(
            "UPDATE article_drafts SET claim_run_id=%s WHERE id=%s",
            (run["run_id"], manifest["draft_id"]),
        )

    untrusted = deepcopy(manifest)
    untrusted["draft_id"] = "wrong-draft"
    untrusted["claim_token"] = "wrong-claim-token-that-is-long-enough"
    untrusted["content_hash"] = "0" * 64
    untrusted["article"]["title"] = "Подменённый заголовок"  # type: ignore[index]

    canonical = _manifest_from_active_run_claim(ledger, untrusted)

    assert canonical["draft_id"] == manifest["draft_id"]
    assert canonical["claim_token"] == manifest["claim_token"]
    assert canonical["content_hash"] == manifest["content_hash"]
    assert canonical["article"]["title"] == manifest["article"]["title"]  # type: ignore[index]


def test_production_scheduler_rejects_a_shared_codex_home(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("VEDICWAY_ENV", "production")
    monkeypatch.setenv("VEDICWAY_SEO_AGENT_ENABLED", "1")
    monkeypatch.setenv("VEDICWAY_SEO_AGENT_TOKEN", "test-internal-token")
    monkeypatch.setenv("VEDICWAY_CODEX_EXECUTABLE", sys.executable)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "shared-codex-home"))
    monkeypatch.setenv("VEDICWAY_SEO_CODEX_HOME", str(tmp_path / "seo-codex-home"))
    job = {"name": "article_site_publish"}

    assert any("dedicated VEDICWAY_SEO_CODEX_HOME" in error for error in preflight(job))
    codex_home = tmp_path / "seo-codex-home"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    assert preflight(job) == []


def test_scheduler_injects_browser_publishers_only_into_their_jobs(tmp_path: Path) -> None:
    servers = {}
    for override in MCP_CONFIG_OVERRIDES:
        servers.update(tomllib.loads(override)["mcp_servers"])
    assert set(servers) == {
        "vedicway-yandex-search",
        "vedicway-yandex-wordstat",
        "vedicway-yandex-webmaster",
        "vedicway-yandex-metrika",
        "vedicway-vk",
        "vedicway-dzen-browser",
        "vedicway-pinterest-browser",
        "vedicway-control",
    }
    assert all(
        server["args"][:2]
        in (["-m", "seo_agent.mcp_launcher"], ["-m", "seo_agent.browser_mcp_launcher"])
        for server in servers.values()
    )
    assert not any(
        variable.startswith(("YANDEX_", "VK_", "PINTEREST_"))
        for server in servers.values()
        for variable in server["env_vars"]
    )
    assert "PYTHONPATH" in servers["vedicway-control"]["env_vars"]
    command = build_codex_command(
        {
            "name": "article_intelligence_refresh",
            "model": "gpt-5.6-luna",
            "reasoning_effort": "medium",
        },
        executable="codex",
        workdir=tmp_path,
        data_dir=tmp_path / "seo-data",
    )
    assert command.count("--config") == 7
    assert all(
        override in command
        for override in mcp_overrides_for_job("article_intelligence_refresh")
    )
    assert "read-only" in command
    assert command[command.index("--disable") + 1] == "shell_tool"
    assert "sandbox_workspace_write.network_access=true" not in command
    assert "--add-dir" not in command
    assert "features.use_legacy_landlock=true" not in command
    assert any("mcp_servers.vedicway-control=" in value for value in command)
    assert command.index("--ignore-user-config") < command.index("--config")

    dzen = mcp_overrides_for_job("dzen_daily_publish")
    pinterest = mcp_overrides_for_job("pinterest_daily_publish")
    assert len(dzen) == 2
    assert any("browser_mcp_launcher\", \"dzen" in value for value in dzen)
    assert len(pinterest) == 2
    assert any("browser_mcp_launcher\", \"pinterest" in value for value in pinterest)
    assert all("VEDICWAY_PINTEREST_ACCESS_TOKEN" not in value for value in pinterest)


def test_scheduler_uses_terra_with_high_reasoning_only_for_publishers(
    tmp_path: Path,
) -> None:
    jobs = load_jobs(Path(__file__).resolve().parents[1] / "job_specs.json")
    high_jobs = {
        "article_site_publish",
        "dzen_daily_publish",
        "vk_daily_publish",
        "pinterest_daily_publish",
        "article_optimization",
    }
    assert {job["model"] for job in jobs.values()} == {"gpt-5.6-terra"}
    assert {
        name for name, job in jobs.items() if job["reasoning_effort"] == "high"
    } == high_jobs
    assert all(
        job["reasoning_effort"] == "medium"
        for name, job in jobs.items()
        if name not in high_jobs
    )
    environment = job_environment(
        jobs["article_site_publish"], {"PATH": str(tmp_path)}
    )
    assert environment["VEDICWAY_SEO_JOB_NAME"] == "article_site_publish"


def test_browser_mcp_launcher_uses_cdp_and_owned_workspace(tmp_path: Path) -> None:
    command, cwd = build_browser_mcp_command(
        "pinterest",
        data_dir=tmp_path,
        node="node",
        cli=tmp_path / "node_modules" / "@playwright" / "mcp" / "cli.js",
        endpoint="http://vedicway-seo-browser-pinterest:9325",
    )
    assert cwd == tmp_path / "browser-input" / "pinterest"
    assert command[:2] == ["node", str(tmp_path / "node_modules" / "@playwright" / "mcp" / "cli.js")]
    assert "--cdp-endpoint" in command
    assert "http://vedicway-seo-browser-pinterest:9325" in command
    assert "--allow-unrestricted-file-access" not in command
    assert command[command.index("--output-dir") + 1] == str(tmp_path / "browser-output" / "pinterest")
    assert "https://pinterest-anaheim.s3.amazonaws.com" in command[
        command.index("--allowed-origins") + 1
    ]

    dzen_command, _ = build_browser_mcp_command(
        "dzen",
        data_dir=tmp_path,
        node="node",
        cli=tmp_path / "node_modules" / "@playwright" / "mcp" / "cli.js",
        endpoint="http://vedicway-seo-browser-dzen:9322",
    )
    assert "https://*.dzeninfra.ru" in dzen_command[
        dzen_command.index("--allowed-origins") + 1
    ]


def test_scheduler_does_not_treat_playwright_actions_as_raw_tool_responses() -> None:
    prompt = build_prompt(
        {
            "name": "dzen_daily_publish",
            "skills": ["vedicway-dzen-distributor", "vedicway-seo-ledger"],
            "prompt": "Опубликуй статью.",
        },
        "run-id",
    )
    assert "Действия Playwright MCP и browser snapshot как tool-response не записывай" in prompt
    assert "Любой внешний ответ сначала сохрани как raw_tool_response" not in prompt


def test_site_client_publishes_and_verifies_public_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.syspath_prepend(
        str(Path(__file__).resolve().parents[2] / "backend" / "src")
    )
    data = tmp_path / "seo-data"
    monkeypatch.setenv("VEDICWAY_SEO_DATA_DIR", str(data))
    monkeypatch.setenv("VEDICWAY_SEO_DATA_DIR", str(data))
    monkeypatch.setenv(
        "VEDICWAY_SEO_AGENT_TOKEN", "test-token-with-more-than-thirty-two-characters"
    )
    monkeypatch.setenv("VEDICWAY_SEO_AGENT_BASE_URL", "http://backend:8000")
    monkeypatch.setenv("VEDICWAY_PUBLIC_ORIGIN", "https://vedicway.ru")
    cover = data / "media" / "cover.webp"
    generate_cover("Дома в натальной карте", "Основы астрологии", cover)
    body = data / "media" / "body.webp"
    Image.new("RGB", (1000, 1500), (239, 225, 204)).save(body, "WEBP")
    manifest_path = data / "manifests" / "article.json"
    manifest_path.parent.mkdir(parents=True)
    manifest = _manifest(cover)
    article = manifest["article"]
    assert isinstance(article, dict)
    media = manifest["media"]
    assert isinstance(media, list)
    media.append(
        {
            "purpose": "body",
            "distribution_role": "pinterest",
            "local_path": str(body),
            "alt_text": "Схема последовательного чтения домов",
            "source_kind": "generated",
            "license_note": "Generated locally for VedicWay",
        }
    )
    _authorize_manifest(manifest)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    article_url = "https://vedicway.ru/blog/doma-v-natalnoy-karte"
    cover_asset_id = "11111111-1111-4111-8111-111111111111"
    body_asset_id = "22222222-2222-4222-8222-222222222222"
    uploaded_asset_ids = iter((cover_asset_id, body_asset_id))
    observed_request_hash = ""
    uploaded_media_requests = 0
    verified_media_ids: set[str] = set()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal observed_request_hash, uploaded_media_requests
        authorization = request.headers.get("authorization")
        if request.url.path.startswith("/internal/content-agent"):
            assert (
                authorization
                == "Bearer test-token-with-more-than-thirty-two-characters"
            )
        if (
            request.method == "GET"
            and request.url.path == "/internal/content-agent/health"
        ):
            return httpx.Response(
                200,
                json={
                    "status": "ready",
                    "capabilities": {"public_unlisted_media": True},
                },
            )
        if (
            request.method == "POST"
            and request.url.path == "/internal/content-agent/media"
        ):
            assert len(request.headers["idempotency-key"]) >= 16
            asset_id = next(uploaded_asset_ids)
            uploaded_media_requests += 1
            if uploaded_media_requests == 1:
                assert b'name="public_unlisted"\r\n\r\nfalse' in request.content
            else:
                assert b'name="public_unlisted"\r\n\r\ntrue' in request.content
            return httpx.Response(
                201,
                json={
                    "asset": {
                        "id": asset_id,
                        "url": f"/media/articles/{asset_id}/1200.webp",
                    }
                },
            )
        if (
            request.method == "GET"
            and request.url.path
            == "/api/v1/content/blog/articles/doma-v-natalnoy-karte"
        ):
            return httpx.Response(404, json={"error": {"code": "ARTICLE_NOT_FOUND"}})
        if (
            request.method == "PUT"
            and request.url.path
            == "/internal/content-agent/blog/articles/doma-v-natalnoy-karte"
        ):
            payload = json.loads(request.content)
            assert payload["cover_media_id"] == cover_asset_id
            assert payload["cover_image_alt"] == "Схема домов в натальной карте"
            assert body_asset_id not in payload["content_html"]
            assert "<h2>Шаг 1: проверка показателей</h2>" in payload["content_html"]
            assert "## Шаг 1" not in payload["content_html"]
            assert len(request.headers["x-content-sha256"]) == 64
            observed_request_hash = request.headers["x-content-sha256"]
            return httpx.Response(
                200, json={"article": payload, "idempotent_replay": False}
            )
        if (
            request.method == "GET"
            and request.url.path == "/blog/doma-v-natalnoy-karte"
        ):
            html = (
                f'<link rel="canonical" href="{article_url}">'
                '<script type="application/ld+json">{"@type":"BlogPosting"}</script>'
                "Дома в натальной карте: последовательный разбор"
            )
            return httpx.Response(200, text=html)
        if request.method == "GET" and request.url.path == "/sitemap.xml":
            return httpx.Response(200, text=article_url)
        if request.method == "GET" and request.url.path == "/feed/dzen.xml":
            return httpx.Response(
                200,
                text=article_url,
            )
        if request.method == "GET" and request.url.path.endswith("/1200.webp"):
            verified_media_ids.add(request.url.path.split("/")[3])
            return httpx.Response(
                200, content=b"webp", headers={"content-type": "image/webp"}
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    result = publish_bundle(manifest_path, transport=httpx.MockTransport(handler))
    assert result["public_url"] == article_url
    assert all(result["evidence"]["checks"].values())
    assert verified_media_ids == {cover_asset_id, body_asset_id}
    assert result["uploaded_media"] == [
        {
            "media_id": result["uploaded_media"][0]["media_id"],
            "backend_media_id": cover_asset_id,
            "public_url": f"https://vedicway.ru/media/articles/{cover_asset_id}/1200.webp",
            "purpose": "cover",
            "distribution_role": None,
            "width": 1200,
            "height": 630,
            "sha256": result["uploaded_media"][0]["sha256"],
        },
        {
            "media_id": result["uploaded_media"][1]["media_id"],
            "backend_media_id": body_asset_id,
            "public_url": f"https://vedicway.ru/media/articles/{body_asset_id}/1200.webp",
            "purpose": "body",
            "distribution_role": "pinterest",
            "width": 1000,
            "height": 1500,
            "sha256": result["uploaded_media"][1]["sha256"],
        },
    ]
    assert result["uploaded_media"][0]["media_id"] != cover_asset_id
    assert result["uploaded_media"][1]["media_id"] != body_asset_id
    with AgentLedger().connect() as connection:
        distribution_media = connection.execute(
            "SELECT distribution_role,backend_media_id,public_url FROM article_media WHERE draft_id=%s AND purpose='body'",
            (manifest["draft_id"],),
        ).fetchone()
    assert distribution_media == {
        "distribution_role": "pinterest",
        "backend_media_id": body_asset_id,
        "public_url": f"https://vedicway.ru/media/articles/{body_asset_id}/1200.webp",
    }


def test_site_client_rejects_backend_without_public_unlisted_capability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.syspath_prepend(
        str(Path(__file__).resolve().parents[2] / "backend" / "src")
    )
    data = tmp_path / "seo-data"
    monkeypatch.setenv("VEDICWAY_SEO_DATA_DIR", str(data))
    monkeypatch.setenv(
        "VEDICWAY_SEO_AGENT_TOKEN", "test-token-with-more-than-thirty-two-characters"
    )
    monkeypatch.setenv("VEDICWAY_SEO_AGENT_BASE_URL", "http://backend:8000")
    monkeypatch.setenv("VEDICWAY_PUBLIC_ORIGIN", "https://vedicway.ru")
    cover = data / "media" / "cover.webp"
    generate_cover("Дома в натальной карте", "Основы астрологии", cover)
    card = data / "media" / "card.webp"
    Image.new("RGB", (1000, 1500), (239, 225, 204)).save(card, "WEBP")
    manifest = _manifest(cover)
    assert isinstance(manifest["media"], list)
    manifest["media"].append(
        {
            "purpose": "body",
            "distribution_role": "pinterest",
            "local_path": str(card),
            "alt_text": "Памятка по чтению домов",
            "source_kind": "generated",
            "license_note": "Generated locally for VedicWay",
        }
    )
    _authorize_manifest(manifest)
    manifest_path = data / "manifests" / "legacy-backend.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/internal/content-agent/health":
            return httpx.Response(200, json={"status": "ready"})
        raise AssertionError("Media upload must not start against a legacy backend")

    with pytest.raises(LedgerError, match="public-unlisted"):
        publish_bundle(manifest_path, transport=httpx.MockTransport(handler))


def test_site_client_rejects_guide_manifests_before_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.syspath_prepend(
        str(Path(__file__).resolve().parents[2] / "backend" / "src")
    )
    data = tmp_path / "seo-data"
    monkeypatch.setenv("VEDICWAY_SEO_DATA_DIR", str(data))
    cover = data / "media" / "cover.webp"
    generate_cover("Дома в натальной карте", "Основы астрологии", cover)
    manifest = _manifest(cover)
    article = manifest["article"]
    assert isinstance(article, dict)
    article["section"] = "guide"
    manifest_path = data / "manifests" / "guide.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(LedgerError, match="blog"):
        publish_bundle(manifest_path)
def test_scheduler_starts_with_an_empty_ledger_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VEDICWAY_SEO_BOOTSTRAP_SEEDS", raising=False)
    assert bootstrap_seed_data_enabled() is False


def test_scheduler_requires_an_explicit_flag_for_seed_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VEDICWAY_SEO_BOOTSTRAP_SEEDS", "1")
    assert bootstrap_seed_data_enabled() is True
