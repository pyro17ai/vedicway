from __future__ import annotations

import os

import psycopg
import pytest


@pytest.fixture(autouse=True)
def postgres_ledger(monkeypatch: pytest.MonkeyPatch, tmp_path):
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.fail("TEST_DATABASE_URL is required for PostgreSQL tests")
    if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        pytest.fail("TEST_DATABASE_URL must use PostgreSQL")
    dsn = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS seo_agent CASCADE")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("VEDICWAY_DATABASE_URL", database_url)
    monkeypatch.setenv("VEDICWAY_SEO_DATA_DIR", str(tmp_path / "seo-agent"))
    yield
