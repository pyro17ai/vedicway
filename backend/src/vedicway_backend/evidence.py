from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from .constants import DOMAIN_LABELS_RU, DOMAIN_ORDER, PLANET_LABELS_RU, DomainSlug
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


def _append_fact(facts: list[EvidenceFact], fact: EvidenceFact) -> EvidenceFact:
    existing = next((item for item in facts if item.id == fact.id), None)
    if existing is None:
        facts.append(fact)
        return fact
    existing.domains = list(dict.fromkeys([*existing.domains, *fact.domains]))
    return existing


def _period_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return result if result.tzinfo else result.replace(tzinfo=UTC)


def _active_period(periods: list[dict[str, Any]], reference: datetime) -> tuple[int, dict[str, Any]] | None:
    reference = reference if reference.tzinfo else reference.replace(tzinfo=UTC)
    for index, period in enumerate(periods):
        start = _period_datetime(period.get("start"))
        end = _period_datetime(period.get("end"))
        if start is None:
            continue
        comparable = reference.astimezone(start.tzinfo)
        if start <= comparable and (end is None or comparable < end.astimezone(start.tzinfo)):
            return index, period
    return None


def _period_lord_ru(value: object) -> str:
    raw = str(value or "Период Вимшоттари")
    label = PLANET_LABELS_RU.get(raw)
    return label[1] if label else raw


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
        return _append_fact(facts, fact)

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
        return _append_fact(facts, fact)

    character = [add_asc("d1", [DomainSlug.CHARACTER], "Основная карта"), add_planet("SUN", "d1", [DomainSlug.CHARACTER], "Основная карта")]
    inner = [add_planet("MOON", "d1", [DomainSlug.INNER_SUPPORT], "Основная карта"), add_planet("VENUS", "d1", [DomainSlug.INNER_SUPPORT], "Основная карта")]
    relations = [add_asc("D9", [DomainSlug.RELATIONSHIPS], "Навамша D9"), add_planet("VENUS", "D9", [DomainSlug.RELATIONSHIPS], "Навамша D9")]
    family = [add_asc("D4", [DomainSlug.FAMILY_HOME], "Чатуртхамша D4"), add_planet("MOON", "d1", [DomainSlug.FAMILY_HOME], "Основная карта")]
    work = [add_asc("D10", [DomainSlug.WORK], "Дашамша D10"), add_planet("SATURN", "D10", [DomainSlug.WORK], "Дашамша D10")]
    money = [add_asc("D2", [DomainSlug.MONEY], "Хора D2"), add_planet("JUPITER", "D2", [DomainSlug.MONEY], "Хора D2")]
    learning = [add_asc("D24", [DomainSlug.LEARNING], "Чатурвимшамша D24"), add_planet("MERCURY", "D24", [DomainSlug.LEARNING], "Чатурвимшамша D24")]

    dashas = _section_data(snapshot, "dashas")
    periods = dashas.get("maha_dashas", []) if dashas else []
    current_match = _active_period(periods, snapshot.created_at) if isinstance(periods, list) else None
    current_missing: list[str] = []
    if current_match:
        current_index, current = current_match
        current_lord = _period_lord_ru(current.get("lord"))
        current_fact = _append_fact(
            facts,
            _fact(
                "dasha_period",
                current_lord,
                "D1",
                f"Активная махадаша Вимшоттари: {current_lord}",
                [DomainSlug.CURRENT_PERIOD],
                [f"sections.dashas.data.maha_dashas.{current_index}"],
                value={"level": "mahadasha", "start": current.get("start"), "end": current.get("end")},
            ),
        )
        current_period: list[EvidenceFact | None] = [current_fact]
        sub_periods = current.get("sub_periods", [])
        sub_match = _active_period(sub_periods, snapshot.created_at) if isinstance(sub_periods, list) else None
        if sub_match:
            sub_index, sub_period = sub_match
            sub_lord = _period_lord_ru(sub_period.get("lord"))
            current_period.append(
                _append_fact(
                    facts,
                    _fact(
                        "dasha_sub_period",
                        sub_lord,
                        "D1",
                        f"Активная антардаша Вимшоттари: {sub_lord}",
                        [DomainSlug.CURRENT_PERIOD],
                        [f"sections.dashas.data.maha_dashas.{current_index}.sub_periods.{sub_index}"],
                        value={"level": "antardasha", "start": sub_period.get("start"), "end": sub_period.get("end")},
                    ),
                )
            )
        else:
            current_period.append(add_planet("MOON", "d1", [DomainSlug.CURRENT_PERIOD], "Основная карта"))
    else:
        current_missing = ["dashas.active_period"]
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
    forced_missing = {DomainSlug.CURRENT_PERIOD: current_missing}
    for slug in DOMAIN_ORDER:
        candidates, expected_sections = domain_sources[slug]
        available = [fact for fact in candidates if fact is not None]
        missing = [key for key in expected_sections if not _section_data(snapshot, key)] + forced_missing.get(slug, [])
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
            available = [_append_fact(facts, availability)]
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
