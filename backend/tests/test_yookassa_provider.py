from __future__ import annotations

import asyncio
import base64
import json

import httpx
import pytest

from vedicway_backend.errors import DomainError
from vedicway_backend.payment_config import PaymentSettings
from vedicway_backend.payments import PaymentStatus, RefundStatus
from vedicway_backend.yookassa import YooKassaPaymentProvider


def _settings(monkeypatch: pytest.MonkeyPatch) -> PaymentSettings:
    monkeypatch.setenv("VEDICWAY_PAYMENT_PROVIDER", "yookassa")
    monkeypatch.setenv("YOOKASSA_SHOP_ID", "123456")
    monkeypatch.setenv("YOOKASSA_SECRET_KEY", "test_secret_abcdefghijklmnopqrstuvwxyz")
    monkeypatch.setenv("YOOKASSA_VAT_CODE", "11")
    monkeypatch.setenv("VEDICWAY_PUBLIC_BASE_URL", "https://vedicway.example")
    monkeypatch.setenv("VEDICWAY_OFFER_VERSION", "2026-07-18")
    monkeypatch.setenv("VEDICWAY_OFFER_URL", "https://vedicway.example/legal/offer")
    monkeypatch.setenv("VEDICWAY_PRIVACY_URL", "https://vedicway.example/legal/privacy")
    monkeypatch.setenv("VEDICWAY_TEST_PAYMENTS", "0")
    return PaymentSettings.from_environment()


def _payment_payload(status: str = "pending") -> dict[str, object]:
    return {
        "id": "2f4ab123-000f-5000-9000-1d2b3c4d5e6f",
        "status": status,
        "paid": status == "succeeded",
        "amount": {"value": "990.00", "currency": "RUB"},
        "confirmation": {
            "type": "redirect",
            "confirmation_url": "https://yoomoney.ru/checkout/secure-token",
        },
        "metadata": {
            "purchase_id": "pur_123",
            "chart_id": "chart_123",
            "product_code": "full_report_v1",
            "environment": "development",
        },
        **({"captured_at": "2026-07-18T17:00:00Z"} if status == "succeeded" else {}),
    }


def test_create_redirect_payment_contains_receipt_and_stable_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(monkeypatch)
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_payment_payload(), request=request)

    provider = YooKassaPaymentProvider(settings, transport=httpx.MockTransport(handler))
    intent = asyncio.run(
        provider.create_payment(
            purchase_id="pur_123",
            chart_id="chart_123",
            product_code="full_report_v1",
            idempotency_key="provider-create-key",
            amount_minor=99_000,
            currency="RUB",
            return_url="https://vedicway.example/chart/chart_123?payment_return=pur_123",
            email="buyer@example.com",
        )
    )
    asyncio.run(provider.aclose())

    assert intent.status is PaymentStatus.PENDING
    assert intent.checkout_url == "https://yoomoney.ru/checkout/secure-token"
    assert intent.amount_minor == 99_000
    assert len(captured) == 1
    request = captured[0]
    assert request.method == "POST"
    assert request.url.path == "/v3/payments"
    assert request.headers["Idempotence-Key"] == "provider-create-key"
    expected_auth = base64.b64encode(b"123456:test_secret_abcdefghijklmnopqrstuvwxyz").decode("ascii")
    assert request.headers["Authorization"] == f"Basic {expected_auth}"
    payload = json.loads(request.content)
    assert payload["amount"] == {"value": "990.00", "currency": "RUB"}
    assert payload["capture"] is True
    assert payload["metadata"] == {
        "purchase_id": "pur_123",
        "chart_id": "chart_123",
        "product_code": "full_report_v1",
        "environment": "development",
    }
    assert payload["receipt"] == {
        "customer": {"email": "buyer@example.com"},
        "items": [
            {
                "description": "Полный персональный отчёт VedicWay",
                "quantity": "1.00",
                "amount": {"value": "990.00", "currency": "RUB"},
                "vat_code": 11,
                "payment_mode": "full_payment",
                "payment_subject": "service",
            }
        ],
    }
    assert settings.secret_key not in json.dumps(intent.redacted_payload)


def test_get_payment_parses_verified_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert "Idempotence-Key" not in request.headers
        return httpx.Response(200, json=_payment_payload("succeeded"), request=request)

    provider = YooKassaPaymentProvider(settings, transport=httpx.MockTransport(handler))
    intent = asyncio.run(provider.get_payment("2f4ab123-000f-5000-9000-1d2b3c4d5e6f"))
    asyncio.run(provider.aclose())

    assert intent.status is PaymentStatus.SUCCEEDED
    assert intent.paid is True
    assert intent.captured is True
    assert intent.currency == "RUB"
    assert intent.metadata["purchase_id"] == "pur_123"


def test_temporary_errors_retry_with_the_same_idempotency_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(monkeypatch)
    requests: list[httpx.Request] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        status_code = 500 if len(requests) < 3 else 200
        return httpx.Response(status_code, json=_payment_payload(), request=request)

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    provider = YooKassaPaymentProvider(
        settings,
        transport=httpx.MockTransport(handler),
        sleep=fake_sleep,
        max_attempts=3,
    )
    intent = asyncio.run(
        provider.create_payment(
            purchase_id="pur_123",
            chart_id="chart_123",
            product_code="full_report_v1",
            idempotency_key="one-stable-key",
            amount_minor=99_000,
            currency="RUB",
            return_url="https://vedicway.example/chart/chart_123?payment_return=pur_123",
            email="buyer@example.com",
        )
    )
    asyncio.run(provider.aclose())

    assert intent.status is PaymentStatus.PENDING
    assert [request.headers["Idempotence-Key"] for request in requests] == ["one-stable-key"] * 3
    assert sleeps == [0.25, 0.5]


def test_permanent_provider_error_is_redacted_and_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(monkeypatch)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            400,
            json={"type": "error", "id": "trace-secret", "code": "invalid_request", "description": "raw provider text"},
            request=request,
        )

    provider = YooKassaPaymentProvider(settings, transport=httpx.MockTransport(handler))
    with pytest.raises(DomainError) as captured:
        asyncio.run(
            provider.create_payment(
                purchase_id="pur_123",
                chart_id="chart_123",
                product_code="full_report_v1",
                idempotency_key="bad-request-key",
                amount_minor=99_000,
                currency="RUB",
                return_url="https://vedicway.example/chart/chart_123?payment_return=pur_123",
                email="buyer@example.com",
            )
        )
    asyncio.run(provider.aclose())

    assert captured.value.code == "PAYMENT_PROVIDER_REJECTED"
    assert captured.value.detail == {"provider_code": "invalid_request"}
    assert "raw provider text" not in captured.value.message
    assert len(requests) == 1


def test_partial_refund_contains_return_receipt(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "refund_123",
                "status": "succeeded",
                "payment_id": "payment_123",
                "amount": {"value": "300.00", "currency": "RUB"},
                "receipt_registration": "pending",
                "metadata": {"purchase_id": "pur_123"},
            },
            request=request,
        )

    provider = YooKassaPaymentProvider(settings, transport=httpx.MockTransport(handler))
    refund = asyncio.run(
        provider.refund(
            provider_payment_id="payment_123",
            purchase_id="pur_123",
            idempotency_key="refund-key",
            amount_minor=30_000,
            original_amount_minor=99_000,
            currency="RUB",
            email="buyer@example.com",
            reason="Запрос покупателя",
        )
    )
    asyncio.run(provider.aclose())

    assert refund.status is RefundStatus.SUCCEEDED
    payload = json.loads(requests[0].content)
    assert payload["amount"]["value"] == "300.00"
    assert payload["receipt"]["customer"]["email"] == "buyer@example.com"
    assert payload["receipt"]["items"][0]["amount"]["value"] == "300.00"
    assert payload["metadata"] == {"purchase_id": "pur_123"}


def test_full_refund_reuses_original_receipt_without_receipt_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(monkeypatch)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "refund_123",
                "status": "pending",
                "payment_id": "payment_123",
                "amount": {"value": "990.00", "currency": "RUB"},
                "metadata": {"purchase_id": "pur_123"},
            },
            request=request,
        )

    provider = YooKassaPaymentProvider(settings, transport=httpx.MockTransport(handler))
    refund = asyncio.run(
        provider.refund(
            provider_payment_id="payment_123",
            purchase_id="pur_123",
            idempotency_key="refund-key",
            amount_minor=99_000,
            original_amount_minor=99_000,
            currency="RUB",
            email="buyer@example.com",
            reason="Полный возврат",
        )
    )
    asyncio.run(provider.aclose())

    assert refund.status is RefundStatus.PENDING
    assert "receipt" not in json.loads(requests[0].content)


def test_get_refund_parses_cancellation_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "refund_123",
                "status": "canceled",
                "payment_id": "payment_123",
                "amount": {"value": "100.00", "currency": "RUB"},
                "cancellation_details": {"party": "yoo_money", "reason": "insufficient_funds"},
            },
            request=request,
        )

    provider = YooKassaPaymentProvider(settings, transport=httpx.MockTransport(handler))
    refund = asyncio.run(provider.get_refund("refund_123"))
    asyncio.run(provider.aclose())

    assert refund.status is RefundStatus.CANCELLED
    assert refund.failure_code == "insufficient_funds"
