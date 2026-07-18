from __future__ import annotations

import time

from fastapi.testclient import TestClient

from vedicway_backend.main import create_app
from vedicway_backend.store import Store
from vedicway_backend.worker import ChartWorker


def _wait_for(client: TestClient, chart_id: str, predicate, timeout: float = 12.0):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/charts/{chart_id}")
        assert response.status_code == 200
        last = response.json()
        if predicate(last):
            return last
        time.sleep(0.1)
    raise AssertionError(last)


def test_complete_chart_payment_and_pdf_flow(tmp_path) -> None:
    store = Store(tmp_path / "runtime")
    app = create_app(store=store, worker=ChartWorker(store))
    with TestClient(app) as client:
        payload = {"local_date": "2006-10-16", "local_time": "13:30", "place_id": "ru-moscow-524901", "time_accuracy": "exact"}
        first = client.post("/api/v1/charts", json=payload, headers={"Idempotency-Key": "chart-idempotency"})
        assert first.status_code == 202
        chart_id = first.json()["chart_id"]
        assert client.cookies.get("vw_session")
        duplicate = client.post("/api/v1/charts", json=payload, headers={"Idempotency-Key": "chart-idempotency"})
        assert duplicate.json()["chart_id"] == chart_id
        resource = _wait_for(client, chart_id, lambda item: item["interpretation"] is not None)
        assert resource["sections"]["d1"] == "ready"
        assert resource["sections"]["vargas"] == "ready"
        assert resource["interpretation"]["schema_version"] == "interpretation.free.v1"
        assert all(not domain["paragraphs"] for domain in resource["interpretation"]["domains"])
        question = resource["interpretation"]["questions"][0]
        saved = client.put(
            f"/api/v1/charts/{chart_id}/questions/{question['id']}",
            json={"saved": True, "reflection_status": "thinking", "note": "Вернуться к этой теме после разговора."},
        )
        assert saved.status_code == 200
        assert saved.json()["reflection_status"] == "thinking"
        saved_list = client.get(f"/api/v1/charts/{chart_id}/questions/saved")
        assert saved_list.json()["items"][0]["note"] == "Вернуться к этой теме после разговора."
        purchase = client.post(
            f"/api/v1/charts/{chart_id}/purchases",
            json={
                "email": "buyer@example.com",
                "offer_accepted": True,
                "offer_version": "development",
            },
            headers={"Idempotency-Key": "purchase-idempotency"},
        )
        assert purchase.status_code == 202
        confirmation = client.post(f"/api/v1/test/purchases/{purchase.json()['purchase_id']}/confirm")
        assert confirmation.status_code == 202
        resource = _wait_for(
            client,
            chart_id,
            lambda item: item["interpretation"] is not None and item["interpretation"]["schema_version"] == "interpretation.paid.v1" and item["pdf"]["status"] == "ready",
        )
        assert resource["entitlement"]["report_full"] is True
        assert len(resource["interpretation"]["questions"]) == 12
        assert resource["interpretation"]["domains"][0]["paragraphs"]
        pdf = client.get(f"/api/v1/charts/{chart_id}/reports/pdf", follow_redirects=False)
        assert pdf.status_code == 303
        download = client.get(pdf.headers["location"])
        assert download.status_code == 200
        assert download.headers["content-type"].startswith("application/pdf")


def test_magic_link_grants_new_browser_session(tmp_path) -> None:
    store = Store(tmp_path / "runtime")
    app = create_app(store=store, worker=ChartWorker(store))
    with TestClient(app) as owner:
        created = owner.post(
            "/api/v1/charts",
            json={"local_date": "2006-10-16", "local_time": "13:30", "place_id": "ru-moscow-524901"},
            headers={"Idempotency-Key": "magic-chart"},
        )
        chart_id = created.json()["chart_id"]
        token = store.create_magic_link(chart_id)
    with TestClient(app) as visitor:
        response = visitor.get(f"/api/v1/magic-links/{token}", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == f"/chart/{chart_id}"
        assert visitor.cookies.get("vw_session")
        assert visitor.get(f"/api/v1/charts/{chart_id}").status_code == 200
