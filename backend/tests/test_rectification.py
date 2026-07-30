from __future__ import annotations

from datetime import UTC, datetime

from vedicway_backend import rectification
from vedicway_backend.schemas import BirthInput, Place, ResolvedTime, TimeAccuracy


def _birth() -> BirthInput:
    return BirthInput(
        local_datetime=datetime(1990, 1, 10, 12, 0),
        place=Place(
            place_id="ru-moscow-524901",
            display_name="Москва, Россия",
            country_code="RU",
            latitude=55.7558,
            longitude=37.6173,
            tzid="Europe/Moscow",
        ),
        resolved_time=ResolvedTime(
            utc_offset_seconds=10_800,
            utc_datetime=datetime(1990, 1, 10, 9, 0, tzinfo=UTC),
            resolution_source="test",
        ),
        time_accuracy=TimeAccuracy.UNKNOWN,
    )


def _chart(input_value: BirthInput) -> dict[str, object]:
    ascendant_sign = 0 if input_value.local_datetime.hour < 9 else 6
    planets = [
        {"planet": "Sun", "rasi_index": 9},
        {"planet": "Moon", "rasi_index": 3},
        {"planet": "Mars", "rasi_index": 0},
        {"planet": "Mercury", "rasi_index": 9},
        {"planet": "Jupiter", "rasi_index": 4},
        {"planet": "Venus", "rasi_index": 6},
        {"planet": "Saturn", "rasi_index": 9},
        {"planet": "Rahu", "rasi_index": 10},
        {"planet": "Ketu", "rasi_index": 4},
    ]
    return {
        "ascendant": {"rasi_index": ascendant_sign},
        "planets": planets,
    }


def _dashas(input_value: BirthInput, include_antara: bool = True) -> dict[str, object]:
    favorable = input_value.local_datetime.hour < 9
    return {
        "maha_dashas": [
            {
                "lord": "Jupiter" if favorable else "Ketu",
                "start": "1990-01-01 00:00:00",
                "end": "2110-01-01 00:00:00",
                "sub_periods": [
                    {
                        "lord": "Venus" if favorable else "Rahu",
                        "start": "1990-01-01 00:00:00",
                        "end": "2110-01-01 00:00:00",
                    }
                ],
            }
        ]
    }


def test_rectification_is_deterministic_and_keeps_holdout_out_of_fit(monkeypatch) -> None:
    api = {
        "get_rasi_chart": _chart,
        "get_vimsottari_dasha": _dashas,
        "get_divisional_chart": lambda input_value, divisor: {
            "ascendant": {"rasi_index": 0 if input_value.local_datetime.hour < 9 else 6}
        },
    }
    monkeypatch.setattr(rectification, "_load_pyjhora", lambda: api)
    monkeypatch.setattr(rectification, "_birth_data", lambda birth, _: birth)
    answers = {
        "time_window": "morning",
        "events": [
            {"event_type": "education", "year": 2010, "month": 6},
            {"event_type": "career", "year": 2012, "month": 9},
            {"event_type": "marriage", "year": 2015, "month": 5},
            {"event_type": "relocation", "year": 2020, "month": None},
        ],
    }

    first = rectification.calculate_rectification(_birth(), answers)
    second = rectification.calculate_rectification(_birth(), answers)

    assert first == second
    assert first["selected_time"].startswith(("06:", "07:", "08:"))
    assert first["fit_event_count"] == 3
    assert first["holdout_event_count"] == 1
    assert first["candidate_count_scored"] == first["candidate_count_expected"]
    assert first["algorithm_version"] == "rectification.v1"
    best_minutes = int(first["selected_time"][:2]) * 60 + int(first["selected_time"][3:])
    assert all(
        abs(int(item["time"][:2]) * 60 + int(item["time"][3:]) - best_minutes) >= 10
        for item in first["alternatives"]
    )
