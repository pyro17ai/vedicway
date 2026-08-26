from __future__ import annotations

import json
import os
import sys
import tomllib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml
from PIL import Image

import seo_agent.control as control
from seo_agent.control import dispatch
from seo_agent.db import (
    LedgerError,
    normalize_tool_provider,
    normalize_tool_response,
)
from seo_agent.cli import parser as cli_parser
from seo_agent.mcp_launcher import isolated_environment
from seo_agent.scheduler import (
    MCP_CONFIG_OVERRIDES,
    build_codex_command,
    build_prompt,
    due_jobs,
    job_environment,
    load_jobs,
    mcp_overrides_for_job,
    preflight,
)
import seo_agent.scheduler as scheduler


ROOT = Path(__file__).resolve().parents[1]


def _ready_scheduler_environment(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VEDICWAY_ENV", "production")
    monkeypatch.setenv("VEDICWAY_SEO_AGENT_ENABLED", "1")
    monkeypatch.setenv(
        "VEDICWAY_SEO_AGENT_TOKEN", "test-internal-token-with-thirty-two-characters"
    )
    monkeypatch.setenv("VEDICWAY_CODEX_EXECUTABLE", sys.executable)
    codex_home = tmp_path / "seo-codex-home"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("VEDICWAY_SEO_CODEX_HOME", str(codex_home))
    codex_home.mkdir(parents=True, exist_ok=True)
    (codex_home / "auth.json").write_text(
        json.dumps({"auth_mode": "chatgpt", "tokens": {"access_token": "test"}}),
        encoding="utf-8",
    )
    imagegen_skill = codex_home / "skills" / ".system" / "imagegen" / "SKILL.md"
    imagegen_skill.parent.mkdir(parents=True, exist_ok=True)
    imagegen_skill.write_text("---\nname: imagegen\n---\n", encoding="utf-8")


def test_each_public_platform_has_a_daily_job_and_research_can_fall_back_to_wordstat(
    monkeypatch, tmp_path: Path
) -> None:
    jobs = load_jobs(ROOT / "seo_agent" / "job_specs.json")
    daily = {
        name: job["interval_minutes"]
        for name, job in jobs.items()
        if name
        in {
            "article_intelligence_refresh",
            "article_content_production",
            "article_site_publish",
            "dzen_daily_publish",
            "vk_daily_publish",
            "pinterest_daily_publish",
        }
    }
    assert daily == {
        "article_intelligence_refresh": 1440,
        "article_content_production": 1440,
        "article_site_publish": 1440,
        "dzen_daily_publish": 1440,
        "vk_daily_publish": 1440,
        "pinterest_daily_publish": 1440,
    }
    assert "distribution-only" in jobs["article_content_production"]["prompt"]
    assert "не вставляй placeholder" in jobs["article_content_production"]["prompt"]
    assert "item: null" in jobs["article_site_publish"]["prompt"]
    assert "заверши run как skipped" in jobs["article_site_publish"]["prompt"]
    assert jobs["pinterest_daily_publish"]["daily_at_moscow"] == "12:00"
    assert "10" in jobs["article_content_production"]["prompt"]
    assert "imagegen" in jobs["article_content_production"]["skills"]
    assert "imagegen" in jobs["article_optimization"]["skills"]
    assert "$imagegen" in jobs["article_content_production"]["prompt"]
    assert "vedicway-imagegen" not in jobs["article_content_production"]["prompt"]
    assert "13:00" in jobs["pinterest_daily_publish"]["prompt"]
    assert "22:00" in jobs["pinterest_daily_publish"]["prompt"]
    intelligence_prompt = jobs["article_intelligence_refresh"]["prompt"]
    assert "одним канареечным seed" in intelligence_prompt
    assert "не вызывай Wordstat повторно" in intelligence_prompt
    assert "ровно один подтверждающий вызов" in intelligence_prompt
    assert "не создавай query, serp-snapshot и cluster" in intelligence_prompt
    assert "заверши run как blocked" in intelligence_prompt

    _ready_scheduler_environment(monkeypatch, tmp_path)
    monkeypatch.delenv("VEDICWAY_YANDEX_HOST_ID", raising=False)
    monkeypatch.delenv("VEDICWAY_METRIKA_COUNTER_ID", raising=False)
    assert preflight(jobs["article_intelligence_refresh"]) == []
    assert preflight(jobs["article_lifecycle_review"]) == [
        "VEDICWAY_YANDEX_HOST_ID is missing",
        "VEDICWAY_METRIKA_COUNTER_ID is missing",
    ]


def test_scheduler_accepts_dedicated_chatgpt_auth_without_an_api_key(
    monkeypatch, tmp_path: Path
) -> None:
    _ready_scheduler_environment(monkeypatch, tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    codex_home = tmp_path / "seo-codex-home"
    (codex_home / "auth.json").write_text(
        json.dumps({"auth_mode": "chatgpt", "tokens": {"access_token": "test"}}),
        encoding="utf-8",
    )
    jobs = load_jobs(ROOT / "seo_agent" / "job_specs.json")

    assert preflight(jobs["article_intelligence_refresh"]) == []


def test_image_jobs_require_the_builtin_imagegen_skill_instead_of_an_api_key(
    monkeypatch, tmp_path: Path
) -> None:
    _ready_scheduler_environment(monkeypatch, tmp_path)
    codex_home = tmp_path / "seo-codex-home"
    jobs = load_jobs(ROOT / "seo_agent" / "job_specs.json")

    assert preflight(jobs["article_content_production"]) == []
    assert preflight(jobs["article_optimization"]) == []

    (codex_home / "skills" / ".system" / "imagegen" / "SKILL.md").unlink()
    expected = ["Built-in Codex imagegen skill is missing"]
    assert preflight(jobs["article_content_production"]) == expected
    assert preflight(jobs["article_optimization"]) == expected


def test_seo_entrypoint_uses_chatgpt_auth_without_an_image_api_key() -> None:
    entrypoint = (ROOT / "docker" / "backend" / "entrypoint.sh").read_text(
        encoding="utf-8"
    )
    seo_profile = entrypoint.split("seo-agent)", 1)[1].split("lifecycle)", 1)[0]

    assert "install_codex_auth" in seo_profile
    assert "OPENAI_API_KEY" not in seo_profile


@pytest.mark.parametrize(
    ("kind", "source_size", "expected_size"),
    [
        ("article-cover", (1536, 1024), (1200, 630)),
        ("pinterest-card", (1024, 1536), (1000, 1500)),
    ],
)
def test_control_imports_builtin_imagegen_output_into_owned_media(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    kind: str,
    source_size: tuple[int, int],
    expected_size: tuple[int, int],
) -> None:
    codex_home = tmp_path / "codex-home"
    data_dir = tmp_path / "seo-data"
    source = codex_home / "generated_images" / "session" / f"{kind}.png"
    source.parent.mkdir(parents=True)
    Image.new("RGB", source_size, "#31204f").save(source, "PNG")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("VEDICWAY_SEO_DATA_DIR", str(data_dir))

    result = dispatch(
        "import-generated-image",
        {
            "source_path": str(source),
            "kind": kind,
            "output": f"media/test/{kind}.webp",
        },
    )

    target = data_dir / "media" / "test" / f"{kind}.webp"
    assert result == {
        "path": str(target.resolve()),
        "source_path": str(source.resolve()),
        "sha256": result["sha256"],
        "width": expected_size[0],
        "height": expected_size[1],
        "generator": "codex-imagegen",
        "kind": kind,
    }
    with Image.open(target) as image:
        assert image.format == "WEBP"
        assert image.size == expected_size


def test_control_rejects_an_image_outside_codex_generated_images(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    codex_home = tmp_path / "codex-home"
    data_dir = tmp_path / "seo-data"
    source = tmp_path / "foreign.png"
    Image.new("RGB", (1024, 1536), "#31204f").save(source, "PNG")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("VEDICWAY_SEO_DATA_DIR", str(data_dir))

    with pytest.raises(LedgerError, match="generated_images"):
        dispatch(
            "import-generated-image",
            {
                "source_path": str(source),
                "kind": "pinterest-card",
                "output": "media/test/card.webp",
            },
        )


def test_control_imports_the_latest_unconsumed_image_when_builtin_tool_omits_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    codex_home = tmp_path / "codex-home"
    data_dir = tmp_path / "seo-data"
    generated = codex_home / "generated_images" / "session"
    generated.mkdir(parents=True)
    old_source = generated / "old.png"
    new_source = generated / "new.png"
    Image.new("RGB", (1024, 1536), "#111111").save(old_source, "PNG")
    Image.new("RGB", (1024, 1536), "#31204f").save(new_source, "PNG")
    os.utime(old_source, ns=(100, 100))
    os.utime(new_source, ns=(300, 300))
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("VEDICWAY_SEO_DATA_DIR", str(data_dir))
    monkeypatch.setenv("VEDICWAY_SEO_RUN_ID", "imagegen-test-run")
    monkeypatch.setenv("VEDICWAY_IMAGEGEN_RUN_STARTED_NS", "200")

    result = dispatch(
        "import-generated-image",
        {
            "kind": "pinterest-card",
            "output": "media/test/latest.webp",
        },
    )

    assert result["source_path"] == str(new_source.resolve())
    with pytest.raises(LedgerError, match="unimported"):
        dispatch(
            "import-generated-image",
            {
                "kind": "pinterest-card",
                "output": "media/test/duplicate.webp",
            },
        )


def test_scheduler_does_not_treat_control_responses_as_external_evidence() -> None:
    prompt = build_prompt(
        {
            "name": "vk_daily_publish",
            "skills": ["vedicway-vk-publisher", "vedicway-seo-ledger"],
            "prompt": "Publish one item.",
        },
        "test-run",
    )

    assert "Ответы vedicway-control не сохраняй как tool-response" in prompt


def test_every_scheduler_prompt_ends_with_run_log_and_writing_contract(
    monkeypatch,
) -> None:
    jobs = load_jobs(ROOT / "seo_agent" / "job_specs.json")
    monkeypatch.setenv("VEDICWAY_PINTEREST_BOARD_NAME", "Ведическая астрология")
    monkeypatch.setenv("VEDICWAY_YANDEX_HOST_ID", "https:vedicway.ru:443")
    monkeypatch.setenv("VEDICWAY_METRIKA_COUNTER_ID", "111176610")

    for job in jobs.values():
        prompt = build_prompt(job, "run-log-contract")
        assert "вызови vedicway_record_run_log ровно один раз" in prompt.casefold()
        assert "поле log_text" in prompt
        assert "<!-- writing & answering format -->" in prompt
        assert "Отвечай мне всегда естественным публицистическим русским языком" in prompt
        assert "Не пиши заключительный абзац" in prompt
        assert prompt.rstrip().endswith("<!-- writing & answering format -->")


def test_scheduler_gives_yandex_jobs_the_exact_non_secret_owner_ids(
    monkeypatch,
) -> None:
    monkeypatch.setenv("VEDICWAY_YANDEX_HOST_ID", "https:vedicway.ru:443")
    monkeypatch.setenv("VEDICWAY_METRIKA_COUNTER_ID", "111176610")

    prompt = build_prompt(
        {
            "name": "article_intelligence_refresh",
            "skills": ["vedicway-yandex-signals", "vedicway-seo-ledger"],
            "prompt": "Refresh signals.",
        },
        "test-run",
    )

    assert "Разрешённый Webmaster host_id: https:vedicway.ru:443" in prompt
    assert "разрешённый Metrika counter_id: 111176610" in prompt
    assert "не вызывай ledger_claim" in prompt


def test_backend_image_applies_the_pinned_metrika_response_patch() -> None:
    dockerfile = (ROOT / "docker" / "backend" / "Dockerfile").read_text(
        encoding="utf-8"
    )

    assert "patch-yandex-metrika.mjs" in dockerfile
    assert "node /opt/vedicway/seo_agent/mcp/patch-yandex-metrika.mjs" in dockerfile


@pytest.mark.parametrize(
    ("provided", "expected"),
    [
        ("yandex_search", "yandex-search"),
        ("yandex_wordstat", "wordstat"),
        ("yandex-webmaster", "webmaster"),
        ("yandex_metrika", "metrika"),
        ("vk", "vk"),
    ],
)
def test_tool_response_provider_aliases_are_normalized(
    provided: str, expected: str
) -> None:
    assert normalize_tool_provider(provided) == expected


def test_control_rejects_internal_mcp_as_an_external_tool_response() -> None:
    with pytest.raises(LedgerError, match="Unsupported tool-response provider"):
        normalize_tool_provider("vedicway-control")


def test_plain_text_mcp_response_is_preserved_as_json() -> None:
    assert normalize_tool_response("Permission denied") == {
        "text": "Permission denied"
    }


def test_control_reads_due_lifecycle_through_a_narrow_action(monkeypatch) -> None:
    class StubLedger:
        def due_lifecycle(self, *, limit: int):
            return [{"id": "publication-1", "limit": limit}]

    monkeypatch.setattr(control, "AgentLedger", StubLedger)

    assert dispatch("ledger-due-lifecycle", {"limit": 7}) == {
        "items": [{"id": "publication-1", "limit": 7}]
    }


def test_seo_agent_mounts_its_dedicated_codex_auth() -> None:
    compose = yaml.safe_load((ROOT / "compose.production.yml").read_text(encoding="utf-8"))
    seo_agent = compose["services"]["seo-agent"]

    assert seo_agent["environment"]["CODEX_AUTH_FILE"] == "/run/secrets/codex_auth"
    assert (
        seo_agent["environment"]["VEDICWAY_CODEX_HOME"]
        == "/var/lib/vedicway/seo-codex-home"
    )
    assert "codex_auth" in seo_agent["secrets"]
    assert "codex_api_key" not in seo_agent["secrets"]
    assert "OPENAI_API_KEY_FILE" not in seo_agent["environment"]

    worker = compose["services"]["worker"]
    assert "codex_auth" in worker["secrets"]
    assert "codex_api_key" not in worker["secrets"]
    assert "OPENAI_API_KEY_FILE" not in worker["environment"]


def test_seo_agent_healthcheck_bootstraps_its_own_database_url() -> None:
    compose = yaml.safe_load((ROOT / "compose.production.yml").read_text(encoding="utf-8"))
    healthcheck = " ".join(compose["services"]["seo-agent"]["healthcheck"]["test"])

    assert "POSTGRES_PASSWORD_FILE" in healthcheck
    assert "seo_agent.cli health" in healthcheck


def test_moscow_daily_schedule_runs_once_after_noon() -> None:
    schedule_due = getattr(scheduler, "daily_schedule_due", None)
    assert callable(schedule_due), "scheduler must support a Moscow wall-clock schedule"
    moscow = ZoneInfo("Europe/Moscow")
    assert schedule_due(None, "12:00", datetime(2026, 8, 19, 11, 59, tzinfo=moscow)) is False
    assert schedule_due(None, "12:00", datetime(2026, 8, 19, 12, 0, tzinfo=moscow)) is True
    assert schedule_due(None, "12:00", datetime(2026, 8, 19, 13, 0, tzinfo=moscow)) is False
    assert schedule_due(
        "2026-08-19T09:01:00.000Z",
        "12:00",
        datetime(2026, 8, 19, 20, 0, tzinfo=moscow),
    ) is False
    assert schedule_due(
        "2026-08-18T09:01:00.000Z",
        "12:00",
        datetime(2026, 8, 19, 12, 0, tzinfo=moscow),
    ) is True


def test_scheduler_rechecks_an_orphaned_run_after_five_minutes() -> None:
    heartbeat = (datetime.now(UTC) - timedelta(seconds=301)).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")

    class Cursor:
        def fetchone(self):
            return {
                "status": "running",
                "started_at": heartbeat,
                "heartbeat_at": heartbeat,
                "finished_at": None,
            }

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, query, parameters):
            return Cursor()

    class Ledger:
        def connect(self):
            return Connection()

    assert due_jobs(
        Ledger(),
        {"article_intelligence_refresh": {"interval_minutes": 1440}},
    ) == ["article_intelligence_refresh"]


def test_pinterest_migration_allows_ten_media_assets_per_draft() -> None:
    migration = ROOT / "seo_agent" / "migrations" / "005_pinterest_daily_batch.sql"
    assert migration.is_file()
    sql = migration.read_text(encoding="utf-8")
    assert "DROP INDEX IF EXISTS one_distribution_media_role_per_draft" in sql


def test_scheduler_injects_vk_and_isolated_browser_publishers() -> None:
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
        server["default_tools_approval_mode"] == "approve"
        for server in servers.values()
    )

    with pytest.raises(Exception, match="VEDICWAY_VK_USER_ACCESS_TOKEN"):
        isolated_environment(
            "vk",
            {
                "VEDICWAY_VK_GROUP_ID": "222",
                "VEDICWAY_VK_GROUP_ACCESS_TOKEN": "vedicway-token",
            },
        )

    vk = isolated_environment(
        "vk",
        {
            "PATH": "runtime",
            "VK_GROUP_ID": "111",
            "VK_GROUP_ACCESS_TOKEN": "foreign-token",
            "VK_USER_ACCESS_TOKEN": "foreign-user-token",
            "VEDICWAY_VK_GROUP_ID": "222",
            "VEDICWAY_VK_GROUP_ACCESS_TOKEN": "vedicway-token",
            "VEDICWAY_VK_USER_ACCESS_TOKEN": "vedicway-user-token",
        },
    )
    assert vk == {
        "PATH": "runtime",
        "VK_GROUP_ID": "222",
        "VK_GROUP_ACCESS_TOKEN": "vedicway-token",
        "VK_USER_ACCESS_TOKEN": "vedicway-user-token",
    }

    with pytest.raises(Exception, match="Unsupported VedicWay MCP target"):
        isolated_environment("pinterest", {"PINTEREST_ACCESS_TOKEN": "foreign"})
    with pytest.raises(Exception, match="Unsupported VedicWay MCP target"):
        isolated_environment("imagegen", {"OPENAI_API_KEY": "foreign"})


def test_scheduler_exposes_mcp_only_to_the_jobs_that_need_each_server(tmp_path: Path) -> None:
    content = mcp_overrides_for_job("article_content_production")
    assert len(content) == 1
    assert any("vedicway-control" in value for value in content)
    assert len(mcp_overrides_for_job("article_site_publish")) == 1
    assert len(mcp_overrides_for_job("dzen_daily_publish")) == 2
    assert {"vedicway-control", "vedicway-vk"} == {
        name
        for value in mcp_overrides_for_job("vk_daily_publish")
        for name in ("vedicway-control", "vedicway-vk")
        if name in value
    }
    assert {"vedicway-control", "vedicway-pinterest-browser"} == {
        name
        for value in mcp_overrides_for_job("pinterest_daily_publish")
        for name in ("vedicway-control", "vedicway-pinterest-browser")
        if name in value
    }
    intelligence = mcp_overrides_for_job("article_intelligence_refresh")
    assert len(intelligence) == 5
    assert not any("vedicway-vk" in value or "vedicway-pinterest" in value for value in intelligence)

    command = build_codex_command(
        {
            "name": "vk_daily_publish",
            "model": "gpt-5.6-luna",
            "reasoning_effort": "medium",
        },
        executable="codex",
        workdir=tmp_path,
        data_dir=tmp_path / "seo-data",
    )
    assert "read-only" in command
    assert "features.use_legacy_landlock=true" in command
    assert "sandbox_workspace_write.network_access=true" not in command
    assert "--add-dir" not in command
    assert sum("mcp_servers." in value for value in command) == 2
    assert any("mcp_servers.vedicway-vk" in value for value in command)
    assert any("mcp_servers.vedicway-control" in value for value in command)

    base = {
        "PATH": "/runtime",
        "OPENAI_API_KEY": "must-not-reach-codex-or-mcp",
        "VEDICWAY_VK_GROUP_ACCESS_TOKEN": "vk-group",
        "VEDICWAY_VK_USER_ACCESS_TOKEN": "vk-user",
        "VEDICWAY_YANDEX_SEARCH_API_KEY": "yandex",
    }
    assert job_environment({"name": "vk_daily_publish"}, base) == {
        "PATH": "/runtime",
        "VEDICWAY_VK_GROUP_ACCESS_TOKEN": "vk-group",
        "VEDICWAY_VK_USER_ACCESS_TOKEN": "vk-user",
        "VEDICWAY_SEO_JOB_NAME": "vk_daily_publish",
    }
    content_environment = job_environment({"name": "article_content_production"}, base)
    assert content_environment["VEDICWAY_IMAGEGEN_RUN_STARTED_NS"].isdigit()
    assert "OPENAI_API_KEY" not in content_environment
def test_job_specs_are_valid_json_with_no_legacy_platforms() -> None:
    payload = json.loads(
        (ROOT / "seo_agent" / "job_specs.json").read_text(encoding="utf-8")
    )
    serialized = json.dumps(payload, ensure_ascii=False).casefold()
    assert all(
        retired not in serialized
        for retired in ("joomla", "virtuemart", "telegram", "tenchat", "max-social")
    )


def test_ledger_cli_accepts_distribution_claims_and_records() -> None:
    commands = cli_parser()
    assert commands.parse_args(["claim", "vk-post"]).entity == "vk-post"
    assert (
        commands.parse_args(["claim", "pinterest-pin"]).entity
        == "pinterest-pin"
    )
    assert commands.parse_args(["claim", "dzen-article"]).entity == "dzen-article"
    assert (
        commands.parse_args(
            ["write", "distribution-item", "--json-file", "distribution.json"]
        ).record_type
        == "distribution-item"
    )
