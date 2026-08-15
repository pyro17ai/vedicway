from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

import vedicway_backend.main as main_module
from vedicway_backend.errors import DomainError
from vedicway_backend.main import create_app
from vedicway_backend.schemas import (
    BirthInput,
    PdfRenderPreferences,
    Place,
    ResolvedTime,
    TimeAccuracy,
)
from vedicway_backend.store import Store


class NoopWorker:
    def drain(self, limit: int = 16) -> int:
        return 0


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


def _chart(store: Store) -> tuple[str, str, str]:
    session_id, token = store.create_session()
    chart_id, _ = store.create_chart(session_id, _birth(), "resource-limits")
    return session_id, token, chart_id


def test_pdf_enqueue_deduplicates_matching_active_request(tmp_path) -> None:
    store = Store(tmp_path / "runtime")
    _, _, chart_id = _chart(store)
    preferences = PdfRenderPreferences().model_dump(mode="json")

    first = store.enqueue_pdf_job(chart_id, preferences)
    second = store.enqueue_pdf_job(chart_id, preferences)

    assert second == first
    with store._connection() as connection:
        assert (
            connection.execute(
                """SELECT COUNT(*) AS count FROM pdf_render_requests
                   WHERE chart_id = %s""",
                (chart_id,),
            ).fetchone()["count"]
            == 1
        )
        assert (
            connection.execute(
                """SELECT COUNT(*) AS count FROM jobs
                   WHERE chart_id = %s AND job_type = 'pdf_v1'""",
                (chart_id,),
            ).fetchone()["count"]
            == 1
        )


def test_pdf_enqueue_rejects_different_preferences_while_active(tmp_path) -> None:
    store = Store(tmp_path / "runtime")
    _, _, chart_id = _chart(store)
    store.enqueue_pdf_job(
        chart_id,
        PdfRenderPreferences(varga="D1").model_dump(mode="json"),
    )

    with pytest.raises(DomainError) as error:
        store.enqueue_pdf_job(
            chart_id,
            PdfRenderPreferences(varga="D24").model_dump(mode="json"),
        )

    assert error.value.code == "PDF_RENDER_IN_PROGRESS"
    assert error.value.status_code == 409


def test_pdf_enqueue_limits_chart_to_ten_renders_per_day(tmp_path) -> None:
    store = Store(tmp_path / "runtime")
    _, _, chart_id = _chart(store)
    preferences = PdfRenderPreferences().model_dump(mode="json")
    for _ in range(10):
        _, request_id = store.enqueue_pdf_job(chart_id, preferences)
        store.update_pdf_render_request(request_id, "failed")

    with pytest.raises(DomainError) as error:
        store.enqueue_pdf_job(chart_id, preferences)

    assert error.value.code == "PDF_RENDER_LIMIT"
    assert error.value.status_code == 429


def test_sse_rejects_fourth_connection_for_session(tmp_path) -> None:
    store = Store(tmp_path / "runtime")
    session_id, token, chart_id = _chart(store)
    app = create_app(store=store, worker=NoopWorker())
    app.state.sse_connections[session_id] = main_module.SSE_CONNECTION_LIMIT

    with TestClient(app) as client:
        client.cookies.set("vw_session", token)
        response = client.get(f"/api/v1/charts/{chart_id}/events")

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "SSE_CONNECTION_LIMIT"


def test_sse_releases_connection_after_stream_ends(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(main_module, "SSE_MAX_LIFETIME_SECONDS", 0)
    store = Store(tmp_path / "runtime")
    session_id, token, chart_id = _chart(store)
    app = create_app(store=store, worker=NoopWorker())

    with TestClient(app) as client:
        client.cookies.set("vw_session", token)
        response = client.get(f"/api/v1/charts/{chart_id}/events")

    assert response.status_code == 200
    assert session_id not in app.state.sse_connections
