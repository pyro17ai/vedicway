from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from vedicway_backend.constants import DomainSlug
from vedicway_backend.evidence import compile_evidence


def _planet(code: str, label: str, sign_index: int, house: int, chart: str) -> dict[str, object]:
    sign_labels = (
        "Овен",
        "Телец",
        "Близнецы",
        "Рак",
        "Лев",
        "Дева",
        "Весы",
        "Скорпион",
        "Стрелец",
        "Козерог",
        "Водолей",
        "Рыбы",
    )
    return {
        "planet_code": code,
        "label": label,
        "sign_index": sign_index,
        "sign_label": sign_labels[sign_index],
        "house_number": house,
        "longitude_in_sign": 12.5,
        "retrograde": False,
        "source_path": f"sections.{chart}.planets.{code.lower()}",
    }


def _chart(ascendant_sign: int, planets: list[dict[str, object]]) -> dict[str, object]:
    sign_labels = (
        "Овен",
        "Телец",
        "Близнецы",
        "Рак",
        "Лев",
        "Дева",
        "Весы",
        "Скорпион",
        "Стрелец",
        "Козерог",
        "Водолей",
        "Рыбы",
    )
    return {
        "status": "ready",
        "data": {
            "ascendant": {
                "sign_index": ascendant_sign,
                "sign_label": sign_labels[ascendant_sign],
                "longitude_in_sign": 5.0,
                "nakshatra": "Тестовая",
            },
            "cells": [{"planets": planets}],
        },
    }


def _period(lord: str, start: str, end: str, sub_periods: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {"lord": lord, "start": start, "end": end, "sub_periods": sub_periods or []}


def test_work_money_and_period_packets_include_required_factors_and_future_ranges() -> None:
    sections = {
        "d1": _chart(
            0,
            [
                _planet("SUN", "Солнце", 4, 5, "d1"),
                _planet("MOON", "Луна", 3, 4, "d1"),
                _planet("VENUS", "Венера", 1, 2, "d1"),
                _planet("SATURN", "Сатурн", 10, 11, "d1"),
            ],
        ),
        "D10": _chart(5, [_planet("SATURN", "Сатурн", 9, 5, "d10")]),
        "D2": _chart(
            3,
            [
                _planet("VENUS", "Венера", 4, 2, "d2"),
                _planet("SATURN", "Сатурн", 3, 1, "d2"),
            ],
        ),
        "dashas": {
            "status": "ready",
            "data": {
                "maha_dashas": [
                    _period(
                        "Saturn",
                        "2020-01-01T00:00:00+00:00",
                        "2040-01-01T00:00:00+00:00",
                        [
                            _period("Mercury", "2025-01-01T00:00:00+00:00", "2028-01-01T00:00:00+00:00"),
                            _period("Ketu", "2028-01-01T00:00:00+00:00", "2030-01-01T00:00:00+00:00"),
                            _period("Venus", "2030-01-01T00:00:00+00:00", "2034-01-01T00:00:00+00:00"),
                            _period("Sun", "2034-01-01T00:00:00+00:00", "2036-01-01T00:00:00+00:00"),
                        ],
                    ),
                    _period(
                        "Mercury",
                        "2040-01-01T00:00:00+00:00",
                        "2057-01-01T00:00:00+00:00",
                        [_period("Mercury", "2040-01-01T00:00:00+00:00", "2042-01-01T00:00:00+00:00")],
                    ),
                    _period("Ketu", "2057-01-01T00:00:00+00:00", "2064-01-01T00:00:00+00:00"),
                ]
            },
        },
    }
    snapshot = SimpleNamespace(sections=sections, created_at=datetime(2026, 8, 4, tzinfo=UTC))

    facts, packets = compile_evidence(snapshot)

    by_id = {fact.id: fact for fact in facts}
    by_slug = {packet.slug: packet for packet in packets}
    work_ids = by_slug[DomainSlug.WORK].primary_facts + by_slug[DomainSlug.WORK].confirming_facts
    money_ids = by_slug[DomainSlug.MONEY].primary_facts + by_slug[DomainSlug.MONEY].confirming_facts
    period_ids = by_slug[DomainSlug.CURRENT_PERIOD].primary_facts + by_slug[DomainSlug.CURRENT_PERIOD].confirming_facts

    work_lords = [by_id[fact_id] for fact_id in work_ids if by_id[fact_id].kind == "house_lord_position"]
    assert {(fact.chart, fact.value["natal_house_number"], fact.value["lord_code"]) for fact in work_lords} == {
        ("d1", 10, "SATURN"),
        ("D10", 10, "SATURN"),
    }
    money_lords = [by_id[fact_id] for fact_id in money_ids if by_id[fact_id].kind == "house_lord_position"]
    assert {(fact.chart, fact.value["natal_house_number"], fact.value["lord_code"]) for fact in money_lords} == {
        ("d1", 2, "VENUS"),
        ("D2", 2, "VENUS"),
        ("d1", 11, "SATURN"),
        ("D2", 11, "SATURN"),
    }

    timeline = next(fact for fact in facts if fact.kind == "dasha_timeline")
    assert timeline.id in work_ids and timeline.id in money_ids and timeline.id in period_ids
    assert timeline.domains == [DomainSlug.CURRENT_PERIOD, DomainSlug.WORK, DomainSlug.MONEY]
    assert [period["status"] for period in timeline.value["mahadashas"]] == ["current", "future", "future"]
    assert timeline.value["mahadashas"][0]["start"] == "2020-01-01T00:00:00+00:00"
    assert timeline.value["mahadashas"][1]["end"] == "2057-01-01T00:00:00+00:00"
    assert [period["status"] for period in timeline.value["mahadashas"][0]["antardashas"]] == [
        "current",
        "future",
        "future",
        "future",
    ]
    assert len(work_ids) <= 6 and len(money_ids) <= 6 and len(period_ids) <= 6
