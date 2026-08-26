from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

from check_production_release import parse_env, resolve_input

SECRET_PATHS = {
    "VEDICWAY_SEO_AGENT_TOKEN_FILE": 32,
    "VEDICWAY_YANDEX_SEARCH_API_KEY_FILE": 16,
    "VEDICWAY_YANDEX_FOLDER_ID_FILE": 1,
    "VEDICWAY_YANDEX_WEBMASTER_TOKEN_FILE": 16,
    "VEDICWAY_YANDEX_METRIKA_TOKEN_FILE": 16,
    "VEDICWAY_VK_GROUP_ACCESS_TOKEN_FILE": 16,
    "VEDICWAY_VK_USER_ACCESS_TOKEN_FILE": 16,
}

EXPECTED_MCP = {
    "vedicway-yandex-search",
    "vedicway-yandex-wordstat",
    "vedicway-yandex-webmaster",
    "vedicway-yandex-metrika",
    "vedicway-vk",
    "vedicway-dzen-browser",
    "vedicway-pinterest-browser",
    "vedicway-control",
}

EXPECTED_MCP_LAUNCHERS = {
    "search": ["VEDICWAY_YANDEX_SEARCH_API_KEY", "VEDICWAY_YANDEX_FOLDER_ID"],
    "wordstat": ["VEDICWAY_YANDEX_SEARCH_API_KEY", "VEDICWAY_YANDEX_FOLDER_ID"],
    "webmaster": ["VEDICWAY_YANDEX_WEBMASTER_TOKEN"],
    "metrika": ["VEDICWAY_YANDEX_METRIKA_TOKEN"],
    "vk": ["VEDICWAY_VK_GROUP_ID", "VEDICWAY_VK_GROUP_ACCESS_TOKEN", "VEDICWAY_VK_USER_ACCESS_TOKEN"],
    "control": [
        "PYTHONPATH", "VEDICWAY_SEO_DATABASE_URL", "DATABASE_URL", "VEDICWAY_DATABASE_URL",
        "VEDICWAY_SEO_DATA_DIR", "VEDICWAY_SEO_RUN_ID", "VEDICWAY_SEO_JOB_NAME",
        "VEDICWAY_SEO_AGENT_TOKEN",
        "VEDICWAY_SEO_AGENT_BASE_URL", "VEDICWAY_PUBLIC_ORIGIN",
        "VEDICWAY_SEO_JOB_TIMEOUT_SECONDS", "VEDICWAY_IMAGEGEN_RUN_STARTED_NS",
        "VEDICWAY_PINTEREST_BOARD_NAME",
        "CODEX_HOME",
    ],
}

EXPECTED_PACKAGES = {
    "@modelcontextprotocol/sdk": "1.29.0",
    "yandex-search-mcp": "1.3.0",
    "yandex-wordstat-mcp": "2.0.0",
    "yandex-webmaster-mcp": "1.1.0",
    "yandex-metrika-mcp": "1.1.0",
    "sharp": "0.34.4",
}

EXPECTED_SKILLS = {
    "vedicway-seo-ledger",
    "vedicway-yandex-signals",
    "vedicway-topic-planner",
    "vedicway-content-brief",
    "vedicway-article-writer",
    "vedicway-article-editor-ru",
    "vedicway-article-quality-gate",
    "vedicway-article-media",
    "vedicway-create-image",
    "vedicway-article-cover-image",
    "vedicway-pinterest-card-image",
    "vedicway-article-optimizer",
    "vedicway-site-publisher",
    "vedicway-dzen-distributor",
    "vedicway-lifecycle-review",
    "vedicway-distribution-planner",
    "vedicway-vk-publisher",
    "vedicway-pinterest-publisher",
}
BUILTIN_SKILLS = {"imagegen"}

FORBIDDEN_PUBLISHERS = (
    "joomla",
    "telegram",
    "virtuemart",
    "vc.ru",
    "max-publisher",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed VedicWay SEO agent release check")
    parser.add_argument("--env-file", default=".env.production")
    parser.add_argument("--static-only", action="store_true")
    args = parser.parse_args()
    env_path = Path(args.env_file).resolve()
    root = env_path.parent
    errors: list[str] = []
    if not args.static_only:
        try:
            values = parse_env(env_path)
        except (OSError, ValueError) as error:
            print(error, file=sys.stderr)
            return 2

        if values.get("VEDICWAY_SEO_AGENT_ENABLED") != "1":
            errors.append("VEDICWAY_SEO_AGENT_ENABLED must equal 1 for SEO profile activation")
        origin = urlsplit(values.get("VEDICWAY_PUBLIC_ORIGIN", ""))
        host_id = values.get("VEDICWAY_YANDEX_HOST_ID", "")
        if not origin.hostname or origin.scheme != "https":
            errors.append("VEDICWAY_PUBLIC_ORIGIN must be an absolute HTTPS origin")
        if not host_id or "replace" in host_id.casefold() or (origin.hostname and origin.hostname not in host_id):
            errors.append("VEDICWAY_YANDEX_HOST_ID must explicitly identify the VedicWay public host")
        counter = values.get("VEDICWAY_METRIKA_COUNTER_ID", "")
        if not re.fullmatch(r"\d+", counter) or counter != values.get("VITE_YANDEX_METRIKA_ID"):
            errors.append("VEDICWAY_METRIKA_COUNTER_ID must equal the numeric frontend Metrika counter")
        if not re.fullmatch(r"\d+", values.get("VEDICWAY_VK_GROUP_ID", "")):
            errors.append("VEDICWAY_VK_GROUP_ID must be numeric")
        if not values.get("VEDICWAY_PINTEREST_BOARD_NAME", "").strip() or "replace" in values.get("VEDICWAY_PINTEREST_BOARD_NAME", "").casefold():
            errors.append("VEDICWAY_PINTEREST_BOARD_NAME is missing")
        for name, minimum in SECRET_PATHS.items():
            raw = values.get(name, "")
            if not raw:
                errors.append(f"{name} is missing")
                continue
            path = resolve_input(root, raw)
            if not path.is_file():
                errors.append(f"secret file is missing for {name}")
                continue
            if len(path.read_text(encoding="utf-8").strip()) < minimum:
                errors.append(f"secret in {name} is shorter than {minimum} characters")

    config = (root / ".codex" / "config.toml").read_text(encoding="utf-8")
    configured = set(re.findall(r"^\[mcp_servers\.([^\]]+)\]$", config, re.MULTILINE))
    if configured != EXPECTED_MCP:
        errors.append("Repo-local Codex config must expose exactly eight approved VedicWay MCP servers")
    for target, variables in EXPECTED_MCP_LAUNCHERS.items():
        launcher = f'args = ["-m", "seo_agent.mcp_launcher", "{target}"]'
        env_contract = "env_vars = [" + ", ".join(f'"{name}"' for name in variables) + "]"
        if launcher not in config or env_contract not in config:
            errors.append(f"{target} MCP must use the isolated VedicWay launcher and environment")
    for platform in ("dzen", "pinterest"):
        launcher = f'args = ["-m", "seo_agent.browser_mcp_launcher", "{platform}"]'
        if launcher not in config:
            errors.append(f"{platform} browser MCP must use the isolated Playwright launcher")
    if 'env_vars = ["YANDEX_' in config:
        errors.append("Repo-local MCP config must not inherit generic YANDEX credentials")
    if any(name in config.casefold() for name in ("joomla", "telegram", "virtuemart", "max-publisher")):
        errors.append("Repo-local Codex config contains a forbidden publisher")

    lock = json.loads((root / "seo_agent" / "mcp" / "package-lock.json").read_text(encoding="utf-8"))
    dependencies = lock.get("packages", {}).get("", {}).get("dependencies", {})
    if dependencies != EXPECTED_PACKAGES:
        errors.append("Pinned MCP package set differs from the approved contract")
    specs = json.loads((root / "seo_agent" / "job_specs.json").read_text(encoding="utf-8"))
    names = {job.get("name") for job in specs.get("jobs", [])}
    if names != {
        "article_intelligence_refresh",
        "article_content_production",
        "article_site_publish",
        "dzen_daily_publish",
        "vk_daily_publish",
        "pinterest_daily_publish",
        "article_optimization",
        "article_lifecycle_review",
    }:
        errors.append("Scheduler job set must contain the eight approved VedicWay jobs")
    daily = {job.get("name"): job.get("interval_minutes") for job in specs.get("jobs", [])}
    for name in names - {"article_lifecycle_review"}:
        if daily.get(name) != 1440:
            errors.append(f"{name} must run daily")
    pinterest_job = next(
        (job for job in specs.get("jobs", []) if job.get("name") == "pinterest_daily_publish"),
        {},
    )
    if pinterest_job.get("daily_at_moscow") != "12:00":
        errors.append("Pinterest daily job must start at 12:00 Moscow time")
    pinterest_prompt = str(pinterest_job.get("prompt", ""))
    if not all(marker in pinterest_prompt for marker in ("10", "13:00", "22:00")):
        errors.append("Pinterest daily job must publish ten hourly cards from 13:00 to 22:00")
    migration = root / "seo_agent" / "migrations" / "005_pinterest_daily_batch.sql"
    if not migration.is_file() or "DROP INDEX IF EXISTS one_distribution_media_role_per_draft" not in migration.read_text(encoding="utf-8"):
        errors.append("Pinterest daily batch migration is missing")
    referenced_skills = {
        skill
        for job in specs.get("jobs", [])
        if isinstance(job, dict)
        for skill in job.get("skills", [])
        if isinstance(skill, str)
    }
    if referenced_skills != EXPECTED_SKILLS | BUILTIN_SKILLS:
        errors.append("Scheduler must reference the approved VedicWay and built-in skill set")
    skill_root = root / ".agents" / "skills"
    installed_skills = {
        path.name for path in skill_root.glob("vedicway-*") if path.is_dir()
    }
    if installed_skills != EXPECTED_SKILLS:
        errors.append("Repo-local VedicWay SEO skill directories differ from the approved contract")
    for name in sorted(EXPECTED_SKILLS):
        skill_file = skill_root / name / "SKILL.md"
        agent_file = skill_root / name / "agents" / "openai.yaml"
        if not skill_file.is_file() or not agent_file.is_file():
            errors.append(f"{name} must contain SKILL.md and agents/openai.yaml")
            continue
        skill_text = skill_file.read_text(encoding="utf-8")
        if not re.search(rf"(?m)^name:\s*{re.escape(name)}\s*$", skill_text):
            errors.append(f"{name} has an invalid frontmatter name")
        if "TODO" in skill_text:
            errors.append(f"{name} still contains TODO")
        folded = skill_text.casefold()
        if any(publisher in folded for publisher in FORBIDDEN_PUBLISHERS):
            errors.append(f"{name} references a forbidden publisher")
    dockerfile = (root / "docker" / "backend" / "Dockerfile").read_text(encoding="utf-8")
    if "COPY .agents ./.agents" in dockerfile:
        errors.append("SEO runtime must not copy the unrestricted repo-local skill tree")
    for name in sorted(EXPECTED_SKILLS | {"vedic-astrology"}):
        expected_copy = f"COPY .agents/skills/{name} ./.agents/skills/{name}"
        if expected_copy not in dockerfile:
            errors.append(f"Backend image is missing the approved runtime skill {name}")
    if "COPY .agents/skills/numerology" in dockerfile:
        errors.append("SEO runtime must not include the unrelated numerology skill")
    for package in ("vk-group-mcp", "agent-control-mcp"):
        entrypoint = root / "seo_agent" / "mcp" / "packages" / package / "src" / "index.js"
        if package == "agent-control-mcp":
            entrypoint = entrypoint.with_suffix(".mjs")
        if not entrypoint.is_file():
            errors.append(f"SEO runtime is missing {package}")
    if (root / "seo_agent" / "mcp" / "packages" / "pinterest-business-mcp" / "src" / "index.mjs").exists():
        errors.append("Pinterest API publisher must be absent from the browser-only release")
    browser_lock = json.loads(
        (root / "seo_agent" / "browser_runtime" / "package-lock.json").read_text(encoding="utf-8")
    )
    browser_dependencies = browser_lock.get("packages", {}).get("", {}).get("dependencies", {})
    if browser_dependencies != {
        "@playwright/mcp": "0.0.79",
        "cloakbrowser": "0.4.8",
        "playwright": "1.61.1",
        "playwright-core": "1.61.1",
    }:
        errors.append("Pinned Playwright browser runtime differs from the donor contract")
    scheduler = (root / "seo_agent" / "scheduler.py").read_text(encoding="utf-8")
    for guard in (
        '"--strict-config"',
        '"--ignore-user-config"',
        '"--ephemeral"',
        '"--sandbox", "read-only"',
        '"VEDICWAY_SEO_CODEX_HOME"',
        'service_tier=',
        "MCP_CONFIG_OVERRIDES",
        "JOB_MCP_SERVERS",
        "seo_agent.mcp_launcher",
        "seo_agent.browser_mcp_launcher",
        "vedicway-control",
    ):
        if guard not in scheduler:
            errors.append(f"SEO scheduler is missing Codex execution guard {guard}")
    for server in EXPECTED_MCP:
        if f"mcp_servers.{server}" not in scheduler:
            errors.append(f"SEO scheduler does not inject the isolated MCP server {server}")
    for forbidden in (
        '"--sandbox", "workspace-write"',
        '"sandbox_workspace_write.network_access=true"',
        '"--add-dir"',
    ):
        if forbidden in scheduler:
            errors.append(f"SEO scheduler contains forbidden Codex execution setting {forbidden}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("VedicWay SEO agent inputs, Skills, identity guards, MCP set and scheduler contract passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
