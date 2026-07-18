from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

PYJHORA_SOURCE = Path(os.environ.get("VEDICWAY_PYJHORA_SOURCE", r"C:\Users\Grisha\Documents\Codex\2026-07-08\pyjhora-mcp\src"))
if PYJHORA_SOURCE.exists():
    os.environ.setdefault("VEDICWAY_PYJHORA_SOURCE", str(PYJHORA_SOURCE))


@pytest.fixture(autouse=True)
def test_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("VEDICWAY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("VEDICWAY_TEST_PAYMENTS", "1")
    monkeypatch.setenv("VEDICWAY_INTERPRETATION_PROVIDER", "stub")
    if PYJHORA_SOURCE.exists():
        monkeypatch.setenv("VEDICWAY_PYJHORA_SOURCE", str(PYJHORA_SOURCE))
