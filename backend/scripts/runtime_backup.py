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


def backup(data_dir: Path, media_dir: Path, backup_dir: Path) -> Path:
    data_dir = _guard_runtime_target(data_dir, "data")
    media_dir = _guard_runtime_target(media_dir, "media")
    source_db = data_dir / "vedicway.sqlite3"
    if not source_db.is_file():
        raise SystemExit(f"SQLite database is missing: {source_db}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = backup_dir / f"vedicway-runtime-{timestamp}.tar.gz"
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


def restore(data_dir: Path, media_dir: Path, backup_dir: Path, filename: str, confirmation: str) -> None:
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
        for name in ("vedicway.sqlite3", "vedicway.sqlite3-wal", "vedicway.sqlite3-shm"):
            (data_dir / name).unlink(missing_ok=True)
        reports = data_dir / "reports"
        if reports.exists():
            shutil.rmtree(reports)
        for item in media_dir.iterdir():
            shutil.rmtree(item) if item.is_dir() else item.unlink()

        shutil.copy2(staged_db, data_dir / "vedicway.sqlite3")
        staged_reports = stage / "data" / "reports"
        if staged_reports.is_dir():
            shutil.copytree(staged_reports, reports)
        staged_media = stage / "media"
        if staged_media.is_dir():
            for item in staged_media.iterdir():
                destination = media_dir / item.name
                shutil.copytree(item, destination) if item.is_dir() else shutil.copy2(item, destination)

    print(f"Runtime restore completed: {filename}")


def main() -> None:
    parser = argparse.ArgumentParser(description="VedicWay SQLite/reports/media backup")
    parser.add_argument("action", choices=("backup", "restore"))
    parser.add_argument("--data-dir", type=Path, default=RUNTIME_ROOT / "data")
    parser.add_argument("--media-dir", type=Path, default=RUNTIME_ROOT / "media")
    parser.add_argument("--backup-dir", type=Path, default=Path("/backups"))
    parser.add_argument("--file", default=os.environ.get("RESTORE_RUNTIME_FILE", ""))
    parser.add_argument("--confirm", default=os.environ.get("CONFIRM_RUNTIME_RESTORE", ""))
    args = parser.parse_args()
    if args.action == "backup":
        backup(args.data_dir, args.media_dir, args.backup_dir)
    else:
        restore(args.data_dir, args.media_dir, args.backup_dir, args.file, args.confirm)


if __name__ == "__main__":
    main()
