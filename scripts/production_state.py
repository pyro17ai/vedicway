from __future__ import annotations

import argparse
import os
import re
import secrets
import subprocess
from datetime import UTC, datetime
from pathlib import Path

CORE_SERVICES = ("frontend", "backend", "worker", "email")
BUNDLE_RE = re.compile(r"vedicway-pair-([A-Za-z0-9][A-Za-z0-9._-]{7,63})\.vwb")


def _run(base: list[str], *args: str, env: dict[str, str]) -> None:
    subprocess.run([*base, *args], check=True, env=env)


def _services(env: dict[str, str]) -> tuple[str, ...]:
    return (*CORE_SERVICES, "seo-agent") if env.get("VEDICWAY_SEO_AGENT_ENABLED") == "1" else CORE_SERVICES


def _resume(base: list[str], env: dict[str, str]) -> None:
    profile = ("--profile", "seo") if env.get("VEDICWAY_SEO_AGENT_ENABLED") == "1" else ()
    _run(base, *profile, "up", "-d", *_services(env), env=env)


def _load_env(path: Path, current: dict[str, str]) -> dict[str, str]:
    merged = dict(current)
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        merged.setdefault(name.strip(), value.strip())
    return merged


def backup(base: list[str], env: dict[str, str]) -> str:
    pair_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}"
    operation_env = {**env, "BACKUP_SET_ID": pair_id}
    _run(base, "stop", *_services(operation_env), env=operation_env)
    try:
        _run(base, "--profile", "ops", "run", "--rm", "backup", env=operation_env)
        _run(base, "--profile", "ops", "run", "--rm", "runtime-backup", env=operation_env)
        _run(base, "--profile", "ops", "run", "--rm", "seo-agent-backup", env=operation_env)
        _run(base, "--profile", "ops", "run", "--rm", "backup-bundle", "seal", env=operation_env)
    finally:
        _resume(base, operation_env)
    return f"vedicway-pair-{pair_id}.vwb"


def restore(base: list[str], env: dict[str, str], bundle: str) -> None:
    match = BUNDLE_RE.fullmatch(Path(bundle).name)
    if not match or Path(bundle).name != bundle:
        raise SystemExit("--bundle must be a plain VedicWay .vwb file name")
    pair_id = match.group(1)
    stage = f"/backups/.restore-{pair_id}"
    operation_env = {
        **env,
        "BACKUP_BUNDLE_FILE": bundle,
        "BACKUP_SET_ID": pair_id,
        "RESTORE_SET_ID": pair_id,
        "RESTORE_FILE": "postgres.dump",
        "RESTORE_RUNTIME_FILE": "runtime.tar.gz",
        "RESTORE_SEO_FILE": "seo-agent.sqlite3",
        "CONFIRM_RESTORE": f"restore-{env.get('POSTGRES_DB', 'vedicway')}",
        "CONFIRM_RUNTIME_RESTORE": "restore-runtime",
        "CONFIRM_SEO_RESTORE": "restore-seo-agent",
    }
    _run(base, "stop", *_services(operation_env), env=operation_env)
    try:
        try:
            _run(base, "--profile", "ops", "run", "--rm", "backup-bundle", "unseal", env=operation_env)
            prepare_env = {**operation_env, "RESTORE_BACKUP_DIR": stage, "RESTORE_PHASE": "prepare"}
            _run(base, "--profile", "ops", "run", "--rm", "restore", env=prepare_env)
            _run(base, "--profile", "ops", "run", "--rm", "runtime-restore", "prepare", env=prepare_env)
            _run(base, "--profile", "ops", "run", "--rm", "seo-agent-restore", "prepare", env=prepare_env)

            commit_env = {**prepare_env, "RESTORE_PHASE": "commit"}
            _run(base, "--profile", "ops", "run", "--rm", "restore", env=commit_env)
            _run(base, "--profile", "ops", "run", "--rm", "runtime-restore", "commit", env=commit_env)
            _run(base, "--profile", "ops", "run", "--rm", "seo-agent-restore", "commit", env=commit_env)
        except Exception:
            rollback_env = {**operation_env, "RESTORE_BACKUP_DIR": stage, "RESTORE_PHASE": "rollback"}
            runtime_rollback = subprocess.run([*base, "--profile", "ops", "run", "--rm", "runtime-restore", "rollback"], env=rollback_env, check=False)
            seo_rollback = subprocess.run([*base, "--profile", "ops", "run", "--rm", "seo-agent-restore", "rollback"], env=rollback_env, check=False)
            postgres_rollback = subprocess.run([*base, "--profile", "ops", "run", "--rm", "restore"], env=rollback_env, check=False)
            if runtime_rollback.returncode == 0 and seo_rollback.returncode == 0 and postgres_rollback.returncode == 0:
                _resume(base, operation_env)
            raise

        finalize_errors: list[str] = []
        finalize_env = {**prepare_env, "RESTORE_PHASE": "finalize"}
        for service, command in (
            ("restore", ()),
            ("runtime-restore", ("finalize",)),
            ("seo-agent-restore", ("finalize",)),
        ):
            try:
                _run(base, "--profile", "ops", "run", "--rm", service, *command, env=finalize_env)
            except Exception:
                finalize_errors.append(service)
        _resume(base, operation_env)
        if finalize_errors:
            raise RuntimeError(
                "Restore committed, but cleanup failed for: " + ", ".join(finalize_errors)
            )
    finally:
        subprocess.run([*base, "--profile", "ops", "run", "--rm", "backup-bundle", "cleanup"], env=operation_env, check=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Quiesced, encrypted VedicWay state backup and paired restore")
    parser.add_argument("action", choices=("backup", "restore"))
    parser.add_argument("--bundle", default="")
    parser.add_argument("--env-file", default=".env.production")
    parser.add_argument("--compose-file", default="compose.production.yml")
    args = parser.parse_args()
    base = ["docker", "compose", "--env-file", args.env_file, "-f", args.compose_file]
    env = _load_env(Path(args.env_file), os.environ.copy())
    if args.action == "backup":
        print(backup(base, env))
    else:
        restore(base, env, args.bundle)


if __name__ == "__main__":
    main()
