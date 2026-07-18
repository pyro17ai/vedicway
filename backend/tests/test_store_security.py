from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from vedicway_backend.store import Store


def _production_data_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VEDICWAY_ENV", "production")
    monkeypatch.setenv("VEDICWAY_DATA_KEY", Fernet.generate_key().decode("ascii"))
    monkeypatch.delenv("VEDICWAY_SIGNING_KEY", raising=False)


def test_production_store_requires_signing_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _production_data_key(monkeypatch)

    with pytest.raises(RuntimeError, match="VEDICWAY_SIGNING_KEY is required"):
        Store(tmp_path / "runtime")


def test_production_store_rejects_short_signing_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _production_data_key(monkeypatch)
    monkeypatch.setenv("VEDICWAY_SIGNING_KEY", "too-short")

    with pytest.raises(RuntimeError, match="at least 32 bytes"):
        Store(tmp_path / "runtime")
