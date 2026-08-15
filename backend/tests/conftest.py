from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

PYJHORA_SOURCE = Path(os.environ.get("VEDICWAY_PYJHORA_SOURCE", r"C:\Users\Huawei\.codex\mcp\pyjhora-mcp\src"))
if PYJHORA_SOURCE.exists():
    os.environ.setdefault("VEDICWAY_PYJHORA_SOURCE", str(PYJHORA_SOURCE))


@pytest.fixture(autouse=True)
def test_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.fail("TEST_DATABASE_URL is required for PostgreSQL tests")
    if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        pytest.fail("TEST_DATABASE_URL must use PostgreSQL")
    dsn = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(
            """TRUNCATE TABLE
                 runtime.email_deliveries,
                 runtime.retention_runs,
                 runtime.erasure_tombstones,
                 runtime.privacy_requests,
                 runtime.magic_link_confirmations,
                 runtime.magic_links,
                 runtime.saved_questions,
                 runtime.rate_limit_events,
                 runtime.pdf_render_requests,
                 runtime.reports,
                 runtime.payment_operations,
                 runtime.refunds,
                 runtime.rectifications,
                 runtime.entitlements,
                 runtime.payment_incidents,
                 runtime.payment_events,
                 runtime.purchases,
                 runtime.agent_runs,
                 runtime.outbox_events,
                 runtime.jobs,
                 runtime.chart_access,
                 runtime.charts,
                 runtime.birth_profiles,
                 runtime.anonymous_sessions
               RESTART IDENTITY CASCADE"""
        )
        connection.execute(
            """TRUNCATE TABLE
                 public.article_comments,
                 public.consent_records,
                 public.articles,
                 public.media_assets
               RESTART IDENTITY CASCADE"""
        )
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("VEDICWAY_DATABASE_URL", database_url)
    monkeypatch.setenv("VEDICWAY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("VEDICWAY_TEST_PAYMENTS", "1")
    monkeypatch.setenv("VEDICWAY_INTERPRETATION_PROVIDER", "stub")
    if PYJHORA_SOURCE.exists():
        monkeypatch.setenv("VEDICWAY_PYJHORA_SOURCE", str(PYJHORA_SOURCE))
    yield
