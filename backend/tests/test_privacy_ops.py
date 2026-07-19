from __future__ import annotations

from datetime import date

from vedicway_backend.places import PlaceRegistry
from vedicway_backend.schemas import ChartCreateRequest
from vedicway_backend.store import Store
from vedicway_backend.time_normalization import resolve_birth_input


def _birth():
    request = ChartCreateRequest(
        local_date=date(1998, 9, 15),
        local_time="17:28",
        place_id="ru-moscow-524901",
    )
    return resolve_birth_input(request, PlaceRegistry().get(request.place_id))


def test_erasure_deletes_unpaid_chart_and_redacts_paid_chart(tmp_path) -> None:
    store = Store(tmp_path / "runtime")

    unpaid_session, _ = store.create_session()
    unpaid_chart, _ = store.create_chart(unpaid_session, _birth(), "unpaid")
    unpaid_result = store.erase_chart_personal_data(unpaid_chart)
    assert unpaid_result["hard_deleted"] is True
    with store._connection() as connection:
        assert connection.execute("SELECT 1 FROM charts WHERE id = ?", (unpaid_chart,)).fetchone() is None

    paid_session, _ = store.create_session()
    paid_chart, _ = store.create_chart(paid_session, _birth(), "paid")
    purchase, _ = store.create_purchase(paid_chart, "purchase", "receipt@example.ru")
    paid_result = store.erase_chart_personal_data(paid_chart)

    assert paid_result["financial_records_retained"] is True
    assert store.get_purchase_email(purchase["id"]) is None
    assert store.chart_owned_by(paid_chart, paid_session) is False
    with store._connection() as connection:
        chart = connection.execute("SELECT * FROM charts WHERE id = ?", (paid_chart,)).fetchone()
        profile = connection.execute(
            "SELECT encrypted_payload FROM birth_profiles WHERE id = ?",
            (chart["birth_profile_id"],),
        ).fetchone()
    assert chart["status"] == "erased"
    assert chart["soft_deleted_at"] is not None
    assert chart["snapshot_json"] is None
    assert store._decrypt(profile["encrypted_payload"]) == {"erased": True}
