from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .errors import DomainError
from .payment_config import PaymentSettings


class PaymentStatus(StrEnum):
    CREATED = "created"
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    CANCELLED = "cancelled"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


class RefundStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PaymentIntent:
    provider: str
    provider_payment_id: str | None
    status: PaymentStatus
    checkout_url: str | None
    amount_minor: int
    currency: str
    metadata: dict[str, str] = field(default_factory=dict)
    paid: bool = False
    captured: bool = False
    failure_code: str | None = None
    redacted_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RefundIntent:
    provider: str
    provider_refund_id: str | None
    provider_payment_id: str
    status: RefundStatus
    amount_minor: int
    currency: str
    metadata: dict[str, str] = field(default_factory=dict)
    failure_code: str | None = None
    receipt_registration: str | None = None
    redacted_payload: dict[str, Any] = field(default_factory=dict)


class PaymentProvider(ABC):
    name: str

    @abstractmethod
    async def create_payment(
        self,
        *,
        purchase_id: str,
        chart_id: str,
        product_code: str,
        idempotency_key: str,
        amount_minor: int,
        currency: str,
        return_url: str,
        email: str,
    ) -> PaymentIntent:
        raise NotImplementedError

    @abstractmethod
    async def get_payment(self, provider_payment_id: str) -> PaymentIntent:
        raise NotImplementedError

    @abstractmethod
    async def refund(
        self,
        *,
        provider_payment_id: str,
        purchase_id: str,
        idempotency_key: str,
        amount_minor: int,
        original_amount_minor: int,
        currency: str,
        email: str,
        reason: str,
    ) -> RefundIntent:
        raise NotImplementedError

    @abstractmethod
    async def get_refund(self, provider_refund_id: str) -> RefundIntent:
        raise NotImplementedError

    @abstractmethod
    def normalize_status(self, value: str) -> PaymentStatus:
        raise NotImplementedError

    async def aclose(self) -> None:
        return None


class TestPaymentProvider(PaymentProvider):
    """Local adapter. Production configuration rejects this provider."""

    name = "test"

    async def create_payment(
        self,
        *,
        purchase_id: str,
        chart_id: str,
        product_code: str,
        idempotency_key: str,
        amount_minor: int,
        currency: str,
        return_url: str,
        email: str,
    ) -> PaymentIntent:
        return PaymentIntent(
            provider=self.name,
            provider_payment_id=f"test_{purchase_id}",
            status=PaymentStatus.PENDING,
            checkout_url=f"/api/v1/test/checkout/{purchase_id}",
            amount_minor=amount_minor,
            currency=currency,
            metadata={"purchase_id": purchase_id, "chart_id": chart_id, "product_code": product_code},
            redacted_payload={"id": f"test_{purchase_id}", "status": "pending"},
        )

    async def get_payment(self, provider_payment_id: str) -> PaymentIntent:
        return PaymentIntent(
            provider=self.name,
            provider_payment_id=provider_payment_id,
            status=PaymentStatus.PENDING,
            checkout_url=None,
            amount_minor=0,
            currency="RUB",
        )

    async def refund(
        self,
        *,
        provider_payment_id: str,
        purchase_id: str,
        idempotency_key: str,
        amount_minor: int,
        original_amount_minor: int,
        currency: str,
        email: str,
        reason: str,
    ) -> RefundIntent:
        return RefundIntent(
            provider=self.name,
            provider_refund_id=f"test_refund_{purchase_id}",
            provider_payment_id=provider_payment_id,
            status=RefundStatus.SUCCEEDED,
            amount_minor=amount_minor,
            currency=currency,
            metadata={"purchase_id": purchase_id},
        )

    async def get_refund(self, provider_refund_id: str) -> RefundIntent:
        return RefundIntent(
            provider=self.name,
            provider_refund_id=provider_refund_id,
            provider_payment_id="test_payment",
            status=RefundStatus.SUCCEEDED,
            amount_minor=0,
            currency="RUB",
        )

    def normalize_status(self, value: str) -> PaymentStatus:
        if value == "canceled":
            return PaymentStatus.CANCELLED
        return PaymentStatus(value)


class DisabledPaymentProvider(PaymentProvider):
    name = "disabled"

    @staticmethod
    def _disabled() -> None:
        raise DomainError(
            "PAYMENT_PROVIDER_UNAVAILABLE",
            "Приём платежей временно недоступен",
            recoverable=True,
            status_code=503,
        )

    async def create_payment(self, **_: Any) -> PaymentIntent:
        self._disabled()
        raise AssertionError("unreachable")

    async def get_payment(self, provider_payment_id: str) -> PaymentIntent:
        self._disabled()
        raise AssertionError("unreachable")

    async def refund(self, **_: Any) -> RefundIntent:
        self._disabled()
        raise AssertionError("unreachable")

    async def get_refund(self, provider_refund_id: str) -> RefundIntent:
        self._disabled()
        raise AssertionError("unreachable")

    def normalize_status(self, value: str) -> PaymentStatus:
        if value == "canceled":
            return PaymentStatus.CANCELLED
        return PaymentStatus(value)


def payment_provider_from_settings(
    settings: PaymentSettings,
    *,
    transport: Any | None = None,
    sleep: Callable[[float], Awaitable[None]] | None = None,
) -> PaymentProvider:
    if settings.provider == "test":
        return TestPaymentProvider()
    if settings.provider == "yookassa":
        from .yookassa import YooKassaPaymentProvider

        return YooKassaPaymentProvider(settings, transport=transport, sleep=sleep)
    return DisabledPaymentProvider()


def payment_provider_from_environment() -> PaymentProvider:
    return payment_provider_from_settings(PaymentSettings.from_environment())
