from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "runtime_backup.py"
SPEC = importlib.util.spec_from_file_location("vedicway_runtime_backup", SCRIPT)
assert SPEC and SPEC.loader
runtime_backup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime_backup)


def test_runtime_backup_and_restore_round_trip(tmp_path, monkeypatch) -> None:
    root = tmp_path.resolve()
    data = root / "data"
    media = root / "media"
    backups = root / "backups"
    data.mkdir()
    media.mkdir()
    monkeypatch.setattr(runtime_backup, "RUNTIME_ROOT", root)

    (data / "reports").mkdir()
    (data / "reports" / "report.pdf").write_bytes(b"pdf")
    (media / "cover.webp").write_bytes(b"image")

    archive = runtime_backup.backup(data, media, backups)

    (data / "reports" / "report.pdf").write_bytes(b"changed-pdf")
    (media / "cover.webp").write_bytes(b"changed")
    runtime_backup.restore(data, media, backups, archive.name, "restore-runtime")

    assert (media / "cover.webp").read_bytes() == b"image"
    assert (data / "reports" / "report.pdf").read_bytes() == b"pdf"
