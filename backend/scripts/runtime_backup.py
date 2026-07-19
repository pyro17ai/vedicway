from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import tarfile
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

RUNTIME_ROOT = Path("/var/lib/vedicway")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _guard_runtime_target(path: Path, expected_name: str) -> Path:
    resolved = path.resolve()
    if resolved.name != expected_name or resolved.parent != RUNTIME_ROOT:
        raise SystemExit(f"Refusing unsafe runtime target: {resolved}")
    return resolved


def backup(data_dir: Path, media_dir: Path, backup_dir: Path, backup_set_id: str | None = None) -> Path:
    data_dir = _guard_runtime_target(data_dir, "data")
    media_dir = _guard_runtime_target(media_dir, "media")
    source_db = data_dir / "vedicway.sqlite3"
    if not source_db.is_file():
        raise SystemExit(f"SQLite database is missing: {source_db}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_set_id = backup_set_id or os.environ.get("BACKUP_SET_ID") or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    if not backup_set_id.replace("-", "").replace("_", "").replace(".", "").isalnum():
        raise SystemExit("Invalid BACKUP_SET_ID")
    target = backup_dir / f"vedicway-runtime-{backup_set_id}.tar.gz"
    temporary_target = target.with_suffix(target.suffix + ".tmp")

    with tempfile.TemporaryDirectory(prefix="vedicway-runtime-") as temporary:
        stage = Path(temporary)
        staged_db = stage / "vedicway.sqlite3"
        with closing(sqlite3.connect(f"file:{source_db.as_posix()}?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(staged_db)) as destination:
                source.backup(destination)
                result = destination.execute("PRAGMA integrity_check").fetchone()
                if not result or result[0] != "ok":
                    raise SystemExit("SQLite integrity_check failed during backup")

        manifest = {
            "backup_set_id": backup_set_id,
            "created_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "database": "data/vedicway.sqlite3",
            "database_sha256": _sha256(staged_db),
            "reports_included": (data_dir / "reports").is_dir(),
            "media_included": media_dir.is_dir(),
        }
        (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        with tarfile.open(temporary_target, "w:gz", compresslevel=9) as archive:
            archive.add(stage / "manifest.json", arcname="manifest.json")
            archive.add(staged_db, arcname="data/vedicway.sqlite3")
            reports = data_dir / "reports"
            if reports.is_dir():
                archive.add(reports, arcname="data/reports", recursive=True)
            if media_dir.is_dir():
                archive.add(media_dir, arcname="media", recursive=True)

    os.replace(temporary_target, target)
    checksum = target.with_suffix(target.suffix + ".sha256")
    checksum.write_text(f"{_sha256(target)}  {target.name}\n", encoding="ascii")
    os.chmod(target, 0o600)
    os.chmod(checksum, 0o600)
    print(target)
    return target


def _safe_extract(archive: tarfile.TarFile, target: Path) -> None:
    for member in archive.getmembers():
        if member.issym() or member.islnk() or member.isdev():
            raise SystemExit(f"Unsafe archive member: {member.name}")
        destination = (target / member.name).resolve()
        if target.resolve() not in destination.parents and destination != target.resolve():
            raise SystemExit(f"Archive path escapes target: {member.name}")
    archive.extractall(target)


def _restore_paths(data_dir: Path, media_dir: Path, pair_id: str) -> tuple[Path, Path, Path, Path, Path]:
    if not pair_id or not pair_id.replace("-", "").replace("_", "").replace(".", "").isalnum():
        raise SystemExit("RESTORE_SET_ID is invalid")
    return (
        data_dir / f".restore-stage-{pair_id}",
        data_dir / f".restore-previous-{pair_id}",
        media_dir / f".restore-stage-{pair_id}",
        media_dir / f".restore-previous-{pair_id}",
        data_dir / f".restore-state-{pair_id}.json",
    )


def prepare_restore(
    data_dir: Path,
    media_dir: Path,
    backup_dir: Path,
    filename: str,
    confirmation: str,
    pair_id: str,
) -> None:
    data_dir = _guard_runtime_target(data_dir, "data")
    media_dir = _guard_runtime_target(media_dir, "media")
    if confirmation != "restore-runtime":
        raise SystemExit("Set CONFIRM_RUNTIME_RESTORE=restore-runtime")
    if not filename or Path(filename).name != filename:
        raise SystemExit("RESTORE_RUNTIME_FILE must be a plain file name")

    source = (backup_dir / filename).resolve()
    if source.parent != backup_dir.resolve() or not source.is_file():
        raise SystemExit(f"Runtime backup is missing: {source}")
    checksum_path = source.with_suffix(source.suffix + ".sha256")
    if not checksum_path.is_file():
        raise SystemExit(f"Runtime backup checksum is missing: {checksum_path}")
    expected = checksum_path.read_text(encoding="ascii").split()[0]
    if expected != _sha256(source):
        raise SystemExit("Runtime backup checksum mismatch")

    with tempfile.TemporaryDirectory(prefix="vedicway-restore-") as temporary:
        stage = Path(temporary)
        with tarfile.open(source, "r:gz") as archive:
            _safe_extract(archive, stage)
        staged_db = stage / "data" / "vedicway.sqlite3"
        manifest = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
        if not staged_db.is_file() or manifest.get("database_sha256") != _sha256(staged_db):
            raise SystemExit("Runtime backup database failed manifest validation")
        with closing(sqlite3.connect(f"file:{staged_db.as_posix()}?mode=ro", uri=True)) as connection:
            result = connection.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise SystemExit("SQLite integrity_check failed before restore")

        data_dir.mkdir(parents=True, exist_ok=True)
        media_dir.mkdir(parents=True, exist_ok=True)
        stage_data, previous_data, stage_media, previous_media, state_path = _restore_paths(data_dir, media_dir, pair_id)
        if any(path.exists() for path in (stage_data, previous_data, stage_media, previous_media, state_path)):
            raise SystemExit("Runtime restore staging already exists; rollback or finalize it first")
        stage_data.mkdir()
        stage_media.mkdir()
        shutil.copy2(staged_db, stage_data / "vedicway.sqlite3")
        staged_reports = stage / "data" / "reports"
        if staged_reports.is_dir():
            shutil.copytree(staged_reports, stage_data / "reports")
        staged_media = stage / "media"
        if staged_media.is_dir():
            for item in staged_media.iterdir():
                destination = stage_media / item.name
                shutil.copytree(item, destination) if item.is_dir() else shutil.copy2(item, destination)

        state = {
            "pair_id": pair_id,
            "phase": "prepared",
            "original_data": [name for name in ("vedicway.sqlite3", "vedicway.sqlite3-wal", "vedicway.sqlite3-shm", "reports") if (data_dir / name).exists()],
            "new_data": [item.name for item in stage_data.iterdir()],
            "original_media": [item.name for item in media_dir.iterdir() if not item.name.startswith(".restore-")],
            "new_media": [item.name for item in stage_media.iterdir()],
        }
        state_path.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")

    print(f"Runtime restore prepared: {filename} ({pair_id})")


def commit_restore(data_dir: Path, media_dir: Path, pair_id: str, confirmation: str) -> None:
    data_dir = _guard_runtime_target(data_dir, "data")
    media_dir = _guard_runtime_target(media_dir, "media")
    if confirmation != "restore-runtime":
        raise SystemExit("Set CONFIRM_RUNTIME_RESTORE=restore-runtime")
    stage_data, previous_data, stage_media, previous_media, state_path = _restore_paths(data_dir, media_dir, pair_id)
    if not state_path.is_file() or not stage_data.is_dir() or not stage_media.is_dir():
        raise SystemExit("Prepared runtime restore is missing")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    previous_data.mkdir()
    previous_media.mkdir()
    try:
        for name in state["original_data"]:
            os.replace(data_dir / name, previous_data / name)
        for name in state["original_media"]:
            os.replace(media_dir / name, previous_media / name)
        for name in state["new_data"]:
            os.replace(stage_data / name, data_dir / name)
        for name in state["new_media"]:
            os.replace(stage_media / name, media_dir / name)
        state["phase"] = "committed"
        state_path.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
    except Exception:
        rollback_restore(data_dir, media_dir, pair_id, confirmation)
        raise


def rollback_restore(data_dir: Path, media_dir: Path, pair_id: str, confirmation: str) -> None:
    data_dir = _guard_runtime_target(data_dir, "data")
    media_dir = _guard_runtime_target(media_dir, "media")
    if confirmation != "restore-runtime":
        raise SystemExit("Set CONFIRM_RUNTIME_RESTORE=restore-runtime")
    stage_data, previous_data, stage_media, previous_media, state_path = _restore_paths(data_dir, media_dir, pair_id)
    if not state_path.is_file():
        return
    state = json.loads(state_path.read_text(encoding="utf-8"))
    for name in state["new_data"]:
        target = data_dir / name
        replaces_original = name in state["original_data"]
        if target.exists() and (not replaces_original or (previous_data / name).exists()):
            shutil.rmtree(target) if target.is_dir() else target.unlink()
    for name in state["new_media"]:
        target = media_dir / name
        replaces_original = name in state["original_media"]
        if target.exists() and (not replaces_original or (previous_media / name).exists()):
            shutil.rmtree(target) if target.is_dir() else target.unlink()
    if previous_data.is_dir():
        for item in list(previous_data.iterdir()):
            os.replace(item, data_dir / item.name)
    if previous_media.is_dir():
        for item in list(previous_media.iterdir()):
            os.replace(item, media_dir / item.name)
    for path in (stage_data, previous_data, stage_media, previous_media):
        shutil.rmtree(path, ignore_errors=True)
    state_path.unlink(missing_ok=True)


def finalize_restore(data_dir: Path, media_dir: Path, pair_id: str, confirmation: str) -> None:
    data_dir = _guard_runtime_target(data_dir, "data")
    media_dir = _guard_runtime_target(media_dir, "media")
    if confirmation != "restore-runtime":
        raise SystemExit("Set CONFIRM_RUNTIME_RESTORE=restore-runtime")
    stage_data, previous_data, stage_media, previous_media, state_path = _restore_paths(data_dir, media_dir, pair_id)
    for path in (stage_data, previous_data, stage_media, previous_media):
        shutil.rmtree(path, ignore_errors=True)
    state_path.unlink(missing_ok=True)


def restore(data_dir: Path, media_dir: Path, backup_dir: Path, filename: str, confirmation: str) -> None:
    source = backup_dir / filename
    with tarfile.open(source, "r:gz") as archive:
        manifest_file = archive.extractfile("manifest.json")
        if manifest_file is None:
            raise SystemExit("Runtime manifest is missing")
        pair_id = str(json.load(manifest_file).get("backup_set_id") or "legacy-restore")
    prepare_restore(data_dir, media_dir, backup_dir, filename, confirmation, pair_id)
    try:
        commit_restore(data_dir, media_dir, pair_id, confirmation)
    except Exception:
        rollback_restore(data_dir, media_dir, pair_id, confirmation)
        raise
    finalize_restore(data_dir, media_dir, pair_id, confirmation)

    print(f"Runtime restore completed: {filename}")


def main() -> None:
    parser = argparse.ArgumentParser(description="VedicWay SQLite/reports/media backup")
    parser.add_argument("action", choices=("backup", "restore", "prepare", "commit", "rollback", "finalize"))
    parser.add_argument("--data-dir", type=Path, default=RUNTIME_ROOT / "data")
    parser.add_argument("--media-dir", type=Path, default=RUNTIME_ROOT / "media")
    parser.add_argument("--backup-dir", type=Path, default=Path(os.environ.get("BACKUP_DIR", "/backups")))
    parser.add_argument("--file", default=os.environ.get("RESTORE_RUNTIME_FILE", ""))
    parser.add_argument("--confirm", default=os.environ.get("CONFIRM_RUNTIME_RESTORE", ""))
    parser.add_argument("--pair-id", default=os.environ.get("RESTORE_SET_ID", ""))
    args = parser.parse_args()
    if args.action == "backup":
        backup(args.data_dir, args.media_dir, args.backup_dir, os.environ.get("BACKUP_SET_ID"))
    elif args.action == "restore":
        restore(args.data_dir, args.media_dir, args.backup_dir, args.file, args.confirm)
    elif args.action == "prepare":
        prepare_restore(args.data_dir, args.media_dir, args.backup_dir, args.file, args.confirm, args.pair_id)
    elif args.action == "commit":
        commit_restore(args.data_dir, args.media_dir, args.pair_id, args.confirm)
    elif args.action == "rollback":
        rollback_restore(args.data_dir, args.media_dir, args.pair_id, args.confirm)
    else:
        finalize_restore(args.data_dir, args.media_dir, args.pair_id, args.confirm)


if __name__ == "__main__":
    main()
