from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from .db import AgentLedger, LedgerError

SET_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{7,63}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup(backup_dir: Path, set_id: str | None = None) -> Path:
    ledger = AgentLedger()
    ledger.initialize()
    resolved_id = set_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    if not SET_ID.fullmatch(resolved_id):
        raise LedgerError("Invalid BACKUP_SET_ID")
    target_dir = backup_dir.expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"vedicway-seo-{resolved_id}.sqlite3"
    ledger.backup(target)
    with closing(sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True)) as connection:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            target.unlink(missing_ok=True)
            raise LedgerError("SEO backup integrity_check failed")
    sidecar = target.with_suffix(target.suffix + ".sha256")
    sidecar.write_text(f"{_sha256(target)}  {target.name}\n", encoding="ascii")
    if os.name == "posix":
        os.chmod(target, 0o600)
        os.chmod(sidecar, 0o600)
    return target


def _restore_paths(ledger: AgentLedger, set_id: str) -> tuple[Path, Path, Path]:
    if not SET_ID.fullmatch(set_id):
        raise LedgerError("Invalid RESTORE_SET_ID")
    return (
        ledger.data_dir / f".restore-stage-{set_id}.sqlite3",
        ledger.data_dir / f".restore-previous-{set_id}",
        ledger.data_dir / f".restore-state-{set_id}.json",
    )


def prepare_restore(backup_dir: Path, filename: str, confirmation: str, set_id: str) -> Path:
    if confirmation != "restore-seo-agent":
        raise LedgerError("Set CONFIRM_SEO_RESTORE=restore-seo-agent")
    source = (backup_dir.expanduser().resolve() / filename).resolve()
    if source.parent != backup_dir.expanduser().resolve() or not source.is_file():
        raise LedgerError("RESTORE_SEO_FILE must be a file directly inside BACKUP_DIR")
    sidecar = source.with_suffix(source.suffix + ".sha256")
    if not sidecar.is_file() or sidecar.read_text(encoding="ascii").split()[0] != _sha256(source):
        raise LedgerError("SEO backup checksum failed")
    with closing(sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)) as connection:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise LedgerError("SEO backup integrity_check failed")
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'").fetchone():
            raise LedgerError("SEO backup schema is missing")
    ledger = AgentLedger()
    ledger.data_dir.mkdir(parents=True, exist_ok=True)
    stage, previous, state_path = _restore_paths(ledger, set_id)
    if stage.exists() or previous.exists() or state_path.exists():
        raise LedgerError("SEO restore staging already exists")
    shutil.copy2(source, stage)
    state = {
        "set_id": set_id,
        "phase": "prepared",
        "database_name": ledger.path.name,
        "original_files": [
            path.name
            for path in (ledger.path, Path(f"{ledger.path}-wal"), Path(f"{ledger.path}-shm"))
            if path.exists()
        ],
    }
    state_path.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
    return stage


def commit_restore(confirmation: str, set_id: str) -> Path:
    if confirmation != "restore-seo-agent":
        raise LedgerError("Set CONFIRM_SEO_RESTORE=restore-seo-agent")
    ledger = AgentLedger()
    stage, previous, state_path = _restore_paths(ledger, set_id)
    if not stage.is_file() or not state_path.is_file() or previous.exists():
        raise LedgerError("Prepared SEO restore is missing or already committed")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    previous.mkdir()
    try:
        for name in state["original_files"]:
            os.replace(ledger.data_dir / name, previous / name)
        os.replace(stage, ledger.path)
        ledger.health()
        state["phase"] = "committed"
        state_path.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
    except Exception:
        rollback_restore(confirmation, set_id)
        raise
    return ledger.path


def rollback_restore(confirmation: str, set_id: str) -> None:
    if confirmation != "restore-seo-agent":
        raise LedgerError("Set CONFIRM_SEO_RESTORE=restore-seo-agent")
    ledger = AgentLedger()
    stage, previous, state_path = _restore_paths(ledger, set_id)
    if not state_path.is_file():
        return
    state = json.loads(state_path.read_text(encoding="utf-8"))
    for path in (ledger.path, Path(f"{ledger.path}-wal"), Path(f"{ledger.path}-shm")):
        if path.exists() and (path.name not in state["original_files"] or (previous / path.name).exists()):
            path.unlink()
    if previous.is_dir():
        for item in previous.iterdir():
            os.replace(item, ledger.data_dir / item.name)
    stage.unlink(missing_ok=True)
    shutil.rmtree(previous, ignore_errors=True)
    state_path.unlink(missing_ok=True)


def finalize_restore(confirmation: str, set_id: str) -> None:
    if confirmation != "restore-seo-agent":
        raise LedgerError("Set CONFIRM_SEO_RESTORE=restore-seo-agent")
    ledger = AgentLedger()
    stage, previous, state_path = _restore_paths(ledger, set_id)
    stage.unlink(missing_ok=True)
    shutil.rmtree(previous, ignore_errors=True)
    state_path.unlink(missing_ok=True)


def restore(backup_dir: Path, filename: str, confirmation: str, set_id: str) -> Path:
    prepare_restore(backup_dir, filename, confirmation, set_id)
    try:
        result = commit_restore(confirmation, set_id)
    except Exception:
        rollback_restore(confirmation, set_id)
        raise
    finalize_restore(confirmation, set_id)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup or restore the isolated VedicWay SEO ledger")
    parser.add_argument("action", choices=("backup", "restore", "prepare", "commit", "rollback", "finalize"))
    parser.add_argument("--backup-dir", type=Path, default=Path(os.environ.get("BACKUP_DIR", "/backups")))
    parser.add_argument("--file", default=os.environ.get("RESTORE_SEO_FILE", ""))
    parser.add_argument("--set-id", default=os.environ.get("RESTORE_SET_ID") or os.environ.get("BACKUP_SET_ID", ""))
    parser.add_argument("--confirm", default=os.environ.get("CONFIRM_SEO_RESTORE", ""))
    args = parser.parse_args()
    try:
        if args.action == "backup":
            path = backup(args.backup_dir, args.set_id or None)
        elif args.action == "restore":
            path = restore(args.backup_dir, args.file, args.confirm, args.set_id)
        elif args.action == "prepare":
            path = prepare_restore(args.backup_dir, args.file, args.confirm, args.set_id)
        elif args.action == "commit":
            path = commit_restore(args.confirm, args.set_id)
        elif args.action == "rollback":
            rollback_restore(args.confirm, args.set_id)
            path = AgentLedger().path
        else:
            finalize_restore(args.confirm, args.set_id)
            path = AgentLedger().path
        checksum = _sha256(path) if path.is_file() else None
        print(json.dumps({"status": "ok", "path": str(path), "sha256": checksum}, sort_keys=True))
        return 0
    except (LedgerError, OSError, sqlite3.Error) as error:
        print(json.dumps({"status": "error", "error": str(error)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
