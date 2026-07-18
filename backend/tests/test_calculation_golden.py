from __future__ import annotations

from datetime import date

import pytest

from vedicway_backend.calculator import calculate_extended, calculate_instant
from vedicway_backend.places import PlaceRegistry
from vedicway_backend.schemas import ChartCreateRequest, ChartSnapshot
from vedicway_backend.time_normalization import resolve_birth_input


@pytest.mark.skipif(not __import__("os").environ.get("VEDICWAY_PYJHORA_SOURCE"), reason="own PyJHora source is required")
def test_golden_moscow_lahiri_chart() -> None:
    request = ChartCreateRequest(local_date=date(2006, 10, 16), local_time="13:30", place_id="ru-moscow-524901")
    birth = resolve_birth_input(request, PlaceRegistry().get(request.place_id))
    snapshot = calculate_instant(birth, "chart_golden")
    assert snapshot.sections["panchanga"]["status"] == "queued"
    assert snapshot.sections["dashas"]["status"] == "queued"
    extended = calculate_extended(birth, snapshot)
    assert extended["panchanga"]["data"]["vaara"] == "Monday"
    d1 = snapshot.sections["d1"]["data"]
    assert d1["ascendant"]["sign_label"] == "Скорпион"
    assert d1["ascendant"]["longitude_in_sign"] == pytest.approx(23.7133, abs=0.0001)
    positions = {planet["planet_code"]: planet for cell in d1["cells"] for planet in cell["planets"]}
    assert positions["MOON"]["sign_label"] == "Рак"
    assert positions["MOON"]["longitude_in_sign"] == pytest.approx(25.7398, abs=0.0001)
    assert positions["RAHU"]["sign_label"] == "Рыбы"
    assert positions["RAHU"]["longitude_in_sign"] == pytest.approx(1.1941, abs=0.0001)
    assert positions["KETU"]["sign_label"] == "Дева"
    snapshot_data = snapshot.model_dump(mode="json")
    snapshot_data["sections"].update(extended)
    enriched = ChartSnapshot.model_validate(snapshot_data)
    assert enriched.sections["D9"]["data"]["ascendant"]["sign_label"] == "Водолей"
    assert enriched.sections["D9"]["data"]["ascendant"]["longitude_in_sign"] == pytest.approx(3.4194, abs=0.0001)
    assert enriched.sections["D10"]["data"]["ascendant"]["sign_label"] == "Дева"
    assert enriched.sections["D10"]["data"]["ascendant"]["longitude_in_sign"] == pytest.approx(27.1326, abs=0.0001)
