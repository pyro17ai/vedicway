from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlsplit

OFFICIAL_YOOKASSA_API_BASE_URL = "https://api.yookassa.ru/v3"


class PaymentConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PaymentProduct:
    code: str
    amount_minor: int
    currency: str
    title: str
    receipt_description: str


@dataclass(frozen=True, slots=True)
class PaymentCatalog:
    full_report: PaymentProduct = field(
        default_factory=lambda: PaymentProduct(
            code="full_report_v1",
            amount_minor=99_000,
            currency="RUB",
            title="Полный персональный отчёт",
            receipt_description="Полный персональный отчёт VedicWay",
        )
    )

    def get(self, product_code: str) -> PaymentProduct:
        if product_code != self.full_report.code:
            raise KeyError(product_code)
        return self.full_report


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise PaymentConfigurationError(f"{name} is required")
    return value


def _absolute_url(name: str, value: str, *, require_https: bool) -> str:
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.netloc or parsed.username or parsed.password:
        raise PaymentConfigurationError(f"{name} must be an absolute URL without credentials")
    if parsed.scheme not in ({"https"} if require_https else {"http", "https"}):
        expectation = "HTTPS" if require_https else "HTTP or HTTPS"
        raise PaymentConfigurationError(f"{name} must use {expectation}")
    return value.rstrip("/")


def _integer(name: str, raw: str, minimum: int, maximum: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise PaymentConfigurationError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise PaymentConfigurationError(f"{name} must be between {minimum} and {maximum}")
    return value


def _networks(name: str, raw: str) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    if not raw.strip():
        return ()
    try:
        return tuple(ipaddress.ip_network(item.strip(), strict=False) for item in raw.split(",") if item.strip())
    except ValueError as exc:
        raise PaymentConfigurationError(f"{name} contains an invalid CIDR") from exc


@dataclass(frozen=True, slots=True)
class PaymentSettings:
    environment: str
    provider: Literal["disabled", "test", "yookassa"]
    api_base_url: str
    shop_id: str | None
    secret_key: str | None
    public_base_url: str
    offer_version: str
    offer_url: str
    privacy_url: str
    operations_token: str | None
    trusted_proxy_networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]
    operations_networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]
    vat_code: int | None
    tax_system_code: int | None
    receipts_enabled: bool
    payment_description: str
    catalog: PaymentCatalog = field(default_factory=PaymentCatalog)

    @classmethod
    def from_environment(cls) -> PaymentSettings:
        environment = os.getenv("VEDICWAY_ENV", "development").strip().casefold() or "development"
        production = environment == "production"
        test_payments = os.getenv("VEDICWAY_TEST_PAYMENTS", "0").strip() == "1"
        configured_provider = os.getenv("VEDICWAY_PAYMENT_PROVIDER", "").strip().casefold()

        if production and test_payments:
            raise PaymentConfigurationError("VEDICWAY_TEST_PAYMENTS cannot be enabled in production")
        if test_payments:
            provider: Literal["disabled", "test", "yookassa"] = "test"
        elif configured_provider in {"", "disabled"}:
            provider = "disabled"
        elif configured_provider == "yookassa":
            provider = "yookassa"
        else:
            raise PaymentConfigurationError("VEDICWAY_PAYMENT_PROVIDER must be disabled or yookassa")
        if production and provider != "yookassa":
            raise PaymentConfigurationError("VEDICWAY_PAYMENT_PROVIDER=yookassa is required in production")

        raw_base_url = os.getenv("YOOKASSA_API_BASE_URL", OFFICIAL_YOOKASSA_API_BASE_URL).strip().rstrip("/")
        api_base_url = _absolute_url("YOOKASSA_API_BASE_URL", raw_base_url, require_https=production)
        if production and api_base_url != OFFICIAL_YOOKASSA_API_BASE_URL:
            raise PaymentConfigurationError("YOOKASSA_API_BASE_URL cannot override the official origin in production")

        public_base_url = os.getenv("VEDICWAY_PUBLIC_BASE_URL", "http://127.0.0.1:5173").strip()
        offer_version = os.getenv("VEDICWAY_OFFER_VERSION", "development").strip()
        offer_url = os.getenv("VEDICWAY_OFFER_URL", "http://127.0.0.1:5173/legal/offer").strip()
        privacy_url = os.getenv("VEDICWAY_PRIVACY_URL", "http://127.0.0.1:5173/legal/privacy").strip()
        shop_id: str | None = None
        secret_key: str | None = None
        vat_code: int | None = None
        tax_system_code: int | None = None

        if provider == "yookassa":
            shop_id = _required("YOOKASSA_SHOP_ID")
            secret_key = _required("YOOKASSA_SECRET_KEY")
            public_base_url = _required("VEDICWAY_PUBLIC_BASE_URL")
            offer_version = _required("VEDICWAY_OFFER_VERSION")
            offer_url = _required("VEDICWAY_OFFER_URL")
            privacy_url = _required("VEDICWAY_PRIVACY_URL")
            vat_code = _integer("YOOKASSA_VAT_CODE", _required("YOOKASSA_VAT_CODE"), 1, 12)
            raw_tax_system = os.getenv("YOOKASSA_TAX_SYSTEM_CODE", "").strip()
            if raw_tax_system:
                tax_system_code = _integer("YOOKASSA_TAX_SYSTEM_CODE", raw_tax_system, 1, 6)

        public_base_url = _absolute_url("VEDICWAY_PUBLIC_BASE_URL", public_base_url, require_https=production)
        offer_url = _absolute_url("VEDICWAY_OFFER_URL", offer_url, require_https=production)
        privacy_url = _absolute_url("VEDICWAY_PRIVACY_URL", privacy_url, require_https=production)
        if not offer_version:
            raise PaymentConfigurationError("VEDICWAY_OFFER_VERSION is required")

        operations_token = os.getenv("VEDICWAY_OPERATIONS_TOKEN", "").strip() or None
        operations_networks = _networks(
            "VEDICWAY_OPERATIONS_CIDRS",
            os.getenv("VEDICWAY_OPERATIONS_CIDRS", ""),
        )
        trusted_proxy_networks = _networks(
            "VEDICWAY_TRUSTED_PROXY_CIDRS",
            os.getenv("VEDICWAY_TRUSTED_PROXY_CIDRS", ""),
        )
        if production:
            operations_token = _required("VEDICWAY_OPERATIONS_TOKEN")
            if len(operations_token) < 32:
                raise PaymentConfigurationError("VEDICWAY_OPERATIONS_TOKEN must contain at least 32 characters")
            if not operations_networks:
                raise PaymentConfigurationError("VEDICWAY_OPERATIONS_CIDRS is required")

        return cls(
            environment=environment,
            provider=provider,
            api_base_url=api_base_url,
            shop_id=shop_id,
            secret_key=secret_key,
            public_base_url=public_base_url,
            offer_version=offer_version,
            offer_url=offer_url,
            privacy_url=privacy_url,
            operations_token=operations_token,
            trusted_proxy_networks=trusted_proxy_networks,
            operations_networks=operations_networks,
            vat_code=vat_code,
            tax_system_code=tax_system_code,
            receipts_enabled=provider == "yookassa",
            payment_description=os.getenv("YOOKASSA_PAYMENT_DESCRIPTION", "Оплата полного отчёта VedicWay").strip()
            or "Оплата полного отчёта VedicWay",
        )
