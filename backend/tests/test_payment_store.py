from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from vedicway_backend.errors import DomainError
from vedicway_backend.schemas import BirthInput, Place, ResolvedTime, TimeAccuracy
from vedicway_backend.store import Store


def _chart(store: Store) -> str:
    session_id, _ = store.create_session()
    birth = BirthInput(
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
    chart_id, _ = store.create_chart(session_id, birth, "chart-key")
    return chart_id


def _purchase(store: Store, chart_id: str, key: str = "client-key") -> dict[str, object]:
    purchase, created = store.create_purchase(
        chart_id,
        key,
        "buyer@example.com",
        product_code="full_report_v1",
        provider="yookassa",
        offer_version="2026-07-18",
    )
    assert created is True
    return purchase


def _succeed(store: Store, purchase: dict[str, object], event_id: str = "payment.succeeded:payment_123") -> None:
    store.set_provider_payment(
        str(purchase["id"]),
        "yookassa",
        "payment_123",
        status="pending",
        checkout_url="https://yoomoney.ru/checkout/token",
        provider_status="pending",
        redacted_payload={"id": "payment_123", "status": "pending"},
    )
    transition = store.apply_payment_event(
        str(purchase["id"]),
        provider_event_id=event_id,
        event_type="payment.succeeded",
        object_id="payment_123",
        payload_checksum="checksum-success",
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
    assert transition["duplicate"] is False


def test_purchase_persists_provider_key_before_external_call_and_reuses_active_order(tmp_path) -> None:
    store = Store(tmp_path / "runtime")
    chart_id = _chart(store)

    purchase = _purchase(store, chart_id)
    duplicate, duplicate_created = store.create_purchase(
        chart_id,
        "client-key",
        "buyer@example.com",
        product_code="full_report_v1",
        provider="yookassa",
        offer_version="2026-07-18",
    )
    active, active_created = store.create_purchase(
        chart_id,
        "different-client-key",
        "buyer@example.com",
        product_code="full_report_v1",
        provider="yookassa",
        offer_version="2026-07-18",
    )

    assert purchase["status"] == "created"
    provider_key = UUID(str(purchase["provider_idempotency_key"]))
    assert provider_key.version == 4
    assert str(provider_key) == purchase["provider_idempotency_key"]
    assert duplicate["id"] == purchase["id"]
    assert duplicate_created is False
    assert active["id"] == purchase["id"]
    assert active_created is False
    assert store.get_purchase_email(str(purchase["id"])) == "buyer@example.com"


def test_provider_response_is_persisted_without_secret_payload(tmp_path) -> None:
    store = Store(tmp_path / "runtime")
    purchase = _purchase(store, _chart(store))

    store.set_provider_payment(
        str(purchase["id"]),
        "yookassa",
        "payment_123",
        status="pending",
        checkout_url="https://yoomoney.ru/checkout/token",
        provider_status="pending",
        redacted_payload={"id": "payment_123", "status": "pending"},
    )

    saved = store.get_purchase(str(purchase["id"]))
    assert saved is not None
    assert saved["provider_payment_id"] == "payment_123"
    assert saved["checkout_url"] == "https://yoomoney.ru/checkout/token"
    assert saved["provider_status"] == "pending"
    assert saved["provider_payload_json"] == '{"id":"payment_123","status":"pending"}'


def test_success_transition_is_idempotent_and_grants_one_entitlement(tmp_path) -> None:
    store = Store(tmp_path / "runtime")
    purchase = _purchase(store, _chart(store))
    _succeed(store, purchase)

    duplicate = store.apply_payment_event(
        str(purchase["id"]),
        provider_event_id="payment.succeeded:payment_123",
        event_type="payment.succeeded",
        object_id="payment_123",
        payload_checksum="checksum-success",
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

    saved = store.get_purchase(str(purchase["id"]))
    events = [event for event in store.events_since(str(purchase["chart_id"])) if event.event == "entitlement.granted"]
    assert duplicate["duplicate"] is True
    assert saved is not None and saved["status"] == "succeeded"
    assert saved["paid_amount_minor"] == 99_000
    assert store.has_entitlement(str(purchase["chart_id"])) is True
    assert store.get_chart_resource(str(purchase["chart_id"]), include_paid=True)["entitlement"] == {
        "report_full": True,
        "report_ready": False,
    }
    assert len(events) == 1


def test_payment_mismatch_never_grants_entitlement(tmp_path) -> None:
    store = Store(tmp_path / "runtime")
    purchase = _purchase(store, _chart(store))
    store.set_provider_payment(str(purchase["id"]), "yookassa", "payment_123")

    with pytest.raises(DomainError, match="сумм") as captured:
        store.apply_payment_event(
            str(purchase["id"]),
            provider_event_id="payment.succeeded:payment_123",
            event_type="payment.succeeded",
            object_id="payment_123",
            payload_checksum="checksum-mismatch",
            status="succeeded",
            provider_status="succeeded",
            provider_payment_id="payment_123",
            amount_minor=98_000,
            currency="RUB",
            metadata={"purchase_id": str(purchase["id"])},
        )

    assert captured.value.code == "PAYMENT_MISMATCH"
    assert store.has_entitlement(str(purchase["chart_id"])) is False


def test_canceled_purchase_allows_a_new_attempt(tmp_path) -> None:
    store = Store(tmp_path / "runtime")
    chart_id = _chart(store)
    purchase = _purchase(store, chart_id)
    store.set_provider_payment(str(purchase["id"]), "yookassa", "payment_123")

    store.apply_payment_event(
        str(purchase["id"]),
        provider_event_id="payment.canceled:payment_123",
        event_type="payment.canceled",
        object_id="payment_123",
        payload_checksum="checksum-canceled",
        status="cancelled",
        provider_status="canceled",
        provider_payment_id="payment_123",
        amount_minor=99_000,
        currency="RUB",
        metadata={"purchase_id": str(purchase["id"])},
        failure_code="expired_on_confirmation",
    )
    replacement, created = store.create_purchase(
        chart_id,
        "new-client-key",
        "buyer@example.com",
        product_code="full_report_v1",
        provider="yookassa",
        offer_version="2026-07-18",
    )

    assert store.get_purchase(str(purchase["id"]))["status"] == "cancelled"  # type: ignore[index]
    assert created is True
    assert replacement["id"] != purchase["id"]


def test_partial_then_full_refund_updates_purchase_and_revokes_entitlement(tmp_path) -> None:
    store = Store(tmp_path / "runtime")
    purchase = _purchase(store, _chart(store))
    _succeed(store, purchase)

    first, created = store.create_refund(
        str(purchase["id"]),
        idempotency_key="refund-one",
        amount_minor=30_000,
        reason="Частичный возврат",
        actor_fingerprint="actor-hash",
    )
    duplicate, duplicate_created = store.create_refund(
        str(purchase["id"]),
        idempotency_key="refund-one",
        amount_minor=30_000,
        reason="Частичный возврат",
        actor_fingerprint="actor-hash",
    )
    store.set_provider_refund(
        str(first["id"]),
        provider_refund_id="refund_1",
        status="pending",
        receipt_registration="pending",
    )
    store.apply_refund_event(
        str(first["id"]),
        provider_event_id="refund.succeeded:refund_1",
        event_type="refund.succeeded",
        object_id="refund_1",
        payload_checksum="checksum-refund-1",
        status="succeeded",
        provider_payment_id="payment_123",
        amount_minor=30_000,
        currency="RUB",
    )

    after_partial = store.get_purchase(str(purchase["id"]))
    assert UUID(str(first["provider_idempotency_key"])).version == 4
    assert created is True
    assert duplicate_created is False
    assert duplicate["id"] == first["id"]
    assert after_partial is not None and after_partial["status"] == "partially_refunded"
    assert after_partial["refunded_amount_minor"] == 30_000
    assert store.has_entitlement(str(purchase["chart_id"])) is True

    second, _ = store.create_refund(
        str(purchase["id"]),
        idempotency_key="refund-two",
        amount_minor=69_000,
        reason="Возврат остатка",
        actor_fingerprint="actor-hash",
    )
    store.set_provider_refund(str(second["id"]), provider_refund_id="refund_2", status="pending")
    store.apply_refund_event(
        str(second["id"]),
        provider_event_id="refund.succeeded:refund_2",
        event_type="refund.succeeded",
        object_id="refund_2",
        payload_checksum="checksum-refund-2",
        status="succeeded",
        provider_payment_id="payment_123",
        amount_minor=69_000,
        currency="RUB",
    )

    after_full = store.get_purchase(str(purchase["id"]))
    assert after_full is not None and after_full["status"] == "refunded"
    assert after_full["refunded_amount_minor"] == 99_000
    assert store.has_entitlement(str(purchase["chart_id"])) is False
    revoked = [event for event in store.events_since(str(purchase["chart_id"])) if event.event == "entitlement.revoked"]
    assert len(revoked) == 1


def test_refund_cannot_leave_less_than_one_ruble(tmp_path) -> None:
    store = Store(tmp_path / "runtime")
    purchase = _purchase(store, _chart(store))
    _succeed(store, purchase)

    with pytest.raises(DomainError) as captured:
        store.create_refund(
            str(purchase["id"]),
            idempotency_key="invalid-refund",
            amount_minor=98_950,
            reason="Недопустимый остаток",
            actor_fingerprint="actor-hash",
        )

    assert captured.value.code == "REFUND_AMOUNT_INVALID"
