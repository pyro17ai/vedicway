from __future__ import annotations

from datetime import UTC, datetime

import pytest
from cryptography.fernet import Fernet

from vedicway_backend.schemas import BirthInput, JobStatus, Place, ResolvedTime, TimeAccuracy
from vedicway_backend.store import Store


def _production_data_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VEDICWAY_ENV", "production")
    monkeypatch.setenv("VEDICWAY_DATA_KEY", Fernet.generate_key().decode("ascii"))
    monkeypatch.delenv("VEDICWAY_SIGNING_KEY", raising=False)


def test_production_store_requires_signing_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _production_data_key(monkeypatch)

    with pytest.raises(RuntimeError, match="VEDICWAY_SIGNING_KEY is required"):
        Store(tmp_path / "runtime")


def test_production_store_rejects_short_signing_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _production_data_key(monkeypatch)
    monkeypatch.setenv("VEDICWAY_SIGNING_KEY", "too-short")

    with pytest.raises(RuntimeError, match="at least 32 bytes"):
        Store(tmp_path / "runtime")


def _birth() -> BirthInput:
    return BirthInput(
        local_datetime=datetime(1998, 9, 15, 17, 28),
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
            utc_datetime=datetime(1998, 9, 15, 13, 28, tzinfo=UTC),
            resolution_source="test",
        ),
        time_accuracy=TimeAccuracy.EXACT,
    )


def test_public_birth_is_encrypted_at_rest(tmp_path) -> None:
    store = Store(tmp_path / "runtime")
    session_id, _ = store.create_session()
    chart_id, _ = store.create_chart(session_id, _birth(), "encrypted-birth")

    with store._connection() as connection:
        raw = connection.execute(
            "SELECT birth_public_json FROM charts WHERE id = %s", (chart_id,)
        ).fetchone()["birth_public_json"]

    assert raw.startswith("fernet:v1:")
    assert "1998-09-15" not in raw
    assert "Москва" not in raw
    assert store.get_chart_resource(chart_id)["birth"]["local_time"] == "17:28"


def test_legacy_public_birth_is_migrated_and_remains_readable(tmp_path) -> None:
    data_dir = tmp_path / "runtime"
    store = Store(data_dir)
    session_id, _ = store.create_session()
    chart_id, _ = store.create_chart(session_id, _birth(), "legacy-birth")
    legacy = '{"local_date":"1998-09-15","local_time":"17:28","place":"Москва, Россия"}'
    with store._connection() as connection:
        connection.execute(
            "UPDATE charts SET birth_public_json = %s WHERE id = %s", (legacy, chart_id)
        )

    reopened = Store(data_dir)
    assert reopened.get_chart_resource(chart_id)["birth"]["place"] == "Москва, Россия"
    with reopened._connection() as connection:
        migrated = connection.execute(
            "SELECT birth_public_json FROM charts WHERE id = %s", (chart_id,)
        ).fetchone()["birth_public_json"]
    assert migrated.startswith("fernet:v1:")
    assert "Москва" not in migrated


def test_failed_interpretation_is_not_reported_as_queued_forever(tmp_path) -> None:
    store = Store(tmp_path / "runtime")
    session_id, _ = store.create_session()
    chart_id, _ = store.create_chart(session_id, _birth(), "failed-interpretation")
    job_id = store.enqueue_job(chart_id, "interpretation_free_v1")
    store.update_job_status(
        job_id,
        JobStatus.FAILED_RETRYABLE,
        {"code": "INTERPRETATION_UNAVAILABLE", "recoverable": True},
    )

    resource = store.get_chart_resource(chart_id)

    assert resource["sections"]["interpretation"] == "error"
    assert resource["sections"]["questions"] == "error"
