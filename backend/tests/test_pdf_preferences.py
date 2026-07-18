from __future__ import annotations

import pytest
from pydantic import ValidationError

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
