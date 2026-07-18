from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .errors import DomainError


class PaymentStatus(StrEnum):
    CREATED = "created"
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    CANCELLED = "cancelled"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


@dataclass(frozen=True, slots=True)
class PaymentIntent:
    provider: str
    provider_payment_id: str | None
    status: PaymentStatus
    checkout_url: str | None
    redacted_payload: dict[str, Any]


class PaymentProvider(ABC):
    @abstractmethod
    def create_payment(self, purchase_id: str, amount_minor: int, currency: str, return_url: str) -> PaymentIntent:
        raise NotImplementedError

    @abstractmethod
    def get_payment(self, provider_payment_id: str) -> PaymentIntent:
        raise NotImplementedError

    @abstractmethod
    def verify_webhook(self, raw_body: bytes, headers: dict[str, str]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def refund(self, provider_payment_id: str, amount_minor: int | None = None) -> PaymentIntent:
        raise NotImplementedError

    @abstractmethod
    def normalize_status(self, value: str) -> PaymentStatus:
        raise NotImplementedError


class TestPaymentProvider(PaymentProvider):
    """Local-only adapter. It can never be selected unless VEDICWAY_TEST_PAYMENTS=1."""

    name = "test"

    def create_payment(self, purchase_id: str, amount_minor: int, currency: str, return_url: str) -> PaymentIntent:
        return PaymentIntent(
            provider=self.name,
            provider_payment_id=f"test_{purchase_id}",
            status=PaymentStatus.PENDING,
            checkout_url=f"/api/v1/test/purchases/{purchase_id}/confirm",
            redacted_payload={"amount_minor": amount_minor, "currency": currency, "return_url": return_url},
        )

    def get_payment(self, provider_payment_id: str) -> PaymentIntent:
        return PaymentIntent(self.name, provider_payment_id, PaymentStatus.PENDING, None, {})

    def verify_webhook(self, raw_body: bytes, headers: dict[str, str]) -> dict[str, Any]:
        raise DomainError("TEST_WEBHOOK_UNAVAILABLE", "Тестовый провайдер не принимает внешние webhooks", recoverable=False)

    def refund(self, provider_payment_id: str, amount_minor: int | None = None) -> PaymentIntent:
        return PaymentIntent(self.name, provider_payment_id, PaymentStatus.REFUNDED, None, {"amount_minor": amount_minor})

    def normalize_status(self, value: str) -> PaymentStatus:
        return PaymentStatus(value)


class DisabledPaymentProvider(PaymentProvider):
    name = "pending_provider"

    def _disabled(self):
        raise DomainError("PAYMENT_PROVIDER_UNAVAILABLE", "Приём платежей временно недоступен", recoverable=True, status_code=503)

    def create_payment(self, purchase_id: str, amount_minor: int, currency: str, return_url: str) -> PaymentIntent:
        self._disabled()

    def get_payment(self, provider_payment_id: str) -> PaymentIntent:
        self._disabled()

    def verify_webhook(self, raw_body: bytes, headers: dict[str, str]) -> dict[str, Any]:
        self._disabled()

    def refund(self, provider_payment_id: str, amount_minor: int | None = None) -> PaymentIntent:
        self._disabled()

    def normalize_status(self, value: str) -> PaymentStatus:
        return PaymentStatus(value)


def payment_provider_from_environment() -> PaymentProvider:
    import os

    return TestPaymentProvider() if os.environ.get("VEDICWAY_TEST_PAYMENTS") == "1" else DisabledPaymentProvider()
