import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "tiktok" / "scheduler.py"


def load_scheduler():
    spec = importlib.util.spec_from_file_location("tiktok_scheduler", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_job_root(tmp_path: Path) -> Path:
    prompt_dir = tmp_path / "scripts" / "tiktok" / "prompts"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "plan-queue.txt").write_text(
        "Используй $vedicway-tiktok-carousel в режиме plan-queue.\n",
        encoding="utf-8",
    )
    (prompt_dir / "publish-next.txt").write_text(
        "Используй $vedicway-tiktok-carousel, $imagegen и $playwright-cli.\n",
        encoding="utf-8",
    )
    return tmp_path


def test_build_codex_command_uses_prompt_stdin_and_an_isolated_noninteractive_run(tmp_path):
    scheduler = load_scheduler()
    root = make_job_root(tmp_path)

    command = scheduler.build_codex_command(
        root=root,
        codex_bin="/home/ubuntu/.local/bin/codex",
        last_message=root / "runtime" / "tiktok" / "scheduler" / "plan-last.md",
    )

    assert command == [
        "/home/ubuntu/.local/bin/codex",
        "exec",
        "--ephemeral",
        "--sandbox",
        "danger-full-access",
        "--cd",
        str(root),
        "--json",
        "--output-last-message",
        str(root / "runtime" / "tiktok" / "scheduler" / "plan-last.md"),
        "-",
    ]


def test_run_job_stays_inert_until_scheduler_is_enabled(tmp_path):
    scheduler = load_scheduler()
    root = make_job_root(tmp_path)

    def must_not_run(*_args, **_kwargs):
        raise AssertionError("codex must not run before the enable sentinel exists")

    result = scheduler.run_job(
        "publish-next",
        root=root,
        codex_bin="codex",
        executor=must_not_run,
    )

    assert result == {"job": "publish-next", "status": "disabled"}


def test_run_job_streams_the_selected_prompt_to_codex_and_keeps_a_log(tmp_path):
    scheduler = load_scheduler()
    root = make_job_root(tmp_path)
    enable = root / "runtime" / "tiktok" / "SCHEDULER_ENABLED"
    enable.parent.mkdir(parents=True)
    enable.write_text("enabled\n", encoding="utf-8")
    observed = {}

    def fake_executor(command, **kwargs):
        observed["command"] = command
        observed["input"] = kwargs["input"]
        observed["cwd"] = kwargs["cwd"]
        kwargs["stdout"].write('{"type":"turn.completed"}\n')
        return subprocess.CompletedProcess(command, 0)

    result = scheduler.run_job(
        "plan-queue",
        root=root,
        codex_bin="codex",
        executor=fake_executor,
        now="20260824T090000Z",
    )

    assert result["status"] == "completed"
    assert observed["input"] == "Используй $vedicway-tiktok-carousel в режиме plan-queue.\n"
    assert observed["cwd"] == str(root)
    assert Path(result["log"]).read_text(encoding="utf-8") == '{"type":"turn.completed"}\n'


def test_run_job_refuses_a_second_process_while_the_global_lock_is_live(tmp_path):
    scheduler = load_scheduler()
    root = make_job_root(tmp_path)
    runtime = root / "runtime" / "tiktok"
    runtime.mkdir(parents=True)
    (runtime / "SCHEDULER_ENABLED").write_text("enabled\n", encoding="utf-8")
    (runtime / "scheduler.lock").write_text(f"{os.getpid()}\n", encoding="utf-8")

    result = scheduler.run_job("plan-queue", root=root, codex_bin="codex")

    assert result == {"job": "plan-queue", "status": "busy"}


def test_pid_liveness_check_does_not_terminate_the_caller_on_windows():
    if os.name != "nt":
        return

    script = """
import importlib.util
import os
import sys

spec = importlib.util.spec_from_file_location("tiktok_scheduler", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(module._pid_is_live(os.getpid()))
print("survived")
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(MODULE_PATH)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stdout.splitlines() == ["True", "survived"]


def test_unknown_job_is_rejected_before_any_files_are_changed(tmp_path):
    scheduler = load_scheduler()
    root = make_job_root(tmp_path)

    try:
        scheduler.run_job("delete-everything", root=root, codex_bin="codex")
    except ValueError as error:
        assert str(error) == "Unknown TikTok scheduler job: delete-everything"
    else:
        raise AssertionError("unknown jobs must be rejected")

    assert not (root / "runtime").exists()
