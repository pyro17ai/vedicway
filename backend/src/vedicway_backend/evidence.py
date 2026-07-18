from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any

from .constants import DOMAIN_LABELS_RU, DOMAIN_ORDER, DomainSlug
from .schemas import ChartSnapshot, Coverage, DomainEvidencePacket, EvidenceFact


def _fact_id(kind: str, subject: str, chart: str, source_paths: Iterable[str]) -> str:
    identity = json.dumps([kind, subject, chart, sorted(source_paths)], ensure_ascii=False)
    return f"ef_{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:16]}"


def _fact(
    kind: str,
    subject: str,
    chart: str,
    label: str,
    domains: list[DomainSlug],
    source_paths: list[str],
    sign: str | None = None,
    house: int | None = None,
    value: dict[str, Any] | None = None,
) -> EvidenceFact:
    return EvidenceFact(
        id=_fact_id(kind, subject, chart, source_paths),
        kind=kind,
        subject=subject,
        chart=chart,
        sign=sign,
        house=house,
        value=value or {},
        human_label_ru=label,
        domains=domains,
        source_paths=source_paths,
    )


def _section_data(snapshot: ChartSnapshot, section: str) -> dict[str, Any] | None:
    item = snapshot.sections.get(section)
    if not item or item.get("status") not in {"ready", "partial"}:
        return None
    value = item.get("data")
    return value if isinstance(value, dict) else None


def _planet_map(snapshot: ChartSnapshot, chart_key: str = "d1") -> dict[str, dict[str, Any]]:
    section = _section_data(snapshot, chart_key)
    cells = section.get("cells", []) if section else []
    result: dict[str, dict[str, Any]] = {}
    for cell in cells:
        for planet in cell.get("planets", []):
            result[planet["planet_code"]] = {**planet, "cell": cell}
    return result


def _ascendant(snapshot: ChartSnapshot, chart_key: str) -> dict[str, Any] | None:
    section = _section_data(snapshot, chart_key)
    if not section:
        return None
    ascendant = section.get("ascendant")
    return ascendant if isinstance(ascendant, dict) else None


def compile_evidence(snapshot: ChartSnapshot) -> tuple[list[EvidenceFact], list[DomainEvidencePacket]]:
    """Compile fixed, inspectable evidence before interpretation text is requested."""
    facts: list[EvidenceFact] = []
    d1 = _planet_map(snapshot, "d1")
    d9 = _planet_map(snapshot, "D9")
    d10 = _planet_map(snapshot, "D10")
    d2 = _planet_map(snapshot, "D2")
    d4 = _planet_map(snapshot, "D4")
    d24 = _planet_map(snapshot, "D24")

    def add_planet(code: str, chart: str, domains: list[DomainSlug], label_prefix: str) -> EvidenceFact | None:
        planets = {"d1": d1, "D9": d9, "D10": d10, "D2": d2, "D4": d4, "D24": d24}.get(chart, {})
        planet = planets.get(code)
        if not planet:
            return None
        fact = _fact(
            "planet_position",
            planet["label"],
            chart,
            f"{label_prefix}: {planet['label']} в знаке {planet['sign_label']}, доме {planet['house_number']}",
            domains,
            [planet["source_path"]],
            sign=planet["sign_label"],
            house=int(planet["house_number"]),
            value={
                "planet_code": code,
                "longitude_in_sign": planet["longitude_in_sign"],
                "retrograde": planet.get("retrograde"),
            },
        )
        facts.append(fact)
        return fact

    def add_asc(chart: str, domains: list[DomainSlug], label_prefix: str) -> EvidenceFact | None:
        asc = _ascendant(snapshot, chart)
        if not asc:
            return None
        fact = _fact(
            "ascendant",
            "Лагна",
            chart,
            f"{label_prefix}: лагна в знаке {asc['sign_label']}",
            domains,
            [f"sections.{chart}.ascendant"],
            sign=asc["sign_label"],
            value={"longitude_in_sign": asc.get("longitude_in_sign"), "nakshatra": asc.get("nakshatra")},
        )
        facts.append(fact)
        return fact

    character = [add_asc("d1", [DomainSlug.CHARACTER], "Основная карта"), add_planet("SUN", "d1", [DomainSlug.CHARACTER], "Основная карта")]
    inner = [add_planet("MOON", "d1", [DomainSlug.INNER_SUPPORT], "Основная карта"), add_planet("VENUS", "d1", [DomainSlug.INNER_SUPPORT], "Основная карта")]
    relations = [add_asc("D9", [DomainSlug.RELATIONSHIPS], "Навамша D9"), add_planet("VENUS", "D9", [DomainSlug.RELATIONSHIPS], "Навамша D9")]
    family = [add_asc("D4", [DomainSlug.FAMILY_HOME], "Чатуртхамша D4"), add_planet("MOON", "d1", [DomainSlug.FAMILY_HOME], "Основная карта")]
    work = [add_asc("D10", [DomainSlug.WORK], "Дашамша D10"), add_planet("SATURN", "D10", [DomainSlug.WORK], "Дашамша D10")]
    money = [add_asc("D2", [DomainSlug.MONEY], "Хора D2"), add_planet("JUPITER", "D2", [DomainSlug.MONEY], "Хора D2")]
    learning = [add_asc("D24", [DomainSlug.LEARNING], "Чатурвимшамша D24"), add_planet("MERCURY", "D24", [DomainSlug.LEARNING], "Чатурвимшамша D24")]

    dashas = _section_data(snapshot, "dashas")
    periods = dashas.get("maha_dashas", []) if dashas else []
    current = next((period for period in periods if period.get("start") and period.get("end")), None)
    if current:
        current_fact = _fact(
            "dasha_period",
            str(current.get("lord") or "Период Вимшоттари"),
            "D1",
            f"Период Вимшоттари: {current.get('lord')}",
            [DomainSlug.CURRENT_PERIOD],
            ["sections.dashas.data.maha_dashas.0"],
            value={"start": current.get("start"), "end": current.get("end")},
        )
        facts.append(current_fact)
        current_period = [current_fact, add_planet("MOON", "d1", [DomainSlug.CURRENT_PERIOD], "Основная карта")]
    else:
        current_period = [add_planet("MOON", "d1", [DomainSlug.CURRENT_PERIOD], "Основная карта")]

    packets: list[DomainEvidencePacket] = []
    domain_sources = {
        DomainSlug.CHARACTER: (character, []),
        DomainSlug.INNER_SUPPORT: (inner, []),
        DomainSlug.RELATIONSHIPS: (relations, ["D9"]),
        DomainSlug.FAMILY_HOME: (family, ["D4"]),
        DomainSlug.WORK: (work, ["D10"]),
        DomainSlug.MONEY: (money, ["D2"]),
        DomainSlug.LEARNING: (learning, ["D24"]),
        DomainSlug.CURRENT_PERIOD: (current_period, ["dashas"]),
    }
    for slug in DOMAIN_ORDER:
        candidates, expected_sections = domain_sources[slug]
        available = [fact for fact in candidates if fact is not None]
        missing = [key for key in expected_sections if not _section_data(snapshot, key)]
        if not available:
            availability = _fact(
                "section_availability",
                "Статус расчёта",
                "system",
                f"Для темы «{DOMAIN_LABELS_RU[slug]}» требуется завершение расчётного раздела",
                [slug],
                [f"sections.{item}" for item in missing] or ["sections.d1"],
                value={"missing_sections": missing},
            )
            facts.append(availability)
            available = [availability]
        if missing:
            coverage = Coverage.INSUFFICIENT
        elif len(available) >= 2:
            coverage = Coverage.MULTIPLE_FACTORS
        else:
            coverage = Coverage.SINGLE_FACTOR
        packets.append(
            DomainEvidencePacket(
                slug=slug,
                primary_facts=[fact.id for fact in available[:1]],
                confirming_facts=[fact.id for fact in available[1:2]],
                coverage=coverage,
                allowed_claim_scope=(
                    f"Раздел «{DOMAIN_LABELS_RU[slug]}» описывает наблюдаемые темы для саморефлексии, "
                    "без обещаний точных событий, диагнозов или решений."
                ),
                missing_sections=missing,
            )
        )
    return facts, packets
