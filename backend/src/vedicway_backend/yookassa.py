from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit

import httpx

from .errors import DomainError
from .payment_config import PaymentSettings
from .payments import PaymentIntent, PaymentProvider, PaymentStatus, RefundIntent, RefundStatus

_OBJECT_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_SAFE_PROVIDER_CODE = re.compile(r"^[a-z0-9_.-]{1,64}$")


def _money(amount_minor: int) -> str:
    return f"{Decimal(amount_minor) / Decimal(100):.2f}"


def _minor_units(payload: dict[str, Any]) -> tuple[int, str]:
    amount = payload.get("amount")
    if not isinstance(amount, dict):
        raise DomainError(
            "PAYMENT_PROVIDER_INVALID_RESPONSE",
            "Платёжный сервис вернул неполные данные",
            status_code=503,
        )
    try:
        value = Decimal(str(amount["value"])) * Decimal(100)
        amount_minor = int(value.to_integral_exact())
        currency = str(amount["currency"])
    except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
        raise DomainError(
            "PAYMENT_PROVIDER_INVALID_RESPONSE",
            "Платёжный сервис вернул неверную сумму",
            status_code=503,
        ) from exc
    return amount_minor, currency


def _safe_code(value: Any) -> str | None:
    if isinstance(value, str) and _SAFE_PROVIDER_CODE.fullmatch(value):
        return value
    return None


def _metadata(payload: dict[str, Any]) -> dict[str, str]:
    raw = payload.get("metadata")
    if not isinstance(raw, dict):
        return {}
    result: dict[str, str] = {}
    for key, value in raw.items():
        if isinstance(key, str) and isinstance(value, (str, int, float, bool)):
            result[key] = str(value)
    return result


class YooKassaPaymentProvider(PaymentProvider):
    name = "yookassa"

    def __init__(
        self,
        settings: PaymentSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        max_attempts: int = 3,
        timeout_seconds: float = 15.0,
    ) -> None:
        if settings.provider != "yookassa" or not settings.shop_id or not settings.secret_key:
            raise RuntimeError("YooKassaPaymentProvider requires complete YooKassa settings")
        self.settings = settings
        self.max_attempts = max(1, max_attempts)
        self._sleep = sleep or asyncio.sleep
        self._client = httpx.AsyncClient(
            base_url=f"{settings.api_base_url.rstrip('/')}/",
            auth=(settings.shop_id, settings.secret_key),
            headers={"Accept": "application/json", "User-Agent": "VedicWay/1.0"},
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
            follow_redirects=False,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _validate_object_id(value: str) -> str:
        if not _OBJECT_ID.fullmatch(value):
            raise DomainError(
                "PAYMENT_PROVIDER_ID_INVALID",
                "Идентификатор платёжной операции имеет неверный формат",
                recoverable=False,
                status_code=400,
            )
        return value

    async def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Idempotence-Key": idempotency_key} if idempotency_key else None
        last_transport_error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                response = await self._client.request(method, path, json=payload, headers=headers)
            except (httpx.TimeoutException, httpx.NetworkError, httpx.ProtocolError) as exc:
                last_transport_error = exc
                if attempt + 1 < self.max_attempts:
                    await self._sleep(0.25 * (2**attempt))
                    continue
                raise DomainError(
                    "PAYMENT_PROVIDER_TEMPORARY",
                    "Платёжный сервис временно не отвечает",
                    recoverable=True,
                    status_code=503,
                ) from exc

            if 200 <= response.status_code < 300:
                try:
                    body = response.json()
                except ValueError as exc:
                    raise DomainError(
                        "PAYMENT_PROVIDER_INVALID_RESPONSE",
                        "Платёжный сервис вернул нечитаемый ответ",
                        recoverable=True,
                        status_code=503,
                    ) from exc
                if not isinstance(body, dict):
                    raise DomainError(
                        "PAYMENT_PROVIDER_INVALID_RESPONSE",
                        "Платёжный сервис вернул неверный ответ",
                        recoverable=True,
                        status_code=503,
                    )
                return body

            temporary = response.status_code == 429 or response.status_code >= 500
            if temporary and attempt + 1 < self.max_attempts:
                await self._sleep(0.25 * (2**attempt))
                continue
            provider_code = None
            try:
                error_body = response.json()
                if isinstance(error_body, dict):
                    provider_code = _safe_code(error_body.get("code"))
            except ValueError:
                pass
            detail = {"provider_code": provider_code} if provider_code else {}
            if temporary:
                raise DomainError(
                    "PAYMENT_PROVIDER_TEMPORARY",
                    "Платёжный сервис временно недоступен",
                    recoverable=True,
                    status_code=503,
                    detail=detail,
                )
            if response.status_code in {401, 403}:
                raise DomainError(
                    "PAYMENT_PROVIDER_AUTH_FAILED",
                    "Платёжный сервис не настроен",
                    recoverable=False,
                    status_code=503,
                    detail=detail,
                )
            if response.status_code == 404:
                raise DomainError(
                    "PAYMENT_PROVIDER_OBJECT_NOT_FOUND",
                    "Платёжная операция не найдена",
                    recoverable=False,
                    status_code=502,
                    detail=detail,
                )
            raise DomainError(
                "PAYMENT_PROVIDER_REJECTED",
                "Платёжный сервис отклонил запрос",
                recoverable=False,
                status_code=502,
                detail=detail,
            )
        raise DomainError(
            "PAYMENT_PROVIDER_TEMPORARY",
            "Платёжный сервис временно недоступен",
            status_code=503,
        ) from last_transport_error

    def _receipt(self, email: str, amount_minor: int, currency: str) -> dict[str, Any]:
        product = self.settings.catalog.full_report
        receipt: dict[str, Any] = {
            "customer": {"email": email},
            "items": [
                {
                    "description": product.receipt_description,
                    "quantity": "1.00",
                    "amount": {"value": _money(amount_minor), "currency": currency},
                    "vat_code": self.settings.vat_code,
                    "payment_mode": "full_payment",
                    "payment_subject": "service",
                }
            ],
        }
        if self.settings.tax_system_code is not None:
            receipt["tax_system_code"] = self.settings.tax_system_code
        return receipt

    def _parse_payment(self, payload: dict[str, Any]) -> PaymentIntent:
        provider_payment_id = payload.get("id")
        raw_status = payload.get("status")
        if not isinstance(provider_payment_id, str) or not isinstance(raw_status, str):
            raise DomainError(
                "PAYMENT_PROVIDER_INVALID_RESPONSE",
                "Платёжный сервис вернул неполные данные",
                status_code=503,
            )
        amount_minor, currency = _minor_units(payload)
        status = self.normalize_status(raw_status)
        confirmation = payload.get("confirmation")
        checkout_url = confirmation.get("confirmation_url") if isinstance(confirmation, dict) else None
        if not isinstance(checkout_url, str):
            checkout_url = None
        cancellation = payload.get("cancellation_details")
        failure_code = _safe_code(cancellation.get("reason")) if isinstance(cancellation, dict) else None
        return PaymentIntent(
            provider=self.name,
            provider_payment_id=provider_payment_id,
            status=status,
            checkout_url=checkout_url,
            amount_minor=amount_minor,
            currency=currency,
            metadata=_metadata(payload),
            paid=payload.get("paid") is True,
            captured=isinstance(payload.get("captured_at"), str),
            failure_code=failure_code,
            redacted_payload={
                "id": provider_payment_id,
                "status": raw_status,
                "test": payload.get("test") is True,
                "receipt_registration": payload.get("receipt_registration"),
            },
        )

    @staticmethod
    def _parse_refund(payload: dict[str, Any]) -> RefundIntent:
        provider_refund_id = payload.get("id")
        provider_payment_id = payload.get("payment_id")
        raw_status = payload.get("status")
        if not all(isinstance(value, str) for value in (provider_refund_id, provider_payment_id, raw_status)):
            raise DomainError(
                "PAYMENT_PROVIDER_INVALID_RESPONSE",
                "Платёжный сервис вернул неполные данные возврата",
                status_code=503,
            )
        amount_minor, currency = _minor_units(payload)
        status_map = {
            "pending": RefundStatus.PENDING,
            "succeeded": RefundStatus.SUCCEEDED,
            "canceled": RefundStatus.CANCELLED,
        }
        status = status_map.get(raw_status, RefundStatus.FAILED)
        cancellation = payload.get("cancellation_details")
        failure_code = _safe_code(cancellation.get("reason")) if isinstance(cancellation, dict) else None
        receipt_registration = payload.get("receipt_registration")
        return RefundIntent(
            provider="yookassa",
            provider_refund_id=provider_refund_id,
            provider_payment_id=provider_payment_id,
            status=status,
            amount_minor=amount_minor,
            currency=currency,
            metadata=_metadata(payload),
            failure_code=failure_code,
            receipt_registration=receipt_registration if isinstance(receipt_registration, str) else None,
            redacted_payload={"id": provider_refund_id, "status": raw_status},
        )

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
        product = self.settings.catalog.get(product_code)
        if amount_minor != product.amount_minor or currency != product.currency:
            raise DomainError(
                "PAYMENT_AMOUNT_MISMATCH",
                "Цена покупки изменилась. Обновите страницу.",
                recoverable=False,
                status_code=409,
            )
        return_parts = urlsplit(return_url)
        public_parts = urlsplit(self.settings.public_base_url)
        if (return_parts.scheme, return_parts.netloc) != (public_parts.scheme, public_parts.netloc):
            raise DomainError(
                "PAYMENT_RETURN_URL_INVALID",
                "Адрес возврата после оплаты имеет неверный формат",
                recoverable=False,
                status_code=500,
            )
        payload = {
            "amount": {"value": _money(amount_minor), "currency": currency},
            "capture": True,
            "confirmation": {"type": "redirect", "return_url": return_url},
            "description": self.settings.payment_description,
            "metadata": {
                "purchase_id": purchase_id,
                "chart_id": chart_id,
                "product_code": product_code,
                "environment": self.settings.environment,
            },
            "receipt": self._receipt(email, amount_minor, currency),
        }
        response = await self._request("POST", "payments", payload=payload, idempotency_key=idempotency_key)
        return self._parse_payment(response)

    async def get_payment(self, provider_payment_id: str) -> PaymentIntent:
        payment_id = self._validate_object_id(provider_payment_id)
        response = await self._request("GET", f"payments/{payment_id}")
        return self._parse_payment(response)

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
        payment_id = self._validate_object_id(provider_payment_id)
        if amount_minor < 100 or amount_minor > original_amount_minor:
            raise DomainError(
                "REFUND_AMOUNT_INVALID",
                "Сумма возврата недопустима",
                recoverable=False,
                status_code=409,
            )
        remainder = original_amount_minor - amount_minor
        if remainder and remainder < 100:
            raise DomainError(
                "REFUND_AMOUNT_INVALID",
                "После частичного возврата должно остаться не меньше одного рубля",
                recoverable=False,
                status_code=409,
            )
        payload: dict[str, Any] = {
            "payment_id": payment_id,
            "amount": {"value": _money(amount_minor), "currency": currency},
            "description": f"Возврат по заказу {purchase_id}"[:250],
            "metadata": {"purchase_id": purchase_id},
        }
        if amount_minor != original_amount_minor:
            payload["receipt"] = self._receipt(email, amount_minor, currency)
        response = await self._request("POST", "refunds", payload=payload, idempotency_key=idempotency_key)
        return self._parse_refund(response)

    async def get_refund(self, provider_refund_id: str) -> RefundIntent:
        refund_id = self._validate_object_id(provider_refund_id)
        response = await self._request("GET", f"refunds/{refund_id}")
        return self._parse_refund(response)

    def normalize_status(self, value: str) -> PaymentStatus:
        mapping = {
            "created": PaymentStatus.CREATED,
            "pending": PaymentStatus.PENDING,
            "waiting_for_capture": PaymentStatus.PENDING,
            "succeeded": PaymentStatus.SUCCEEDED,
            "canceled": PaymentStatus.CANCELLED,
        }
        return mapping.get(value, PaymentStatus.FAILED)
