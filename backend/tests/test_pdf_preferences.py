from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from vedicway_backend.pdf import report_html
from vedicway_backend.schemas import PdfRenderPreferences


def test_pdf_preferences_are_allowlisted_and_frozen() -> None:
    preferences = PdfRenderPreferences(varga="D24", mode="expert")
    assert preferences.model_dump(mode="json") == {
        "schema_version": "pdf-render-preferences.v1",
        "varga": "D24",
        "mode": "expert",
        "chart_style": "south_indian",
    }
    with pytest.raises(ValidationError):
        preferences.varga = "D1"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        PdfRenderPreferences(varga="D999")


def test_paid_synthesis_is_rendered_and_escaped_in_pdf_html() -> None:
    snapshot = SimpleNamespace(
        birth={"local_date": "2000-01-01", "local_time": "12:00", "place": "Москва"},
        sections={
            "D9": {
                "data": {
                    "cells": [
                        {"sign_index": 0, "sign_label": "Овен", "is_lagna": True, "planets": []}
                    ]
                }
            }
        },
    )
    bundle = SimpleNamespace(
        overview=SimpleNamespace(summary="Краткий обзор карты."),
        domains=[],
        questions=[],
        global_limitations=[],
        synthesis=["Связный <персональный> синтез по разделам."],
    )

    html = report_html(snapshot, bundle, PdfRenderPreferences(varga="D9"))

    assert "<h2>Общий синтез</h2>" in html
    assert "Связный &lt;персональный&gt; синтез по разделам." in html
