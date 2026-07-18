from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi.testclient import TestClient

from vedicway_backend.main import _launch_worker, create_app
from vedicway_backend.store import Store


def test_inline_worker_can_be_disabled_for_separate_worker_process(monkeypatch) -> None:
    monkeypatch.setenv("VEDICWAY_INLINE_WORKER", "0")
    app = SimpleNamespace(state=SimpleNamespace())

    asyncio.run(_launch_worker(app))

    assert not hasattr(app.state, "worker_task")


def test_production_readiness_rejects_unwarmed_calculation_runtime(tmp_path) -> None:
    app = create_app(store=Store(tmp_path / "runtime"))
    with TestClient(app) as client:
        app.state.production = True
        app.state.instant_runtime_ready = False
        app.state.instant_runtime_error = "EPHEMERIS_MISSING"
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["reason"] == "EPHEMERIS_MISSING"
