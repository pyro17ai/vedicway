from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from vedicway_backend.errors import DomainError
from vedicway_backend.main import create_app
from vedicway_backend.payment_config import PaymentSettings
from vedicway_backend.payments import PaymentIntent, PaymentProvider, PaymentStatus, RefundIntent
from vedicway_backend.schemas import BirthInput, Place, ResolvedTime, TimeAccuracy
from vedicway_backend.store import Store
from vedicway_backend.worker import ChartWorker


class RecordingProvider(PaymentProvider):
    name = "test"

    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.calls: list[dict[str, object]] = []
        self.closed = False

    async def create_payment(self, **kwargs) -> PaymentIntent:  # type: ignore[no-untyped-def]
        self.calls.append(dict(kwargs))
        if len(self.calls) <= self.failures:
            raise DomainError(
                "PAYMENT_PROVIDER_TEMPORARY",
                "Платёжный сервис временно не отвечает.",
                status_code=503,
            )
        return PaymentIntent(
            provider=self.name,
            provider_payment_id="payment_123",
            status=PaymentStatus.PENDING,
            checkout_url="https://yoomoney.ru/checkout/token",
            amount_minor=int(kwargs["amount_minor"]),
            currency=str(kwargs["currency"]),
            metadata={
                "purchase_id": str(kwargs["purchase_id"]),
                "chart_id": str(kwargs["chart_id"]),
                "product_code": str(kwargs["product_code"]),
            },
            redacted_payload={"id": "payment_123", "status": "pending"},
        )

    async def get_payment(self, provider_payment_id: str) -> PaymentIntent:
        raise NotImplementedError

    async def refund(self, **kwargs) -> RefundIntent:  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def get_refund(self, provider_refund_id: str) -> RefundIntent:
        raise NotImplementedError

    def normalize_status(self, value: str) -> PaymentStatus:
        return PaymentStatus(value)

    async def aclose(self) -> None:
        self.closed = True


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


def _client(tmp_path, provider: RecordingProvider) -> tuple[TestClient, Store, str, PaymentSettings]:
    store = Store(tmp_path / "runtime")
    session_id, token = store.create_session()
    chart_id, _ = store.create_chart(session_id, _birth(), "chart-key")
    store.get_snapshot = lambda _: object()  # type: ignore[method-assign,assignment]
    settings = PaymentSettings.from_environment()
    app = create_app(
        store=store,
        worker=ChartWorker(store),
        payment_settings=settings,
        payment_provider=provider,
    )
    client = TestClient(app)
    client.cookies.set("vw_session", token)
    return client, store, chart_id, settings


def _payload(settings: PaymentSettings) -> dict[str, object]:
    return {
        "product_code": "full_report_v1",
        "email": "buyer@example.com",
        "offer_accepted": True,
        "offer_version": settings.offer_version,
    }


def test_purchase_requires_email_and_current_offer(tmp_path) -> None:
    provider = RecordingProvider()
    client, _, chart_id, settings = _client(tmp_path, provider)
    with client:
        missing = client.post(
            f"/api/v1/charts/{chart_id}/purchases",
            json={},
            headers={"Idempotency-Key": "missing"},
        )
        stale = client.post(
            f"/api/v1/charts/{chart_id}/purchases",
            json={**_payload(settings), "offer_version": "old"},
            headers={"Idempotency-Key": "stale"},
        )

    assert missing.status_code == 400
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "OFFER_VERSION_MISMATCH"
    assert provider.calls == []


def test_purchase_uses_server_catalog_and_persisted_provider_key(tmp_path) -> None:
    provider = RecordingProvider()
    client, store, chart_id, settings = _client(tmp_path, provider)
    with client:
        response = client.post(
            f"/api/v1/charts/{chart_id}/purchases",
            json=_payload(settings),
            headers={"Idempotency-Key": "checkout-one"},
        )

    assert response.status_code == 202
    body = response.json()
    assert body == {
        "purchase_id": body["purchase_id"],
        "chart_id": chart_id,
        "product_code": "full_report_v1",
        "status": "pending",
        "checkout_url": "https://yoomoney.ru/checkout/token",
        "price_minor": 99_000,
        "currency": "RUB",
        "retryable": True,
    }
    saved = store.get_purchase(body["purchase_id"])
    assert saved is not None
    assert provider.calls[0]["amount_minor"] == 99_000
    assert provider.calls[0]["idempotency_key"] == saved["provider_idempotency_key"]
    assert "email" not in body
    assert "provider_payload_json" not in body


def test_duplicate_and_active_purchase_reuse_one_provider_payment(tmp_path) -> None:
    provider = RecordingProvider()
    client, _, chart_id, settings = _client(tmp_path, provider)
    with client:
        first = client.post(
            f"/api/v1/charts/{chart_id}/purchases",
            json=_payload(settings),
            headers={"Idempotency-Key": "checkout-one"},
        )
        duplicate = client.post(
            f"/api/v1/charts/{chart_id}/purchases",
            json=_payload(settings),
            headers={"Idempotency-Key": "checkout-one"},
        )
        active = client.post(
            f"/api/v1/charts/{chart_id}/purchases",
            json=_payload(settings),
            headers={"Idempotency-Key": "checkout-two"},
        )

    assert first.json()["purchase_id"] == duplicate.json()["purchase_id"] == active.json()["purchase_id"]
    assert len(provider.calls) == 1


def test_already_entitled_chart_cannot_open_checkout(tmp_path) -> None:
    provider = RecordingProvider()
    client, store, chart_id, settings = _client(tmp_path, provider)
    store.has_entitlement = lambda _: True  # type: ignore[method-assign]
    with client:
        response = client.post(
            f"/api/v1/charts/{chart_id}/purchases",
            json=_payload(settings),
            headers={"Idempotency-Key": "checkout"},
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ALREADY_ENTITLED"


def test_ambiguous_provider_failure_is_recoverable_with_same_provider_key(tmp_path) -> None:
    provider = RecordingProvider(failures=1)
    client, store, chart_id, settings = _client(tmp_path, provider)
    with client:
        ambiguous = client.post(
            f"/api/v1/charts/{chart_id}/purchases",
            json=_payload(settings),
            headers={"Idempotency-Key": "checkout"},
        )
        recovered = client.post(
            f"/api/v1/charts/{chart_id}/purchases",
            json=_payload(settings),
            headers={"Idempotency-Key": "checkout-retry"},
        )

    assert ambiguous.status_code == 202
    assert ambiguous.json()["status"] == "unknown"
    assert ambiguous.json()["checkout_url"] is None
    assert recovered.status_code == 202
    assert recovered.json()["status"] == "pending"
    assert recovered.json()["purchase_id"] == ambiguous.json()["purchase_id"]
    assert provider.calls[0]["idempotency_key"] == provider.calls[1]["idempotency_key"]
    assert store.get_purchase(recovered.json()["purchase_id"])["status"] == "pending"  # type: ignore[index]


def test_provider_is_closed_by_application_lifespan(tmp_path) -> None:
    provider = RecordingProvider()
    client, _, _, _ = _client(tmp_path, provider)
    with client:
        assert provider.closed is False
    assert provider.closed is True
