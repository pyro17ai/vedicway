from __future__ import annotations

import ipaddress
from dataclasses import replace
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from vedicway_backend.main import create_app
from vedicway_backend.payment_config import PaymentSettings
from vedicway_backend.payments import (
    PaymentIntent,
    PaymentProvider,
    PaymentStatus,
    RefundIntent,
    RefundStatus,
)
from vedicway_backend.schemas import BirthInput, Place, ResolvedTime, TimeAccuracy
from vedicway_backend.store import Store
from vedicway_backend.worker import ChartWorker

OPERATIONS_TOKEN = "operations-token-at-least-thirty-two-characters"


class OperationsProvider(PaymentProvider):
    name = "yookassa"

    def __init__(self) -> None:
        self.refund_calls: list[dict[str, object]] = []
        self.purchase: dict[str, object] | None = None

    async def create_payment(self, **kwargs) -> PaymentIntent:  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def get_payment(self, provider_payment_id: str) -> PaymentIntent:
        assert self.purchase is not None
        return PaymentIntent(
            provider=self.name,
            provider_payment_id=provider_payment_id,
            status=PaymentStatus.SUCCEEDED,
            checkout_url=None,
            amount_minor=99_000,
            currency="RUB",
            metadata={
                "purchase_id": str(self.purchase["id"]),
                "chart_id": str(self.purchase["chart_id"]),
                "product_code": "full_report_v1",
            },
            paid=True,
            captured=True,
            redacted_payload={"id": provider_payment_id, "status": "succeeded"},
        )

    async def refund(self, **kwargs) -> RefundIntent:  # type: ignore[no-untyped-def]
        self.refund_calls.append(dict(kwargs))
        number = len(self.refund_calls)
        return RefundIntent(
            provider=self.name,
            provider_refund_id=f"refund_{number}",
            provider_payment_id=str(kwargs["provider_payment_id"]),
            status=RefundStatus.SUCCEEDED,
            amount_minor=int(kwargs["amount_minor"]),
            currency=str(kwargs["currency"]),
            metadata={"purchase_id": str(kwargs["purchase_id"])},
            receipt_registration="succeeded",
            redacted_payload={"id": f"refund_{number}", "status": "succeeded"},
        )

    async def get_refund(self, provider_refund_id: str) -> RefundIntent:
        raise NotImplementedError

    def normalize_status(self, value: str) -> PaymentStatus:
        return PaymentStatus(value)


def _birth() -> BirthInput:
    return BirthInput(
        local_datetime=datetime(2006, 10, 16, 13, 30),
        place=Place(
            place_id="ru-moscow-524901",
            display_name="Москва, Россия",
            country_code="RU",
            latitude=55.7558,
            longitude=37.6173,
            tzid="Europe/Moscow",
        ),
        resolved_time=ResolvedTime(
            utc_offset_seconds=14_400,
            utc_datetime=datetime(2006, 10, 16, 9, 30, tzinfo=UTC),
            resolution_source="test",
        ),
        time_accuracy=TimeAccuracy.EXACT,
    )


def _setup(tmp_path):  # type: ignore[no-untyped-def]
    store = Store(tmp_path / "runtime")
    session_id, _ = store.create_session()
    chart_id, _ = store.create_chart(session_id, _birth(), "chart-key")
    purchase, _ = store.create_purchase(
        chart_id,
        "purchase-key",
        "buyer@example.com",
        provider="yookassa",
        offer_version="development",
    )
    store.set_provider_payment(str(purchase["id"]), "yookassa", "payment_123", status="pending")
    store.apply_payment_event(
        str(purchase["id"]),
        provider_event_id="setup:payment.succeeded:payment_123",
        event_type="payment.succeeded",
        object_id="payment_123",
        payload_checksum="setup-checksum",
        status="succeeded",
        provider_status="succeeded",
        provider_payment_id="payment_123",
        amount_minor=99_000,
        currency="RUB",
        metadata={
            "purchase_id": str(purchase["id"]),
            "chart_id": chart_id,
            "product_code": "full_report_v1",
        },
    )
    provider = OperationsProvider()
    provider.purchase = purchase
    settings = replace(
        PaymentSettings.from_environment(),
        operations_token=OPERATIONS_TOKEN,
        operations_networks=(ipaddress.ip_network("10.0.0.0/24"),),
    )
    app = create_app(
        store=store,
        worker=ChartWorker(store),
        payment_settings=settings,
        payment_provider=provider,
    )
    return app, store, purchase, provider


def _headers(key: str = "refund-key") -> dict[str, str]:
    return {"X-Operations-Token": OPERATIONS_TOKEN, "Idempotency-Key": key}


def test_operations_require_constant_time_token_and_allowed_network(tmp_path) -> None:
    app, _, purchase, provider = _setup(tmp_path)
    path = f"/internal/payments/{purchase['id']}/refunds"
    with TestClient(app, client=("10.0.0.5", 50000)) as allowed:
        missing = allowed.post(path, json={"amount_minor": 30_000, "reason": "Запрос покупателя"})
        wrong = allowed.post(
            path,
            json={"amount_minor": 30_000, "reason": "Запрос покупателя"},
            headers={"X-Operations-Token": "wrong", "Idempotency-Key": "one"},
        )
    with TestClient(app, client=("203.0.113.10", 50000)) as denied:
        outside = denied.post(
            path,
            json={"amount_minor": 30_000, "reason": "Запрос покупателя"},
            headers=_headers(),
        )

    assert missing.status_code == 404
    assert wrong.status_code == 404
    assert outside.status_code == 403
    assert provider.refund_calls == []


def test_refund_requires_reason_valid_amount_and_idempotency_key(tmp_path) -> None:
    app, _, purchase, provider = _setup(tmp_path)
    path = f"/internal/payments/{purchase['id']}/refunds"
    with TestClient(app, client=("10.0.0.5", 50000)) as client:
        missing_reason = client.post(path, json={"amount_minor": 30_000}, headers=_headers("reason"))
        too_small = client.post(
            path,
            json={"amount_minor": 99, "reason": "Запрос покупателя"},
            headers=_headers("small"),
        )
        missing_key = client.post(
            path,
            json={"amount_minor": 30_000, "reason": "Запрос покупателя"},
            headers={"X-Operations-Token": OPERATIONS_TOKEN},
        )

    assert missing_reason.status_code == 400
    assert too_small.status_code == 400
    assert missing_key.status_code == 400
    assert provider.refund_calls == []


def test_duplicate_refund_key_calls_provider_once_and_audits_result(tmp_path) -> None:
    app, store, purchase, provider = _setup(tmp_path)
    path = f"/internal/payments/{purchase['id']}/refunds"
    with TestClient(app, client=("10.0.0.5", 50000)) as client:
        first = client.post(
            path,
            json={"amount_minor": 30_000, "reason": "Частичный возврат"},
            headers=_headers("same-key"),
        )
        duplicate = client.post(
            path,
            json={"amount_minor": 30_000, "reason": "Частичный возврат"},
            headers=_headers("same-key"),
        )

    assert first.status_code == 202
    assert duplicate.status_code == 202
    assert duplicate.json()["refund_id"] == first.json()["refund_id"]
    assert len(provider.refund_calls) == 1
    assert provider.refund_calls[0]["idempotency_key"] == store.get_refund(first.json()["refund_id"])["provider_idempotency_key"]  # type: ignore[index]
    audits = store.payment_operations(str(purchase["id"]))
    assert audits[0]["action"] == "refund"
    assert audits[0]["amount_minor"] == 30_000
    assert audits[0]["reason"] == "Частичный возврат"
    with store._connection() as connection:
        stored_audits = connection.execute(
            """SELECT action, actor_fingerprint, source_ip, trace_id, detail_json
               FROM payment_operations"""
        ).fetchall()
    assert OPERATIONS_TOKEN not in repr(stored_audits)


def test_partial_then_full_refund_revokes_entitlement(tmp_path) -> None:
    app, store, purchase, provider = _setup(tmp_path)
    path = f"/internal/payments/{purchase['id']}/refunds"
    with TestClient(app, client=("10.0.0.5", 50000)) as client:
        partial = client.post(
            path,
            json={"amount_minor": 30_000, "reason": "Частичный возврат"},
            headers=_headers("partial"),
        )
        assert store.has_entitlement(str(purchase["chart_id"])) is True
        full = client.post(
            path,
            json={"amount_minor": 69_000, "reason": "Возврат остатка"},
            headers=_headers("remainder"),
        )

    assert partial.json()["status"] == "succeeded"
    assert full.json()["status"] == "succeeded"
    assert len(provider.refund_calls) == 2
    assert store.get_purchase(str(purchase["id"]))["status"] == "refunded"  # type: ignore[index]
    assert store.has_entitlement(str(purchase["chart_id"])) is False


def test_internal_reconcile_is_protected_and_audited(tmp_path) -> None:
    app, store, purchase, _ = _setup(tmp_path)
    with TestClient(app, client=("10.0.0.5", 50000)) as client:
        response = client.post(
            f"/internal/payments/{purchase['id']}/reconcile",
            headers={"X-Operations-Token": OPERATIONS_TOKEN},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"
    assert store.payment_operations(str(purchase["id"]))[-1]["action"] == "reconcile"
