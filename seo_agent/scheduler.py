from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .bootstrap import bootstrap
from .db import AgentLedger, LedgerError

ROOT = Path(__file__).resolve().parents[1]
MOSCOW = ZoneInfo("Europe/Moscow")
RUN_LEASE_STALE_AFTER_SECONDS = 300

MCP_CONFIG_OVERRIDES = (
    'mcp_servers.vedicway-yandex-search={ command = "python", '
    'args = ["-m", "seo_agent.mcp_launcher", "search"], '
    'env_vars = ["VEDICWAY_YANDEX_SEARCH_API_KEY", "VEDICWAY_YANDEX_FOLDER_ID"], '
    'default_tools_approval_mode = "approve", '
    'startup_timeout_sec = 20, tool_timeout_sec = 120 }',
    'mcp_servers.vedicway-yandex-wordstat={ command = "python", '
    'args = ["-m", "seo_agent.mcp_launcher", "wordstat"], '
    'env_vars = ["VEDICWAY_YANDEX_SEARCH_API_KEY", "VEDICWAY_YANDEX_FOLDER_ID"], '
    'default_tools_approval_mode = "approve", '
    'startup_timeout_sec = 20, tool_timeout_sec = 120 }',
    'mcp_servers.vedicway-yandex-webmaster={ command = "python", '
    'args = ["-m", "seo_agent.mcp_launcher", "webmaster"], '
    'env_vars = ["VEDICWAY_YANDEX_WEBMASTER_TOKEN"], '
    'default_tools_approval_mode = "approve", '
    'startup_timeout_sec = 20, tool_timeout_sec = 120 }',
    'mcp_servers.vedicway-yandex-metrika={ command = "python", '
    'args = ["-m", "seo_agent.mcp_launcher", "metrika"], '
    'env_vars = ["VEDICWAY_YANDEX_METRIKA_TOKEN"], '
    'default_tools_approval_mode = "approve", '
    'startup_timeout_sec = 20, tool_timeout_sec = 120 }',
    'mcp_servers.vedicway-vk={ command = "python", '
    'args = ["-m", "seo_agent.mcp_launcher", "vk"], '
    'env_vars = ["VEDICWAY_VK_GROUP_ID", "VEDICWAY_VK_GROUP_ACCESS_TOKEN", "VEDICWAY_VK_USER_ACCESS_TOKEN"], '
    'default_tools_approval_mode = "approve", '
    'startup_timeout_sec = 20, tool_timeout_sec = 120 }',
    'mcp_servers.vedicway-dzen-browser={ command = "python", '
    'args = ["-m", "seo_agent.browser_mcp_launcher", "dzen"], '
    'env_vars = ["VEDICWAY_SEO_DATA_DIR", "VEDICWAY_DZEN_CDP_URL"], '
    'default_tools_approval_mode = "approve", '
    'startup_timeout_sec = 20, tool_timeout_sec = 180 }',
    'mcp_servers.vedicway-pinterest-browser={ command = "python", '
    'args = ["-m", "seo_agent.browser_mcp_launcher", "pinterest"], '
    'env_vars = ["VEDICWAY_SEO_DATA_DIR", "VEDICWAY_PINTEREST_CDP_URL"], '
    'default_tools_approval_mode = "approve", '
    'startup_timeout_sec = 20, tool_timeout_sec = 180 }',
    'mcp_servers.vedicway-control={ command = "python", '
    'args = ["-m", "seo_agent.mcp_launcher", "control"], '
    'env_vars = ["PYTHONPATH", "VEDICWAY_SEO_DATABASE_URL", "DATABASE_URL", "VEDICWAY_DATABASE_URL", '
    '"VEDICWAY_SEO_DATA_DIR", "VEDICWAY_SEO_RUN_ID", "VEDICWAY_SEO_JOB_NAME", '
    '"VEDICWAY_SEO_AGENT_TOKEN", '
    '"VEDICWAY_SEO_AGENT_BASE_URL", "VEDICWAY_PUBLIC_ORIGIN", '
    '"VEDICWAY_SEO_JOB_TIMEOUT_SECONDS", "VEDICWAY_IMAGEGEN_RUN_STARTED_NS", '
    '"VEDICWAY_PINTEREST_BOARD_NAME", "CODEX_HOME"], '
    'default_tools_approval_mode = "approve", '
    'startup_timeout_sec = 20, tool_timeout_sec = 180 }',
)

JOB_MCP_SERVERS = {
    "article_intelligence_refresh": {
        "vedicway-control",
        "vedicway-yandex-search",
        "vedicway-yandex-wordstat",
        "vedicway-yandex-webmaster",
        "vedicway-yandex-metrika",
    },
    "article_content_production": {"vedicway-control"},
    "article_site_publish": {"vedicway-control"},
    "dzen_daily_publish": {"vedicway-control", "vedicway-dzen-browser"},
    "vk_daily_publish": {"vedicway-control", "vedicway-vk"},
    "pinterest_daily_publish": {"vedicway-control", "vedicway-pinterest-browser"},
    "article_optimization": {"vedicway-control"},
    "article_lifecycle_review": {
        "vedicway-control",
        "vedicway-yandex-search",
        "vedicway-yandex-wordstat",
        "vedicway-yandex-webmaster",
        "vedicway-yandex-metrika",
    },
}

SENSITIVE_JOB_ENVIRONMENT = {
    "OPENAI_API_KEY",
    "VEDICWAY_YANDEX_SEARCH_API_KEY",
    "VEDICWAY_YANDEX_FOLDER_ID",
    "VEDICWAY_YANDEX_WEBMASTER_TOKEN",
    "VEDICWAY_YANDEX_METRIKA_TOKEN",
    "VEDICWAY_VK_GROUP_ACCESS_TOKEN",
    "VEDICWAY_VK_USER_ACCESS_TOKEN",
    "VEDICWAY_SEO_AGENT_TOKEN",
}

RUN_COMPLETION_INSTRUCTIONS = """После выполнения всей работы запиши в seo_agent.run_logs текущего Run ID через vedicway_record_run_log коротко лог того, как ты выполнял задачу и возникли ли какие-то ошибки. Вызови vedicway_record_run_log ровно один раз и передай только поле log_text. Затем обязательно вызови vedicway_record_result ровно один раз.

<!-- writing & answering format -->

Отвечай мне всегда естественным публицистическим русским языком, наполненным естественными словоформами и без нейросетевой риторики и пустой связности слов в предложении.

Эта инструкция затрагивает только твою работу с непосредственными ответами мне в чате и написании текстов в файлах.

Главные ограничения в своих ответах и тексте, которые ты обязан соблюдать:

- Используй больше густых абзацев и меньше списков. Если используешь списки в своих ответах - количество пунктов должно быть до 3-х. Пунктов может быть больше только если список планируется создаваться не в формате "1 пункт - одно или пара слов", а в формате "1 пункт - один абзац"

- Сильно реже используй перечисления однородных членов. Если есть возможность изложить мысль 1 фразой, которая объединяет однородные члены - используй ее. Избегай перечислений из трёх элементов; используй только пары или одиночные понятия (в редких исключениях, когда по-другому ну никак нельзя полно изложить мысли - используй больше однородных членов)

- Избегай речевые конструкции: "Это не про X, это про Y", "Это не X, это Y", "X это про ...", "Не X, а Y", "X - это не Y, а Z"

- Избегай канцеляризмов и излишества вводных конструкций

- Не пиши заключительный абзац; закончи последней содержательной мыслью

- Избегай универсальных хеджей оговорок по типу: «Стоит отметить», «важно понимать», «следует признать», «безусловно», «несомненно».

- Тексты и ответы которые ты пишешь должны быть с авторской позиций и строго от тебя как ПЕРСОНЫ. Ты не должен балансировать картину, нужно больше категоричности, если я не прошу обратного. Избегай конструкции по типу "с одной стороны / с другой стороны"

- ИИ-тексты имеют статистически узкое распределение длин абзацев — обычно 3-5 предложений каждый, с редкими отклонениями. ТЫ должен отклоняться от этого среднего числа чаще и делать это релевантно и подходяще по стилю

- используй конкретные числа, имена, события вместо обобщений; не используй фразы по типу “открывает возможности”, “играет ключевую роль”, “выходит на новый уровень” и тому подобное

- Избегай кавычек "елочек" и длинных тире

- когда утверждение фактически верно, не добавляй “потенциально”, “как правило”, “обычно”, нужно утверждать уверенно

- Каждое предложение должно сообщать факт, объяснять причинную связь, давать решение, пример, действие или ограничение. Если оно ничего не меняет, убери его. Начинай с сути: вывода, тезиса, события, проблемы или прямого ответа. Не пиши формальное вступление и формальный вывод; заканчивай последней полезной мыслью.

- Пиши по-русски. Английское слово оставляй только если это официальное название, код, устоявшийся термин для этой аудитории или русский перевод исказит смысл. Иначе используй естественный русский эквивалент.

- Предпочитай активные глаголы и называй того, кто действует. Не раздувай фразы отглагольными существительными, пассивным залогом и цепочками существительных. По умолчанию избегай канцелярита, пустых оценок и конструкций вроде: «данный», «является», «в рамках», «осуществлять», «имеет важное значение», «позволяет повысить эффективность», «в современном мире», «важно отметить», «следует отметить», «безусловно», «таким образом», «подводя итоги», «не просто X, а Y», «это не X, это Y». Не заменяй их синонимами: либо дай конкретику, либо убери фразу.

- Не дроби объяснительный текст на цепочку абзацев из одного-двух предложений. Абзац должен содержать законченную мысль; короткий абзац допустим только как осознанный акцент, переход или если этого требует площадка. Чередуй длину предложений естественно, но не пиши рублеными фразами подряд.

<!-- writing & answering format -->"""


def mcp_overrides_for_job(name: str) -> tuple[str, ...]:
    if name not in JOB_MCP_SERVERS:
        raise LedgerError(f"Unknown MCP policy for job: {name}")
    enabled = JOB_MCP_SERVERS[name]
    return tuple(
        override
        for override in MCP_CONFIG_OVERRIDES
        if any(f"mcp_servers.{server}=" in override for server in enabled)
    )


def job_environment(
    job: dict[str, Any], base: dict[str, str] | None = None
) -> dict[str, str]:
    name = str(job["name"])
    enabled = JOB_MCP_SERVERS.get(name)
    if enabled is None:
        raise LedgerError(f"Unknown environment policy for job: {name}")
    source = dict(base or os.environ)
    allowed: set[str] = set()
    if any(server.startswith("vedicway-yandex-") for server in enabled):
        allowed.update(
            {
                "VEDICWAY_YANDEX_SEARCH_API_KEY",
                "VEDICWAY_YANDEX_FOLDER_ID",
                "VEDICWAY_YANDEX_WEBMASTER_TOKEN",
                "VEDICWAY_YANDEX_METRIKA_TOKEN",
            }
        )
    if "vedicway-vk" in enabled:
        allowed.update(
            {"VEDICWAY_VK_GROUP_ACCESS_TOKEN", "VEDICWAY_VK_USER_ACCESS_TOKEN"}
        )
    if name in {"article_site_publish", "article_optimization"}:
        allowed.add("VEDICWAY_SEO_AGENT_TOKEN")
    for variable in SENSITIVE_JOB_ENVIRONMENT.difference(allowed):
        source.pop(variable, None)
    if name in {"article_content_production", "article_optimization"}:
        source["VEDICWAY_IMAGEGEN_RUN_STARTED_NS"] = str(time.time_ns())
    source["VEDICWAY_SEO_JOB_NAME"] = name
    return source


def bootstrap_seed_data_enabled() -> bool:
    return os.getenv("VEDICWAY_SEO_BOOTSTRAP_SEEDS", "0") == "1"


def load_jobs(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        raise LedgerError("job_specs.json has no jobs array")
    result: dict[str, dict[str, Any]] = {}
    for job in jobs:
        if not isinstance(job, dict) or not isinstance(job.get("name"), str):
            raise LedgerError("Invalid job specification")
        if job["name"] in result:
            raise LedgerError(f"Duplicate job name: {job['name']}")
        if (
            not isinstance(job.get("interval_minutes"), int)
            or job["interval_minutes"] < 1
            or not isinstance(job.get("model"), str)
            or job.get("reasoning_effort")
            not in {"low", "medium", "high", "xhigh", "max", "ultra"}
            or not isinstance(job.get("prompt"), str)
            or not job["prompt"].strip()
            or not isinstance(job.get("skills"), list)
            or not job["skills"]
            or any(not isinstance(skill, str) or not skill for skill in job["skills"])
        ):
            raise LedgerError(f"Incomplete job specification: {job['name']}")
        daily_at = job.get("daily_at_moscow")
        if daily_at is not None and not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", str(daily_at)):
            raise LedgerError(f"Invalid Moscow schedule: {job['name']}")
        result[job["name"]] = job
    return result


def daily_schedule_due(
    latest_started_at: str | None,
    schedule_time: str,
    now: datetime | None = None,
) -> bool:
    if not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", schedule_time):
        raise LedgerError("Daily schedule must use HH:MM")
    current = (now or datetime.now(UTC)).astimezone(MOSCOW)
    hour, minute = (int(part) for part in schedule_time.split(":"))
    scheduled = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if current < scheduled or current >= scheduled + timedelta(hours=1):
        return False
    if latest_started_at is None:
        return True
    latest = datetime.fromisoformat(latest_started_at.replace("Z", "+00:00"))
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=UTC)
    return latest.astimezone(MOSCOW) < scheduled


def preflight(job: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if os.environ.get("VEDICWAY_SEO_AGENT_ENABLED", "0") != "1":
        errors.append("VEDICWAY_SEO_AGENT_ENABLED must equal 1")
    codex_home = Path(os.environ.get("CODEX_HOME", "")).expanduser()
    if not (codex_home / "auth.json").is_file():
        errors.append("Codex authentication is missing")
    if job["name"] in {"article_content_production", "article_optimization"}:
        imagegen_skill = codex_home / "skills" / ".system" / "imagegen" / "SKILL.md"
        if not imagegen_skill.is_file():
            errors.append("Built-in Codex imagegen skill is missing")
    if not os.environ.get("VEDICWAY_SEO_AGENT_TOKEN"):
        errors.append("VEDICWAY_SEO_AGENT_TOKEN is missing")
    service_tier = os.environ.get("VEDICWAY_CODEX_SERVICE_TIER", "fast")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", service_tier):
        errors.append("VEDICWAY_CODEX_SERVICE_TIER has an invalid value")
    try:
        timeout_seconds = int(os.environ.get("VEDICWAY_SEO_JOB_TIMEOUT_SECONDS", "3600"))
        if not 60 <= timeout_seconds <= 86_100:
            raise ValueError
    except ValueError:
        errors.append("VEDICWAY_SEO_JOB_TIMEOUT_SECONDS must be between 60 and 86100")
    if job["name"] == "article_lifecycle_review":
        if not os.environ.get("VEDICWAY_YANDEX_HOST_ID"):
            errors.append("VEDICWAY_YANDEX_HOST_ID is missing")
        if not os.environ.get("VEDICWAY_METRIKA_COUNTER_ID"):
            errors.append("VEDICWAY_METRIKA_COUNTER_ID is missing")
    if job["name"] == "vk_daily_publish":
        if not os.environ.get("VEDICWAY_VK_GROUP_ID"):
            errors.append("VEDICWAY_VK_GROUP_ID is missing")
        if not os.environ.get("VEDICWAY_VK_GROUP_ACCESS_TOKEN"):
            errors.append("VEDICWAY_VK_GROUP_ACCESS_TOKEN is missing")
        if not os.environ.get("VEDICWAY_VK_USER_ACCESS_TOKEN"):
            errors.append("VEDICWAY_VK_USER_ACCESS_TOKEN is missing")
    if job["name"] == "pinterest_daily_publish":
        if not os.environ.get("VEDICWAY_PINTEREST_BOARD_NAME"):
            errors.append("VEDICWAY_PINTEREST_BOARD_NAME is missing")
    executable = Path(os.environ.get("VEDICWAY_CODEX_EXECUTABLE", "codex"))
    if executable.is_absolute() and not executable.is_file():
        errors.append(f"Codex executable is missing: {executable}")
    if os.environ.get("VEDICWAY_ENV", "development").casefold() == "production":
        active_home = os.environ.get("CODEX_HOME", "").strip()
        dedicated_home = os.environ.get("VEDICWAY_SEO_CODEX_HOME", "").strip()
        if (
            not active_home
            or not dedicated_home
            or Path(active_home).expanduser().resolve()
            != Path(dedicated_home).expanduser().resolve()
        ):
            errors.append(
                "CODEX_HOME must equal the dedicated VEDICWAY_SEO_CODEX_HOME in production"
            )
    return errors


def build_prompt(job: dict[str, Any], run_id: str) -> str:
    skills = ", ".join(f"${name}" for name in job["skills"])
    context_parts: list[str] = []
    if job["name"] == "pinterest_daily_publish":
        context_parts.append(
            " Доска Pinterest для CSV: "
            + os.environ.get("VEDICWAY_PINTEREST_BOARD_NAME", "").strip()
            + "."
        )
    if job["name"] in {"article_intelligence_refresh", "article_lifecycle_review"}:
        context_parts.append(
            " Разрешённый Webmaster host_id: "
            + os.environ.get("VEDICWAY_YANDEX_HOST_ID", "").strip()
            + "; разрешённый Metrika counter_id: "
            + os.environ.get("VEDICWAY_METRIKA_COUNTER_ID", "").strip()
            + "."
        )
    if job["name"] == "article_intelligence_refresh":
        context_parts.append(
            " Это исследовательский run: создавай свежие query и cluster records, "
            "не вызывай ledger_claim."
        )
    elif job["name"] == "article_lifecycle_review":
        context_parts.append(
            " Читай очередь только через vedicway_ledger_due_lifecycle; "
            "не вызывай ledger_claim."
        )
    return (
        "Ты выполняешь автономный production-run SEO-контура VedicWay. "
        f"Run ID: {run_id}. Используй Skills: {skills}. "
        "Работай с реестром и сайтом только через MCP vedicway-control. "
        "Изображения создавай только через системный Skill $imagegen и встроенный image_gen tool, "
        "ровно одним отдельным вызовом на каждый файл. Не используй OpenAI API, imagegen-MCP, "
        "shell или Python для генерации. Готовый файл из CODEX_HOME/generated_images импортируй "
        "через MCP vedicway-control инструментом vedicway_import_generated_image. Если image_gen "
        "не вернул source_path, вызови импорт без source_path: control сам выберет свежий, ещё не "
        "импортированный файл текущего run; "
        "не запускай shell, Python CLI, произвольный SQL и не используй административные cookie. "
        "Как raw_tool_response сохраняй только ответы внешних исследовательских и "
        "публикационных API: Yandex Search, Wordstat, Webmaster, Metrika и VK. "
        "Действия Playwright MCP и browser snapshot как tool-response не записывай; terminal "
        "browser evidence сохраняй только внутри publication-attempt или distribution-attempt. "
        "Ответы vedicway-control не сохраняй как tool-response: health, claim и чтение очереди "
        "уже принадлежат реестру. Для Yandex provider используй только yandex-search, wordstat, "
        "webmaster или metrika. "
        + str(job["prompt"])
        + "".join(context_parts)
        + "\n\n"
        + RUN_COMPLETION_INSTRUCTIONS
    )


def build_codex_command(
    job: dict[str, Any], *, executable: str, workdir: Path, data_dir: Path
) -> list[str]:
    command = [
        executable,
        "exec", "--skip-git-repo-check", "--strict-config", "--ignore-user-config",
        "--ephemeral", "--disable", "shell_tool", "--color", "never",
        "--sandbox", "read-only",
        "--cd", str(workdir),
    ]
    if job["name"] == "vk_daily_publish":
        command.extend(("--config", "features.use_legacy_landlock=true"))
    for override in mcp_overrides_for_job(str(job["name"])):
        command.extend(("--config", override))
    command.extend(
        (
            "--model", str(job["model"]),
            "--config", f'model_reasoning_effort="{job["reasoning_effort"]}"',
            "--config",
            f'service_tier="{os.environ.get("VEDICWAY_CODEX_SERVICE_TIER", "fast")}"',
            "-",
        )
    )
    return command


def run_job(name: str, jobs: dict[str, dict[str, Any]], *, dry_run: bool = False) -> dict[str, Any]:
    if name not in jobs:
        raise LedgerError(f"Unknown job: {name}")
    job = jobs[name]
    failures = preflight(job)
    if dry_run:
        return {"job": name, "dry_run": True, "preflight_errors": failures, "skills": job["skills"]}
    if failures:
        raise LedgerError("; ".join(failures))
    ledger = AgentLedger()
    ledger.initialize()
    workdir = Path(os.environ.get("VEDICWAY_SEO_AGENT_WORKDIR", ROOT)).expanduser().resolve()
    if not workdir.is_dir():
        raise LedgerError(f"SEO agent workdir is missing: {workdir}")
    schedule_token = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M")
    timeout_seconds = int(os.environ.get("VEDICWAY_SEO_JOB_TIMEOUT_SECONDS", "3600"))
    lease = ledger.start_run(
        name,
        schedule_token,
        stale_after_seconds=RUN_LEASE_STALE_AFTER_SECONDS,
    )
    command = build_codex_command(
        job,
        executable=os.environ.get("VEDICWAY_CODEX_EXECUTABLE", "codex"),
        workdir=workdir,
        data_dir=ledger.data_dir,
    )
    env = job_environment(job)
    env["VEDICWAY_SEO_RUN_ID"] = lease["run_id"]
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            cwd=workdir,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert process.stdin is not None
        process.stdin.write(build_prompt(job, lease["run_id"]))
        process.stdin.close()
        deadline = time.monotonic() + timeout_seconds
        while process.poll() is None:
            if time.monotonic() >= deadline:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
                raise LedgerError(f"Codex exceeded {timeout_seconds} seconds")
            ledger.heartbeat(lease["run_id"], lease["owner_token"])
            time.sleep(20)
        return_code = int(process.returncode or 0)
        failed = None if return_code == 0 else f"Codex exited with code {return_code}"
        status = ledger.finish_run(lease["run_id"], lease["owner_token"], failed_error=failed)
        return {"job": name, "run_id": lease["run_id"], "status": status, "return_code": return_code}
    except (LedgerError, OSError, subprocess.TimeoutExpired) as error:
        try:
            ledger.finish_run(lease["run_id"], lease["owner_token"], failed_error=str(error))
        except LedgerError:
            pass
        raise LedgerError(str(error)) from error


def due_jobs(
    ledger: AgentLedger,
    jobs: dict[str, dict[str, Any]],
    *,
    stale_after_seconds: int | None = None,
) -> list[str]:
    if stale_after_seconds is None:
        stale_after_seconds = RUN_LEASE_STALE_AFTER_SECONDS
    with ledger.connect() as connection:
        rows = {}
        for name in jobs:
            row = connection.execute(
                """SELECT status,started_at,heartbeat_at,finished_at
                FROM cron_runs WHERE job_name=%s ORDER BY started_at DESC LIMIT 1""",
                (name,),
            ).fetchone()
            if row:
                rows[name] = dict(row)
    now = datetime.now(UTC)
    due: list[str] = []
    for name, job in jobs.items():
        latest = rows.get(name)
        status = latest["status"] if latest else None
        if status == "running":
            heartbeat = latest["heartbeat_at"] or latest["started_at"]
            if (
                datetime.fromisoformat(heartbeat.replace("Z", "+00:00"))
                + timedelta(seconds=stale_after_seconds)
                <= now
                and (
                    job.get("daily_at_moscow") is None
                    or daily_schedule_due(None, str(job["daily_at_moscow"]), now)
                )
            ):
                due.append(name)
            continue
        daily_at = job.get("daily_at_moscow")
        if daily_at is not None:
            if daily_schedule_due(
                latest["started_at"] if latest else None,
                str(daily_at),
                now,
            ):
                due.append(name)
            continue
        if latest is None:
            due.append(name)
            continue
        wait_minutes = int(job["interval_minutes"])
        if status == "failed":
            wait_minutes = 15
        elif status == "blocked":
            wait_minutes = 360
        observed = latest["finished_at"] or latest["started_at"]
        if datetime.fromisoformat(observed.replace("Z", "+00:00")) + timedelta(minutes=wait_minutes) <= now:
            due.append(name)
    return due


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VedicWay SEO scheduler")
    parser.add_argument("mode", choices=("run", "daemon", "preflight"))
    parser.add_argument("--job")
    parser.add_argument("--specs", type=Path, default=Path(__file__).with_name("job_specs.json"))
    parser.add_argument("--poll-seconds", type=int, default=60)
    args = parser.parse_args(argv)
    try:
        jobs = load_jobs(args.specs)
        if args.mode == "preflight":
            targets = [args.job] if args.job else list(jobs)
            print(json.dumps([run_job(name, jobs, dry_run=True) for name in targets], ensure_ascii=False))
            return 0
        if args.mode == "run":
            if not args.job:
                raise LedgerError("--job is required in run mode")
            print(json.dumps(run_job(args.job, jobs), ensure_ascii=False))
            return 0
        ledger = AgentLedger()
        ledger.initialize()
        if bootstrap_seed_data_enabled() and ledger.summary()["counts"]["keyword_queries"] == 0:
            bootstrap(ROOT)
        while True:
            for name in due_jobs(ledger, jobs):
                try:
                    print(json.dumps(run_job(name, jobs), ensure_ascii=False), flush=True)
                except LedgerError as error:
                    print(json.dumps({"job": name, "status": "failed", "error": str(error)}, ensure_ascii=False), file=sys.stderr, flush=True)
            time.sleep(max(30, args.poll_seconds))
    except (LedgerError, OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
