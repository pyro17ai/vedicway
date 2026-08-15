from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "production_state.py"
SPEC = importlib.util.spec_from_file_location("production_state", MODULE_PATH)
assert SPEC and SPEC.loader
production_state = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(production_state)


def test_backup_quiesces_and_bundles_postgres_with_runtime_files(monkeypatch) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run(base, *args, env):
        calls.append(tuple(args))

    monkeypatch.setattr(production_state, "_run", fake_run)
    bundle = production_state.backup(
        ["docker", "compose"], {"VEDICWAY_SEO_AGENT_ENABLED": "1"}
    )
    assert bundle.startswith("vedicway-pair-")
    assert calls[0] == ("stop", "frontend", "backend", "worker", "email", "seo-agent")
    assert ("--profile", "ops", "run", "--rm", "backup") in calls
    assert ("--profile", "ops", "run", "--rm", "runtime-backup") in calls
    assert calls[-1] == (
        "--profile",
        "seo",
        "up",
        "-d",
        "frontend",
        "backend",
        "worker",
        "email",
        "seo-agent",
    )


def test_finalize_failure_keeps_committed_restore_and_resumes_services(monkeypatch) -> None:
    calls: list[tuple[str, ...]] = []
    raw_calls: list[tuple[str, ...]] = []

    def fake_run(base, *args, env):
        call = tuple(args)
        calls.append(call)
        if call[-2:] == ("runtime-restore", "finalize"):
            raise subprocess.CalledProcessError(1, [*base, *args])

    def fake_subprocess_run(command, **kwargs):
        raw_calls.append(tuple(command))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(production_state, "_run", fake_run)
    monkeypatch.setattr(production_state.subprocess, "run", fake_subprocess_run)
    with pytest.raises(RuntimeError, match="Restore committed, but cleanup failed"):
        production_state.restore(
            ["docker", "compose"],
            {"VEDICWAY_SEO_AGENT_ENABLED": "1", "POSTGRES_DB": "vedicway"},
            "vedicway-pair-20260721T120000Z-deadbeef.vwb",
        )
    assert not any(call[-1:] == ("rollback",) for call in raw_calls)
    assert any(call[-2:] == ("runtime-restore", "finalize") for call in calls)
    assert any(call[:4] == ("--profile", "seo", "up", "-d") for call in calls)
