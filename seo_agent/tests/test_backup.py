from __future__ import annotations

from pathlib import Path

import pytest

from seo_agent.backup import backup, restore
from seo_agent.db import AgentLedger, LedgerError, utc_now


def test_seo_backup_and_restore_round_trip(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "data"
    backups = tmp_path / "backups"
    monkeypatch.setenv("VEDICWAY_SEO_DATA_DIR", str(data))
    monkeypatch.setenv("VEDICWAY_SEO_DB", str(data / "vedicway_seo_agent.sqlite3"))
    ledger = AgentLedger()
    ledger.initialize()
    now = utc_now()
    with ledger.transaction(immediate=True) as connection:
        connection.execute("INSERT INTO keyword_clusters(id,slug,title,intent,status,created_at,updated_at) VALUES ('one','one','One','informational','ready',?,?)", (now, now))
    archive = backup(backups, "20260721T120000Z-test")
    with ledger.transaction(immediate=True) as connection:
        connection.execute("DELETE FROM keyword_clusters")
    restored = restore(backups, archive.name, "restore-seo-agent", "20260721T120000Z-test")
    assert restored == ledger.path
    with ledger.connect() as connection:
        assert connection.execute("SELECT slug FROM keyword_clusters").fetchone()[0] == "one"


def test_restore_requires_confirmation(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "data"
    backups = tmp_path / "backups"
    monkeypatch.setenv("VEDICWAY_SEO_DATA_DIR", str(data))
    monkeypatch.setenv("VEDICWAY_SEO_DB", str(data / "vedicway_seo_agent.sqlite3"))
    AgentLedger().initialize()
    archive = backup(backups, "20260721T120000Z-test")
    with pytest.raises(LedgerError, match="CONFIRM_SEO_RESTORE"):
        restore(backups, archive.name, "", "20260721T120000Z-test")
