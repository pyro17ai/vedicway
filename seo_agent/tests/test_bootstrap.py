from __future__ import annotations

from pathlib import Path

from seo_agent.bootstrap import bootstrap
from seo_agent.db import AgentLedger


def test_tracked_yandex_seed_bootstrap_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "data"
    monkeypatch.setenv("VEDICWAY_SEO_DATA_DIR", str(data))
    monkeypatch.setenv("VEDICWAY_SEO_DB", str(data / "vedicway_seo_agent.sqlite3"))
    root = Path(__file__).resolve().parents[2]
    first = bootstrap(root)
    second = bootstrap(root)
    assert first["queries"] >= 16
    assert len(first["ready_clusters"]) == 2
    assert second["ready_clusters"] == first["ready_clusters"]
    summary = AgentLedger().summary()
    assert summary["counts"]["keyword_queries"] == first["queries"]
    assert summary["counts"]["keyword_clusters"] == 2
