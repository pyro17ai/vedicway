from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vedicway_backend.legal_config import LEGAL_DOCUMENT_VERSIONS
from vedicway_backend.main import create_app
from vedicway_backend.pdf import report_html
from vedicway_backend.schemas import PdfRenderPreferences
from vedicway_backend.store import Store
from vedicway_backend.worker import ChartWorker

PYJHORA_SOURCE = Path(
    os.environ.get("VEDICWAY_PYJHORA_SOURCE", r"C:\Users\Huawei\.codex\mcp\pyjhora-mcp\src")
)
LEGAL = {
    "personal_data": True,
    "personal_data_version": LEGAL_DOCUMENT_VERSIONS["personal_data_consent"],
    "terms": True,
    "terms_version": LEGAL_DOCUMENT_VERSIONS["terms"],
}


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


@pytest.mark.skipif(not PYJHORA_SOURCE.exists(), reason="own PyJHora source is required")
def test_complete_chart_payment_and_pdf_flow(tmp_path) -> None:
    store = Store(tmp_path / "runtime")
    app = create_app(store=store, worker=ChartWorker(store))
    with TestClient(app) as client:
        payload = {
            "local_date": "2006-10-16",
            "local_time": "13:30",
            "place_id": "ru-moscow-524901",
            "time_accuracy": "exact",
            "legal": LEGAL,
        }
        first = client.post(
            "/api/v1/charts", json=payload, headers={"Idempotency-Key": "chart-idempotency"}
        )
        assert first.status_code == 202
        chart_id = first.json()["chart_id"]
        assert client.cookies.get("vw_session")
        duplicate = client.post(
            "/api/v1/charts", json=payload, headers={"Idempotency-Key": "chart-idempotency"}
        )
        assert duplicate.json()["chart_id"] == chart_id
        resource = _wait_for(client, chart_id, lambda item: item["interpretation"] is not None)
        assert resource["sections"]["d1"] == "ready"
        assert resource["sections"]["vargas"] == "ready"
        assert resource["interpretation"]["schema_version"] == "interpretation.free.v1"
        assert all(not domain["paragraphs"] for domain in resource["interpretation"]["domains"])
        question = resource["interpretation"]["questions"][0]
        saved = client.put(
            f"/api/v1/charts/{chart_id}/questions/{question['id']}",
            json={
                "saved": True,
                "reflection_status": "thinking",
                "note": "Вернуться к этой теме после разговора.",
            },
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
        checkout_url = purchase.json()["checkout_url"]
        checkout = client.get(checkout_url)
        assert checkout.status_code == 200
        assert "Тестовая оплата YooKassa" in checkout.text
        confirmation = client.post(f"{checkout_url}/complete", follow_redirects=False)
        assert confirmation.status_code == 303
        assert (
            f"payment_return={purchase.json()['purchase_id']}" in confirmation.headers["location"]
        )
        resource = _wait_for(
            client,
            chart_id,
            lambda item: (
                item["interpretation"] is not None
                and item["interpretation"]["schema_version"] == "interpretation.paid.v1"
                and item["pdf"]["status"] == "ready"
            ),
        )
        assert resource["entitlement"]["report_full"] is True
        assert resource["entitlement"]["report_ready"] is True
        assert len(resource["interpretation"]["questions"]) == 12
        assert resource["interpretation"]["domains"][0]["paragraphs"]
        requested = client.post(
            f"/api/v1/charts/{chart_id}/reports/pdf",
            json={
                "preferences": {
                    "schema_version": "pdf-render-preferences.v1",
                    "varga": "D24",
                    "mode": "expert",
                    "chart_style": "south_indian",
                }
            },
        )
        assert requested.status_code == 202
        render_request_id = requested.json()["render_request_id"]
        resource = _wait_for(
            client,
            chart_id,
            lambda item: (
                item["pdf"]["status"] == "ready"
                and item["pdf"].get("render_request_id") == render_request_id
            ),
        )
        assert resource["pdf"]["render_preferences"]["varga"] == "D24"
        assert resource["pdf"]["render_preferences"]["mode"] == "expert"
        immutable_request = store.get_pdf_render_request(render_request_id)
        assert immutable_request is not None
        assert immutable_request["preferences"]["varga"] == "D24"
        exact_status = client.get(
            f"/api/v1/charts/{chart_id}/reports/pdf/requests/{render_request_id}"
        )
        assert exact_status.status_code == 200
        assert exact_status.json()["render_request_id"] == render_request_id
        assert exact_status.json()["preferences"]["mode"] == "expert"
        snapshot = store.get_snapshot(chart_id)
        bundle = store.get_bundle(chart_id, paid=True)
        assert snapshot is not None and bundle is not None
        html = report_html(
            snapshot, bundle, PdfRenderPreferences.model_validate(immutable_request["preferences"])
        )
        assert "Натальная карта · D24" in html
        assert "Профессиональный" in html
        pdf = client.get(
            f"/api/v1/charts/{chart_id}/reports/pdf",
            params={"render_request_id": render_request_id},
            follow_redirects=False,
        )
        assert pdf.status_code == 303
        assert f"render_request_id={render_request_id}" in pdf.headers["location"]
        download = client.get(pdf.headers["location"])
        assert download.status_code == 200
        assert download.headers["content-type"].startswith("application/pdf")
        wrong_render = client.get(
            pdf.headers["location"].replace(render_request_id, "pdfreq-substitution"),
        )
        assert wrong_render.status_code == 401


def test_magic_link_grants_new_browser_session(tmp_path) -> None:
    store = Store(tmp_path / "runtime")
    app = create_app(store=store, worker=ChartWorker(store))
    with TestClient(app) as owner:
        created = owner.post(
            "/api/v1/charts",
            json={
                "local_date": "2006-10-16",
                "local_time": "13:30",
                "place_id": "ru-moscow-524901",
                "legal": LEGAL,
            },
            headers={"Idempotency-Key": "magic-chart"},
        )
        chart_id = created.json()["chart_id"]
        token = store.create_magic_link(chart_id)
        with store._connection() as connection:
            magic_link = connection.execute(
                "SELECT created_at, expires_at FROM magic_links"
            ).fetchone()
        assert magic_link is not None
        assert (
            datetime.fromisoformat(magic_link["expires_at"])
            - datetime.fromisoformat(magic_link["created_at"])
        ) >= timedelta(minutes=59)
    with TestClient(app) as visitor:
        response = visitor.get(f"/api/v1/magic-links/{token}", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/access/confirm"
        assert visitor.cookies.get("vw_session") is None
        csrf = visitor.cookies.get("vw_magic_csrf")
        assert csrf
        confirmed = visitor.post(
            "/api/v1/magic-links/confirm",
            data={"csrf_token": csrf},
            headers={"Origin": "http://testserver"},
            follow_redirects=False,
        )
        assert confirmed.status_code == 303
        assert confirmed.headers["location"] == f"/chart/{chart_id}"
        assert visitor.cookies.get("vw_session")
        assert visitor.get(f"/api/v1/charts/{chart_id}").status_code == 200
