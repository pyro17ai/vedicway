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

from .bootstrap import bootstrap
from .db import AgentLedger, LedgerError

ROOT = Path(__file__).resolve().parents[1]

MCP_CONFIG_OVERRIDES = (
    'mcp_servers.vedicway-yandex-search={ command = "python", '
    'args = ["-m", "seo_agent.mcp_launcher", "search"], '
    'env_vars = ["VEDICWAY_YANDEX_SEARCH_API_KEY", "VEDICWAY_YANDEX_FOLDER_ID"], '
    'startup_timeout_sec = 20, tool_timeout_sec = 120 }',
    'mcp_servers.vedicway-yandex-wordstat={ command = "python", '
    'args = ["-m", "seo_agent.mcp_launcher", "wordstat"], '
    'env_vars = ["VEDICWAY_YANDEX_SEARCH_API_KEY", "VEDICWAY_YANDEX_FOLDER_ID"], '
    'startup_timeout_sec = 20, tool_timeout_sec = 120 }',
    'mcp_servers.vedicway-yandex-webmaster={ command = "python", '
    'args = ["-m", "seo_agent.mcp_launcher", "webmaster"], '
    'env_vars = ["VEDICWAY_YANDEX_WEBMASTER_TOKEN"], '
    'startup_timeout_sec = 20, tool_timeout_sec = 120 }',
    'mcp_servers.vedicway-yandex-metrika={ command = "python", '
    'args = ["-m", "seo_agent.mcp_launcher", "metrika"], '
    'env_vars = ["VEDICWAY_YANDEX_METRIKA_TOKEN"], '
    'startup_timeout_sec = 20, tool_timeout_sec = 120 }',
)


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
        result[job["name"]] = job
    return result


def preflight(job: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if os.environ.get("VEDICWAY_SEO_AGENT_ENABLED", "0") != "1":
        errors.append("VEDICWAY_SEO_AGENT_ENABLED must equal 1")
    if not os.environ.get("OPENAI_API_KEY"):
        errors.append("OPENAI_API_KEY is missing")
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
    if job["name"] in {"article_intelligence_refresh", "article_lifecycle_review"}:
        if not os.environ.get("VEDICWAY_YANDEX_HOST_ID"):
            errors.append("VEDICWAY_YANDEX_HOST_ID is missing")
        if not os.environ.get("VEDICWAY_METRIKA_COUNTER_ID"):
            errors.append("VEDICWAY_METRIKA_COUNTER_ID is missing")
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
    return (
        "Ты выполняешь автономный production-run SEO-контура VedicWay. "
        f"Run ID: {run_id}. Используй Skills: {skills}. "
        "Работай только с БД из VEDICWAY_SEO_DB через python -m seo_agent.cli; "
        "не подключайся к PostgreSQL сайта и не используй административные cookie. "
        "Любой внешний ответ сначала сохрани как raw_tool_response. "
        "В конце обязательно выполни record-result ровно один раз. "
        + str(job["prompt"])
    )


def build_codex_command(
    job: dict[str, Any], *, executable: str, workdir: Path, data_dir: Path
) -> list[str]:
    command = [
        executable,
        "exec", "--skip-git-repo-check", "--strict-config", "--ignore-user-config",
        "--ephemeral", "--color", "never", "--sandbox", "workspace-write",
        "--add-dir", str(data_dir), "--cd", str(workdir),
    ]
    for override in MCP_CONFIG_OVERRIDES:
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
    lease = ledger.start_run(name, schedule_token, stale_after_seconds=timeout_seconds + 300)
    command = build_codex_command(
        job,
        executable=os.environ.get("VEDICWAY_CODEX_EXECUTABLE", "codex"),
        workdir=workdir,
        data_dir=ledger.data_dir,
    )
    env = os.environ.copy()
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
        stale_after_seconds = (
            int(os.environ.get("VEDICWAY_SEO_JOB_TIMEOUT_SECONDS", "3600")) + 300
        )
    with ledger.connect() as connection:
        rows = {}
        for name in jobs:
            row = connection.execute(
                """SELECT status,started_at,heartbeat_at,finished_at
                FROM cron_runs WHERE job_name=? ORDER BY started_at DESC LIMIT 1""",
                (name,),
            ).fetchone()
            if row:
                rows[name] = dict(row)
    now = datetime.now(UTC)
    due: list[str] = []
    for name, job in jobs.items():
        latest = rows.get(name)
        if latest is None:
            due.append(name)
            continue
        status = latest["status"]
        wait_minutes = int(job["interval_minutes"])
        if status == "failed":
            wait_minutes = 15
        elif status == "blocked":
            wait_minutes = 360
        elif status == "running":
            heartbeat = latest["heartbeat_at"] or latest["started_at"]
            if (
                datetime.fromisoformat(heartbeat.replace("Z", "+00:00"))
                + timedelta(seconds=stale_after_seconds)
                <= now
            ):
                due.append(name)
            continue
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
        if ledger.summary()["counts"]["keyword_queries"] == 0:
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
