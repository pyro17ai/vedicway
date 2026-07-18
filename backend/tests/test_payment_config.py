from __future__ import annotations

import pytest

from vedicway_backend.payment_config import (
    OFFICIAL_YOOKASSA_API_BASE_URL,
    PaymentConfigurationError,
    PaymentSettings,
)

PAYMENT_ENV_KEYS = (
    "VEDICWAY_ENV",
    "VEDICWAY_TEST_PAYMENTS",
    "VEDICWAY_PAYMENT_PROVIDER",
    "VEDICWAY_PUBLIC_BASE_URL",
    "VEDICWAY_OFFER_VERSION",
    "VEDICWAY_OFFER_URL",
    "VEDICWAY_PRIVACY_URL",
    "VEDICWAY_OPERATIONS_TOKEN",
    "VEDICWAY_TRUSTED_PROXY_CIDRS",
    "VEDICWAY_OPERATIONS_CIDRS",
    "YOOKASSA_SHOP_ID",
    "YOOKASSA_SECRET_KEY",
    "YOOKASSA_VAT_CODE",
    "YOOKASSA_TAX_SYSTEM_CODE",
    "YOOKASSA_API_BASE_URL",
)


def _clear(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in PAYMENT_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _production(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    values = {
        "VEDICWAY_ENV": "production",
        "VEDICWAY_PAYMENT_PROVIDER": "yookassa",
        "VEDICWAY_PUBLIC_BASE_URL": "https://vedicway.example",
        "VEDICWAY_OFFER_VERSION": "2026-07-18",
        "VEDICWAY_OFFER_URL": "https://vedicway.example/legal/offer",
        "VEDICWAY_PRIVACY_URL": "https://vedicway.example/legal/privacy",
        "VEDICWAY_OPERATIONS_TOKEN": "ops_" + "x" * 48,
        "VEDICWAY_TRUSTED_PROXY_CIDRS": "10.0.0.0/8,2001:db8::/32",
        "VEDICWAY_OPERATIONS_CIDRS": "10.10.0.0/16,127.0.0.1/32",
        "YOOKASSA_SHOP_ID": "123456",
        "YOOKASSA_SECRET_KEY": "live_" + "s" * 48,
        "YOOKASSA_VAT_CODE": "11",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_development_defaults_to_disabled_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)

    settings = PaymentSettings.from_environment()

    assert settings.environment == "development"
    assert settings.provider == "disabled"
    assert settings.catalog.full_report.amount_minor == 99_000
    assert settings.catalog.full_report.currency == "RUB"
    assert settings.api_base_url == OFFICIAL_YOOKASSA_API_BASE_URL


def test_test_provider_requires_explicit_non_production_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("VEDICWAY_TEST_PAYMENTS", "1")

    settings = PaymentSettings.from_environment()

    assert settings.provider == "test"
    assert settings.receipts_enabled is False


def test_complete_yookassa_production_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    _production(monkeypatch)
    monkeypatch.setenv("YOOKASSA_TAX_SYSTEM_CODE", "2")

    settings = PaymentSettings.from_environment()

    assert settings.provider == "yookassa"
    assert settings.shop_id == "123456"
    assert settings.secret_key is not None
    assert settings.vat_code == 11
    assert settings.tax_system_code == 2
    assert settings.public_base_url == "https://vedicway.example"
    assert [str(network) for network in settings.trusted_proxy_networks] == ["10.0.0.0/8", "2001:db8::/32"]
    assert [str(network) for network in settings.operations_networks] == ["10.10.0.0/16", "127.0.0.1/32"]


@pytest.mark.parametrize(
    "missing",
    [
        "YOOKASSA_SHOP_ID",
        "YOOKASSA_SECRET_KEY",
        "YOOKASSA_VAT_CODE",
        "VEDICWAY_PUBLIC_BASE_URL",
        "VEDICWAY_OFFER_VERSION",
        "VEDICWAY_OFFER_URL",
        "VEDICWAY_PRIVACY_URL",
        "VEDICWAY_OPERATIONS_TOKEN",
        "VEDICWAY_OPERATIONS_CIDRS",
    ],
)
def test_production_fails_closed_when_required_setting_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    missing: str,
) -> None:
    _production(monkeypatch)
    monkeypatch.delenv(missing)

    with pytest.raises(PaymentConfigurationError, match=missing):
        PaymentSettings.from_environment()


def test_production_rejects_test_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    _production(monkeypatch)
    monkeypatch.setenv("VEDICWAY_TEST_PAYMENTS", "1")

    with pytest.raises(PaymentConfigurationError, match="VEDICWAY_TEST_PAYMENTS"):
        PaymentSettings.from_environment()


@pytest.mark.parametrize("vat_code", ["0", "13", "twenty-two"])
def test_vat_code_uses_current_yookassa_range(
    monkeypatch: pytest.MonkeyPatch,
    vat_code: str,
) -> None:
    _production(monkeypatch)
    monkeypatch.setenv("YOOKASSA_VAT_CODE", vat_code)

    with pytest.raises(PaymentConfigurationError, match="YOOKASSA_VAT_CODE"):
        PaymentSettings.from_environment()


def test_production_requires_https_public_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    _production(monkeypatch)
    monkeypatch.setenv("VEDICWAY_PUBLIC_BASE_URL", "http://vedicway.example")

    with pytest.raises(PaymentConfigurationError, match="VEDICWAY_PUBLIC_BASE_URL"):
        PaymentSettings.from_environment()


def test_production_forbids_custom_yookassa_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    _production(monkeypatch)
    monkeypatch.setenv("YOOKASSA_API_BASE_URL", "https://payments.example/v3")

    with pytest.raises(PaymentConfigurationError, match="YOOKASSA_API_BASE_URL"):
        PaymentSettings.from_environment()


def test_invalid_network_configuration_fails_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    _production(monkeypatch)
    monkeypatch.setenv("VEDICWAY_TRUSTED_PROXY_CIDRS", "not-a-network")

    with pytest.raises(PaymentConfigurationError, match="VEDICWAY_TRUSTED_PROXY_CIDRS"):
        PaymentSettings.from_environment()
