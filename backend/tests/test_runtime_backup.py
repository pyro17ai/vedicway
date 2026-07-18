from __future__ import annotations

import importlib.util
import sqlite3
from contextlib import closing
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

    with closing(sqlite3.connect(data / "vedicway.sqlite3")) as connection:
        connection.execute("CREATE TABLE smoke(value text)")
        connection.execute("INSERT INTO smoke VALUES ('before')")
        connection.commit()
    (data / "reports").mkdir()
    (data / "reports" / "report.pdf").write_bytes(b"pdf")
    (media / "cover.webp").write_bytes(b"image")

    archive = runtime_backup.backup(data, media, backups)

    with closing(sqlite3.connect(data / "vedicway.sqlite3")) as connection:
        connection.execute("UPDATE smoke SET value='after'")
        connection.commit()
    (media / "cover.webp").write_bytes(b"changed")
    runtime_backup.restore(data, media, backups, archive.name, "restore-runtime")

    with closing(sqlite3.connect(data / "vedicway.sqlite3")) as connection:
        assert connection.execute("SELECT value FROM smoke").fetchone()[0] == "before"
    assert (media / "cover.webp").read_bytes() == b"image"
    assert (data / "reports" / "report.pdf").read_bytes() == b"pdf"
