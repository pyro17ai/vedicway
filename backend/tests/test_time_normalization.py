from __future__ import annotations

import json
from datetime import date

import pytest

from vedicway_backend.errors import DomainError
from vedicway_backend.places import PlaceRegistry
from vedicway_backend.schemas import ChartCreateRequest
from vedicway_backend.time_normalization import (
    normalize_event_time,
    parse_dasha_datetime,
    resolve_birth_input,
)


def test_moscow_historic_offset_uses_tzdb() -> None:
    request = ChartCreateRequest(local_date=date(2006, 10, 16), local_time="13:30", place_id="ru-moscow-524901")
    birth = resolve_birth_input(request, PlaceRegistry().get(request.place_id))
    assert birth.resolved_time.utc_offset_seconds == 4 * 3600
    assert birth.resolved_time.utc_datetime.isoformat() == "2006-10-16T09:30:00+00:00"


def test_nonexistent_and_ambiguous_local_time_are_explicit() -> None:
    registry = PlaceRegistry()
    place = registry.get("us-new-york-5128581")
    with pytest.raises(DomainError, match="существовало") as nonexistent:
        resolve_birth_input(ChartCreateRequest(local_date=date(2020, 3, 8), local_time="02:30", place_id=place.place_id), place)
    assert nonexistent.value.code == "NONEXISTENT_LOCAL_TIME"
    with pytest.raises(DomainError, match="два исторических") as ambiguous:
        resolve_birth_input(ChartCreateRequest(local_date=date(2020, 11, 1), local_time="01:30", place_id=place.place_id), place)
    assert ambiguous.value.code == "AMBIGUOUS_LOCAL_TIME"
    resolved = resolve_birth_input(ChartCreateRequest(local_date=date(2020, 11, 1), local_time="01:30", place_id=place.place_id, fold=1), place)
    assert resolved.resolved_time.fold == 1


def test_panchanga_extended_and_negative_times_keep_dates() -> None:
    negative = normalize_event_time("-20:33:39", date(2006, 10, 16), "Europe/Moscow")
    extended = normalize_event_time("35:41:10", date(2006, 10, 16), "Europe/Moscow")
    assert negative.local_date.isoformat() == "2006-10-15"
    assert negative.day_offset == -1
    assert negative.local_time == "03:26:21"
    assert extended.local_date.isoformat() == "2006-10-17"
    assert extended.day_offset == 1
    assert extended.local_time == "11:41:10"


def test_malformed_pyjhora_meridiem_normalizes_to_iso_time() -> None:
    normalized = parse_dasha_datetime("1997-08-18 20:06:09 PM", "Europe/Moscow")
    assert normalized is not None
    assert normalized.hour == 20
    assert normalized.isoformat().endswith("+04:00")


def test_registry_loads_local_dataset_and_searches_alternate_names(tmp_path) -> None:
    dataset = tmp_path / "licensed-places.json"
    dataset.write_text(
        json.dumps(
            {
                "places": [
                    {
                        "place_id": "de-munich-2867714",
                        "display_name": "Мюнхен, Германия",
                        "country_code": "DE",
                        "latitude": 48.1351,
                        "longitude": 11.582,
                        "tzid": "Europe/Berlin",
                        "alternate_names": ["Munich", "München"],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    registry = PlaceRegistry(dataset_path=dataset)
    assert registry.search("münchen")[0].place_id == "de-munich-2867714"
