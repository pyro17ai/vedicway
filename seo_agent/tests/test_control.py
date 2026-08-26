from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image

import seo_agent.control as control
from seo_agent.control import _render_pinterest_csv, dispatch
from seo_agent.db import LedgerError


@pytest.mark.parametrize(
    "action",
    [
        "generate-cover",
        "generate-pinterest-card",
        "quality-gate",
        "build-distribution",
        "verify-distribution",
    ],
)
def test_control_rejects_removed_responsibilities(action: str) -> None:
    with pytest.raises(LedgerError, match="Unsupported control action"):
        dispatch(action, {})


def test_control_rejects_unknown_actions() -> None:
    with pytest.raises(LedgerError, match="Unsupported control action"):
        dispatch("shell", {"command": "id"})


def test_control_records_a_short_log_for_the_active_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StubLedger:
        def record_run_log(self, run_id: str, log_text: str):
            return {"cron_run_id": run_id, "log_text": log_text}

    monkeypatch.setenv("VEDICWAY_SEO_RUN_ID", "run-log-test")
    monkeypatch.setattr(control, "AgentLedger", StubLedger)

    assert dispatch(
        "record-run-log",
        {"log_text": "Проверил очередь. Ошибок не возникло."},
    ) == {
        "cron_run_id": "run-log-test",
        "log_text": "Проверил очередь. Ошибок не возникло.",
    }


def test_pinterest_batch_claim_stops_after_the_first_empty_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StubLedger:
        def __init__(self) -> None:
            self.calls = 0

        def claim(self, entity: str, *, lease_seconds: int):
            assert entity == "pinterest-pin"
            assert lease_seconds == 3900
            self.calls += 1
            return None

    ledger = StubLedger()
    monkeypatch.setattr(control, "AgentLedger", lambda: ledger)

    assert dispatch("ledger-claim-pinterest-batch", {}) == {
        "items": [],
        "batch_size": 0,
        "complete": False,
    }
    assert ledger.calls == 1


def test_control_reports_unexpected_exception_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(control.sys, "stdin", io.StringIO("{}"))

    def fail(_action: str, _payload: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("upstream publish failed")

    monkeypatch.setattr(control, "dispatch", fail)

    assert control.main(["publish-site"]) == 2
    response = json.loads(capsys.readouterr().out)
    assert response == {
        "status": "error",
        "error": "Control action failed (RuntimeError): upstream publish failed",
    }


def test_generated_image_import_never_overwrites_an_existing_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    codex_home = tmp_path / "codex-home"
    generated = codex_home / "generated_images" / "source.png"
    generated.parent.mkdir(parents=True)
    Image.new("RGB", (1200, 630), (10, 20, 30)).save(generated, "PNG")
    data_dir = tmp_path / "seo-data"
    target = data_dir / "media" / "cover.webp"
    target.parent.mkdir(parents=True)
    Image.new("RGB", (1200, 630), (200, 190, 180)).save(target, "WEBP")
    original = target.read_bytes()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("VEDICWAY_SEO_DATA_DIR", str(data_dir))

    with pytest.raises(LedgerError, match="already exists"):
        dispatch(
            "import-generated-image",
            {
                "source_path": str(generated),
                "kind": "article-cover",
                "output": "media/cover.webp",
            },
        )

    assert target.read_bytes() == original


def test_pinterest_csv_contains_real_bytes_and_moves_late_runs_to_tomorrow() -> None:
    items = [
        {
            "title": f"Карточка {index}",
            "body": f"Описание {index}",
            "target_url": "https://vedicway.ru/blog/natalnaya-karta",
            "media_public_url": (
                f"https://vedicway.ru/media/articles/{index}/1200.webp"
            ),
        }
        for index in range(1, 11)
    ]

    content = _render_pinterest_csv(
        items,
        "Астрология VedicWay",
        now=datetime(2026, 8, 23, 16, 0, tzinfo=UTC),
    )
    rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))

    assert len(content) > 1000
    assert len(rows) == 11
    assert rows[0] == [
        "Title",
        "Media URL",
        "Pinterest board",
        "Thumbnail",
        "Description",
        "Link",
        "Publish date",
        "Keywords",
    ]
    assert rows[1][6] == "2026-08-24T13:00:00+03:00"
    assert rows[10][6] == "2026-08-24T22:00:00+03:00"
