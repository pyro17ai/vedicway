from __future__ import annotations

import os
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from vedicway_backend.calculator import (
    calculate_extended,
    calculate_instant,
    validate_instant_runtime,
)
from vedicway_backend.evidence import compile_evidence
from vedicway_backend.places import PlaceRegistry
from vedicway_backend.schemas import ChartCreateRequest, ChartSnapshot
from vedicway_backend.time_normalization import resolve_birth_input

PYJHORA_SOURCE = Path(os.environ.get("VEDICWAY_PYJHORA_SOURCE", r"C:\Users\Huawei\.codex\mcp\pyjhora-mcp\src"))


@pytest.mark.skipif(not PYJHORA_SOURCE.exists(), reason="own PyJHora source is required")
def test_golden_moscow_lahiri_chart() -> None:
    assert validate_instant_runtime().startswith("cs_")
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
    evidence_snapshot = enriched.model_copy(update={"created_at": datetime(2026, 7, 18, tzinfo=UTC)})
    facts, packets = compile_evidence(evidence_snapshot)
    assert len({fact.id for fact in facts}) == len(facts)
    period_packet = next(packet for packet in packets if packet.slug.value == "current_period")
    period_facts = {fact.id: fact for fact in facts}
    active = [period_facts[fact_id] for fact_id in period_packet.primary_facts + period_packet.confirming_facts]
    assert {fact.human_label_ru for fact in active if fact.kind != "dasha_timeline"} == {
        "Активная махадаша Вимшоттари: Венера",
        "Активная антардаша Вимшоттари: Раху",
    }
    timeline = next(fact for fact in active if fact.kind == "dasha_timeline")
    assert timeline.value["mahadashas"][0]["status"] == "current"
    assert any(period["status"] == "future" for period in timeline.value["mahadashas"])
