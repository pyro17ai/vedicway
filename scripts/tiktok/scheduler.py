#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

JOBS = {
    "plan-queue": "plan-queue.txt",
    "publish-next": "publish-next.txt",
}
TIMEOUT_SECONDS = 4 * 60 * 60


def build_codex_command(*, root: Path, codex_bin: str, last_message: Path) -> list[str]:
    return [
        codex_bin,
        "exec",
        "--ephemeral",
        "--sandbox",
        "danger-full-access",
        "--cd",
        str(root),
        "--json",
        "--output-last-message",
        str(last_message),
        "-",
    ]


def _pid_is_live(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        still_active = 259
        error_access_denied = 5
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return ctypes.get_last_error() == error_access_denied
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return True
            return exit_code.value == still_active
        finally:
            kernel32.CloseHandle(handle)

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _acquire_lock(lock_path: Path) -> bool:
    for attempt in range(2):
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            try:
                owner = int(lock_path.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                owner = 0
            if owner and _pid_is_live(owner):
                return False
            if attempt == 0:
                lock_path.unlink(missing_ok=True)
                continue
            return False
        with os.fdopen(descriptor, "w", encoding="utf-8") as lock_file:
            lock_file.write(f"{os.getpid()}\n")
        return True
    return False


def run_job(
    job: str,
    *,
    root: Path,
    codex_bin: str,
    executor=subprocess.run,
    now: str | None = None,
) -> dict:
    if job not in JOBS:
        raise ValueError(f"Unknown TikTok scheduler job: {job}")

    root = root.resolve()
    runtime = root / "runtime" / "tiktok"
    if not (runtime / "SCHEDULER_ENABLED").is_file():
        return {"job": job, "status": "disabled"}

    runtime.mkdir(parents=True, exist_ok=True)
    lock_path = runtime / "scheduler.lock"
    if not _acquire_lock(lock_path):
        return {"job": job, "status": "busy"}

    scheduler_dir = runtime / "scheduler"
    log_dir = scheduler_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = now or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    log_path = log_dir / f"{stamp}-{job}.jsonl"
    last_message = scheduler_dir / f"{job}-last.md"
    prompt_path = root / "scripts" / "tiktok" / "prompts" / JOBS[job]
    prompt = prompt_path.read_text(encoding="utf-8")
    command = build_codex_command(root=root, codex_bin=codex_bin, last_message=last_message)
    environment = os.environ.copy()
    environment["PATH"] = os.pathsep.join(
        [str(Path.home() / ".local" / "bin"), environment.get("PATH", "")]
    )

    try:
        with log_path.open("w", encoding="utf-8", newline="\n") as log_file:
            completed = executor(
                command,
                input=prompt,
                text=True,
                cwd=str(root),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                timeout=TIMEOUT_SECONDS,
                env=environment,
                check=False,
            )
        status = "completed" if completed.returncode == 0 else "failed"
        return {
            "job": job,
            "status": status,
            "exit_code": completed.returncode,
            "log": str(log_path),
            "last_message": str(last_message),
        }
    finally:
        lock_path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one VedicWay TikTok Codex job")
    parser.add_argument("job", choices=sorted(JOBS))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--codex-bin", default=os.environ.get("CODEX_BIN", "codex"))
    args = parser.parse_args(argv)

    result = run_job(args.job, root=args.root, codex_bin=args.codex_bin)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] in {"completed", "disabled", "busy"} else 1


if __name__ == "__main__":
    sys.exit(main())
