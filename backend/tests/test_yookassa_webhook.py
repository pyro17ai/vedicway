from __future__ import annotations

import ipaddress
from dataclasses import replace
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from vedicway_backend.errors import DomainError
from vedicway_backend.main import create_app
from vedicway_backend.payment_config import PaymentSettings
from vedicway_backend.payment_security import effective_client_ip, is_yookassa_source
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

OFFICIAL_ADDRESSES = [
    "185.71.76.1",
    "185.71.77.25",
    "77.75.153.124",
    "77.75.156.11",
    "77.75.156.35",
    "77.75.154.200",
    "2a02:5180::1234",
]


class LookupProvider(PaymentProvider):
    name = "yookassa"

    def __init__(self, intent: PaymentIntent | DomainError) -> None:
        self.intent = intent
        self.lookup_calls: list[str] = []
        self.refund_intent: RefundIntent | DomainError | None = None

    async def create_payment(self, **kwargs) -> PaymentIntent:  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def get_payment(self, provider_payment_id: str) -> PaymentIntent:
        self.lookup_calls.append(provider_payment_id)
        if isinstance(self.intent, DomainError):
            raise self.intent
        return self.intent

    async def refund(self, **kwargs) -> RefundIntent:  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def get_refund(self, provider_refund_id: str) -> RefundIntent:
        if isinstance(self.refund_intent, DomainError):
            raise self.refund_intent
        if self.refund_intent is None:
            raise NotImplementedError
        return self.refund_intent

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


def _intent(purchase: dict[str, object], **changes: object) -> PaymentIntent:
    values: dict[str, object] = {
        "provider": "yookassa",
        "provider_payment_id": "payment_123",
        "status": PaymentStatus.SUCCEEDED,
        "checkout_url": None,
        "amount_minor": 99_000,
        "currency": "RUB",
        "metadata": {
            "purchase_id": str(purchase["id"]),
            "chart_id": str(purchase["chart_id"]),
            "product_code": "full_report_v1",
        },
        "paid": True,
        "captured": True,
        "redacted_payload": {"id": "payment_123", "status": "succeeded"},
    }
    values.update(changes)
    return PaymentIntent(**values)  # type: ignore[arg-type]


def _setup(  # type: ignore[no-untyped-def]
    tmp_path,
    intent_factory=None,
    *,
    trusted_proxy: bool = False,
    link_provider_payment: bool = True,
):
    store = Store(tmp_path / "runtime")
    session_id, token = store.create_session()
    chart_id, _ = store.create_chart(session_id, _birth(), "chart-key")
    purchase, _ = store.create_purchase(
        chart_id,
        "purchase-key",
        "buyer@example.com",
        provider="yookassa",
        offer_version="development",
    )
    if link_provider_payment:
        store.set_provider_payment(
            str(purchase["id"]),
            "yookassa",
            "payment_123",
            status="pending",
            provider_status="pending",
        )
    intent = intent_factory(purchase) if intent_factory else _intent(purchase)
    provider = LookupProvider(intent)
    settings = PaymentSettings.from_environment()
    if trusted_proxy:
        settings = replace(settings, trusted_proxy_networks=(ipaddress.ip_network("127.0.0.1/32"),))
    app = create_app(
        store=store,
        worker=ChartWorker(store),
        payment_settings=settings,
        payment_provider=provider,
    )
    return app, store, token, purchase, provider


def _notification(event: str = "payment.succeeded") -> dict[str, object]:
    return {"type": "notification", "event": event, "object": {"id": "payment_123"}}


def test_all_official_yookassa_networks_are_recognized() -> None:
    assert all(is_yookassa_source(address) for address in OFFICIAL_ADDRESSES)
    assert is_yookassa_source("185.71.76.32") is False
    assert is_yookassa_source("203.0.113.10") is False


def test_forwarded_address_is_used_only_for_trusted_proxy() -> None:
    trusted = (ipaddress.ip_network("127.0.0.1/32"),)
    assert effective_client_ip("203.0.113.10", "185.71.76.3", trusted) == "203.0.113.10"
    assert effective_client_ip("127.0.0.1", "203.0.113.44, 185.71.76.3", trusted) == "185.71.76.3"


def test_timeweb_edge_chain_preserves_yookassa_source() -> None:
    trusted = tuple(
        ipaddress.ip_network(value)
        for value in ("172.29.0.0/24", "172.22.0.1/32", "92.53.96.169/32")
    )
    assert effective_client_ip(
        "172.29.0.3",
        "77.75.154.206, 92.53.96.169, 172.22.0.1",
        trusted,
    ) == "77.75.154.206"


def test_verified_success_webhook_refetches_and_grants_entitlement(tmp_path) -> None:
    app, store, _, purchase, provider = _setup(tmp_path)
    with TestClient(app, client=("185.71.76.3", 50000)) as client:
        response = client.post("/api/v1/webhooks/payments/yookassa", json=_notification())
        duplicate = client.post("/api/v1/webhooks/payments/yookassa", json=_notification())

    assert response.status_code == 200
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "duplicate"
    assert provider.lookup_calls == ["payment_123"]
    assert store.has_entitlement(str(purchase["chart_id"])) is True


def test_success_webhook_can_attach_purchase_from_verified_metadata(tmp_path) -> None:
    app, store, _, purchase, provider = _setup(tmp_path, link_provider_payment=False)
    with TestClient(app, client=("185.71.76.3", 50000)) as client:
        response = client.post("/api/v1/webhooks/payments/yookassa", json=_notification())

    assert response.status_code == 200
    assert provider.lookup_calls == ["payment_123"]
    saved = store.get_purchase(str(purchase["id"]))
    assert saved is not None
    assert saved["provider_payment_id"] == "payment_123"
    assert saved["status"] == "succeeded"
    assert store.has_entitlement(str(purchase["chart_id"])) is True


def test_spoofed_forwarded_address_is_rejected(tmp_path) -> None:
    app, store, _, purchase, provider = _setup(tmp_path)
    with TestClient(app, client=("203.0.113.10", 50000)) as client:
        response = client.post(
            "/api/v1/webhooks/payments/yookassa",
            json=_notification(),
            headers={"X-Forwarded-For": "185.71.76.3"},
        )

    assert response.status_code == 403
    assert provider.lookup_calls == []
    assert store.has_entitlement(str(purchase["chart_id"])) is False


def test_trusted_proxy_can_forward_real_yookassa_address(tmp_path) -> None:
    app, store, _, purchase, _ = _setup(tmp_path, trusted_proxy=True)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        response = client.post(
            "/api/v1/webhooks/payments/yookassa",
            json=_notification(),
            headers={"X-Forwarded-For": "203.0.113.44, 185.71.76.3"},
        )

    assert response.status_code == 200
    assert store.has_entitlement(str(purchase["chart_id"])) is True


def test_invalid_and_unsupported_notifications_never_change_access(tmp_path) -> None:
    app, store, _, purchase, provider = _setup(tmp_path)
    with TestClient(app, client=("185.71.76.3", 50000)) as client:
        invalid = client.post(
            "/api/v1/webhooks/payments/yookassa",
            content=b"{broken",
            headers={"Content-Type": "application/json"},
        )
        unsupported = client.post(
            "/api/v1/webhooks/payments/yookassa",
            json=_notification("payment.waiting_for_capture"),
        )

    assert invalid.status_code == 400
    assert unsupported.status_code == 200
    assert unsupported.json()["status"] == "ignored"
    assert provider.lookup_calls == []
    assert store.has_entitlement(str(purchase["chart_id"])) is False


def test_webhook_returns_503_when_provider_lookup_is_temporarily_unavailable(tmp_path) -> None:
    error = DomainError("PAYMENT_PROVIDER_TEMPORARY", "Временный сбой", status_code=503)
    app, store, _, purchase, _ = _setup(tmp_path, lambda _: error)
    with TestClient(app, client=("185.71.76.3", 50000)) as client:
        response = client.post("/api/v1/webhooks/payments/yookassa", json=_notification())

    assert response.status_code == 503
    assert store.has_entitlement(str(purchase["chart_id"])) is False


def test_mismatched_provider_amount_is_recorded_without_entitlement(tmp_path) -> None:
    app, store, _, purchase, _ = _setup(tmp_path, lambda item: _intent(item, amount_minor=98_000))
    with TestClient(app, client=("185.71.76.3", 50000)) as client:
        response = client.post("/api/v1/webhooks/payments/yookassa", json=_notification())

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PAYMENT_MISMATCH"
    assert store.has_entitlement(str(purchase["chart_id"])) is False
    assert store.payment_incidents(str(purchase["id"]))[0]["category"] == "webhook_mismatch"


def test_purchase_get_reconciles_once_and_uses_server_state(tmp_path) -> None:
    app, store, token, purchase, provider = _setup(tmp_path)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        client.cookies.set("vw_session", token)
        first = client.get(f"/api/v1/purchases/{purchase['id']}")
        second = client.get(f"/api/v1/purchases/{purchase['id']}")

    assert first.status_code == 200
    assert first.json()["status"] == "succeeded"
    assert second.json()["status"] == "succeeded"
    assert provider.lookup_calls == ["payment_123"]
    assert store.has_entitlement(str(purchase["chart_id"])) is True


def test_refund_success_webhook_is_refetched_and_revokes_full_entitlement(tmp_path) -> None:
    app, store, _, purchase, provider = _setup(tmp_path)
    store.apply_payment_event(
        str(purchase["id"]),
        provider_event_id="setup:succeeded:payment_123",
        event_type="payment.succeeded",
        object_id="payment_123",
        payload_checksum="setup",
        status="succeeded",
        provider_status="succeeded",
        provider_payment_id="payment_123",
        amount_minor=99_000,
        currency="RUB",
        metadata={
            "purchase_id": str(purchase["id"]),
            "chart_id": str(purchase["chart_id"]),
            "product_code": "full_report_v1",
        },
    )
    refund, _ = store.create_refund(
        str(purchase["id"]),
        idempotency_key="refund-key",
        amount_minor=99_000,
        reason="Полный возврат",
        actor_fingerprint="operator",
    )
    store.set_provider_refund(str(refund["id"]), provider_refund_id="refund_123", status="pending")
    provider.refund_intent = RefundIntent(
        provider="yookassa",
        provider_refund_id="refund_123",
        provider_payment_id="payment_123",
        status=RefundStatus.SUCCEEDED,
        amount_minor=99_000,
        currency="RUB",
        redacted_payload={"id": "refund_123", "status": "succeeded"},
    )

    with TestClient(app, client=("185.71.76.3", 50000)) as client:
        response = client.post(
            "/api/v1/webhooks/payments/yookassa",
            json={"type": "notification", "event": "refund.succeeded", "object": {"id": "refund_123"}},
        )

    assert response.status_code == 200
    assert store.get_purchase(str(purchase["id"]))["status"] == "refunded"  # type: ignore[index]
    assert store.has_entitlement(str(purchase["chart_id"])) is False
