from __future__ import annotations

import asyncio
from types import SimpleNamespace

from vedicway_backend.main import _launch_worker


def test_inline_worker_can_be_disabled_for_separate_worker_process(monkeypatch) -> None:
    monkeypatch.setenv("VEDICWAY_INLINE_WORKER", "0")
    app = SimpleNamespace(state=SimpleNamespace())

    asyncio.run(_launch_worker(app))

    assert not hasattr(app.state, "worker_task")
