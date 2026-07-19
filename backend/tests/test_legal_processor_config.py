from __future__ import annotations

from pathlib import Path

import pytest

from vedicway_backend.content_store import ContentDatabase, production_configuration_errors
from vedicway_backend.legal_config import public_legal_config

PROCESSOR_VALUES = {
    "VEDICWAY_INTERPRETATION_PROCESSOR_NAME": "Example Processor LLC",
    "VEDICWAY_INTERPRETATION_PROCESSOR_ADDRESS": "123 Example Street, Dublin",
    "VEDICWAY_INTERPRETATION_PROCESSOR_COUNTRY": "Ирландия",
    "VEDICWAY_INTERPRETATION_PROCESSOR_PURPOSE": "подготовка персонализированного объяснения карты",
    "VEDICWAY_INTERPRETATION_PROCESSOR_DATA_CATEGORIES": (
        "расчётные астрологические показатели|связи между показателями"
    ),
    "VEDICWAY_INTERPRETATION_PROCESSOR_CROSS_BORDER": "1",
}


def _operator(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VEDICWAY_LEGAL_OPERATOR_NAME", "ООО ВедикВей")
    monkeypatch.setenv("VEDICWAY_LEGAL_OPERATOR_ADDRESS", "Москва, ул. Примерная, 1")
    monkeypatch.setenv("VEDICWAY_LEGAL_OPERATOR_INN", "7700000000")
    monkeypatch.setenv("VEDICWAY_LEGAL_OPERATOR_OGRN", "1000000000000")
    monkeypatch.setenv("VEDICWAY_PRIVACY_EMAIL", "privacy@example.ru")


def test_public_legal_config_names_the_actual_interpretation_processor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _operator(monkeypatch)
    monkeypatch.setenv("VEDICWAY_INTERPRETATION_PROVIDER", "codex")
    for name, value in PROCESSOR_VALUES.items():
        monkeypatch.setenv(name, value)

    config = public_legal_config()

    assert config["configured"] is True
    assert config["interpretation_processor_enabled"] is True
    assert config["interpretation_processor_name"] == "Example Processor LLC"
    assert config["interpretation_processor_country"] == "Ирландия"
    assert config["interpretation_processor_data_categories"] == [
        "расчётные астрологические показатели",
        "связи между показателями",
    ]
    assert config["interpretation_processor_cross_border"] is True
    assert config["versions"]["privacy"] == "2026-07-19-v2"
    assert config["versions"]["personal_data_consent"] == "2026-07-19-v2"


def test_codex_production_readiness_fails_closed_without_processor_disclosure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _operator(monkeypatch)
    monkeypatch.setenv("VEDICWAY_ENV", "production")
    monkeypatch.setenv("VEDICWAY_INTERPRETATION_PROVIDER", "codex")
    for name in PROCESSOR_VALUES:
        monkeypatch.delenv(name, raising=False)
    database = ContentDatabase(f"sqlite:///{(tmp_path / 'content.sqlite3').as_posix()}")

    errors = production_configuration_errors(database)

    assert "missing:VEDICWAY_INTERPRETATION_PROCESSOR_NAME" in errors
    assert "legal:interpretation_processor_configuration_required" in errors
    assert "invalid:VEDICWAY_INTERPRETATION_PROCESSOR_CROSS_BORDER" in errors
    assert public_legal_config()["configured"] is False


def test_codex_production_readiness_accepts_complete_processor_disclosure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _operator(monkeypatch)
    monkeypatch.setenv("VEDICWAY_ENV", "production")
    monkeypatch.setenv("VEDICWAY_INTERPRETATION_PROVIDER", "codex")
    for name, value in PROCESSOR_VALUES.items():
        monkeypatch.setenv(name, value)
    database = ContentDatabase(f"sqlite:///{(tmp_path / 'content.sqlite3').as_posix()}")

    errors = production_configuration_errors(database)

    assert not any("INTERPRETATION_PROCESSOR" in error for error in errors)
    assert "legal:interpretation_processor_configuration_required" not in errors


def test_codex_production_readiness_rejects_processor_placeholders(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _operator(monkeypatch)
    monkeypatch.setenv("VEDICWAY_ENV", "production")
    monkeypatch.setenv("VEDICWAY_INTERPRETATION_PROVIDER", "codex")
    for name, value in PROCESSOR_VALUES.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv(
        "VEDICWAY_INTERPRETATION_PROCESSOR_NAME", "REPLACE_WITH_PROCESSOR_LEGAL_NAME"
    )
    database = ContentDatabase(f"sqlite:///{(tmp_path / 'content.sqlite3').as_posix()}")

    errors = production_configuration_errors(database)

    assert "legal:interpretation_processor_configuration_required" in errors
    assert public_legal_config()["configured"] is False


def test_production_env_and_release_checker_require_processor_contract() -> None:
    root = Path(__file__).resolve().parents[2]
    production_env = (root / ".env.production.example").read_text(encoding="utf-8")
    release_checker = (root / "scripts" / "check_production_release.py").read_text(
        encoding="utf-8"
    )

    for name in PROCESSOR_VALUES:
        assert f"{name}=" in production_env
        assert f'"{name}"' in release_checker
    assert "VEDICWAY_INTERPRETATION_PROVIDER must equal codex" in release_checker
