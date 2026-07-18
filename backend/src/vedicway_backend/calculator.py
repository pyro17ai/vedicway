from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from .constants import CLASSICAL_PLANETS, PLANET_LABELS_RU, SIGN_CODES, SIGN_NAMES_RU
from .errors import DomainError
from .schemas import BirthInput, ChartCell, ChartSnapshot, PlanetPosition, SectionStatus, section_model
from .time_normalization import normalize_event_time, normalized_dasha_periods


def _checksum(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def _prepare_pyjhora_source() -> None:
    source = os.environ.get("VEDICWAY_PYJHORA_SOURCE")
    if source:
        source_path = Path(source).expanduser().resolve()
        if source_path.is_dir() and str(source_path) not in sys.path:
            sys.path.insert(0, str(source_path))


@lru_cache(maxsize=1)
def _load_instant_pyjhora() -> dict[str, Any]:
    """Import only the D1 contract needed for the first visible result."""

    _prepare_pyjhora_source()
    try:
        from pyjhora_mcp.models.schemas import BirthDataInput, DateTimeInput, PlaceInput
        from pyjhora_mcp.tools.horoscope import get_rasi_chart
    except Exception as exc:
        raise DomainError(
            "EPHEMERIS_MISSING",
            "Расчётный пакет PyJHora недоступен для worker-процесса",
            recoverable=False,
        ) from exc
    return {
        "BirthDataInput": BirthDataInput,
        "DateTimeInput": DateTimeInput,
        "PlaceInput": PlaceInput,
        "get_rasi_chart": get_rasi_chart,
    }


@lru_cache(maxsize=1)
def _load_pyjhora() -> dict[str, Any]:
    _prepare_pyjhora_source()
    try:
        from pyjhora_mcp.models.schemas import BirthDataInput, DateTimeInput, PlaceInput
        from pyjhora_mcp.tools.dasha import get_ashtottari_dasha, get_vimsottari_dasha
        from pyjhora_mcp.tools.horoscope import (
            get_ashtakavarga,
            get_bhava_chart,
            get_divisional_chart,
            get_rasi_chart,
            get_special_lagnas,
        )
        from pyjhora_mcp.tools.panchanga import get_panchanga
        from pyjhora_mcp.tools.strength import get_bhava_bala, get_shadbala, get_vimsopaka_bala
        from pyjhora_mcp.tools.yoga import get_doshas, get_raja_yogas, get_yogas
    except Exception as exc:
        raise DomainError(
            "EPHEMERIS_MISSING",
            "Расчётный пакет PyJHora недоступен для worker-процесса",
            recoverable=False,
        ) from exc
    return {
        "BirthDataInput": BirthDataInput,
        "DateTimeInput": DateTimeInput,
        "PlaceInput": PlaceInput,
        "get_rasi_chart": get_rasi_chart,
        "get_divisional_chart": get_divisional_chart,
        "get_panchanga": get_panchanga,
        "get_vimsottari_dasha": get_vimsottari_dasha,
        "get_ashtottari_dasha": get_ashtottari_dasha,
        "get_special_lagnas": get_special_lagnas,
        "get_ashtakavarga": get_ashtakavarga,
        "get_bhava_chart": get_bhava_chart,
        "get_shadbala": get_shadbala,
        "get_bhava_bala": get_bhava_bala,
        "get_vimsopaka_bala": get_vimsopaka_bala,
        "get_yogas": get_yogas,
        "get_doshas": get_doshas,
        "get_raja_yogas": get_raja_yogas,
    }


def warm_instant_runtime() -> None:
    """Move the import-only cold start before the first visitor creates a chart."""

    _load_instant_pyjhora()


def _birth_data(birth: BirthInput, api: dict[str, Any]):
    offset_hours = birth.resolved_time.utc_offset_seconds / 3600
    return api["BirthDataInput"](
        place=api["PlaceInput"](
            name=birth.place.display_name,
            latitude=birth.place.latitude,
            longitude=birth.place.longitude,
            timezone=offset_hours,
        ),
        date_time=api["DateTimeInput"](
            year=birth.local_datetime.year,
            month=birth.local_datetime.month,
            day=birth.local_datetime.day,
            hour=birth.local_datetime.hour,
            minute=birth.local_datetime.minute,
            second=birth.local_datetime.second,
        ),
        ayanamsa=birth.ayanamsa,
    )


def _planet_position(raw: dict[str, Any], ascendant_sign: int, source_path: str) -> PlanetPosition:
    source_name = str(raw.get("planet", ""))
    code, label, short_label = PLANET_LABELS_RU.get(source_name, (source_name.upper(), source_name, source_name[:2]))
    sign_index = int(raw["rasi_index"])
    return PlanetPosition(
        planet_code=code,
        label=label,
        short_label=short_label,
        classical=code in CLASSICAL_PLANETS,
        sign_index=sign_index,
        sign_label=SIGN_NAMES_RU[sign_index],
        house_number=((sign_index - ascendant_sign) % 12) + 1,
        longitude_in_sign=float(raw["longitude_in_rasi"]),
        total_longitude=float(raw.get("total_longitude", sign_index * 30 + float(raw["longitude_in_rasi"]))),
        nakshatra=str(raw.get("nakshatra", "Не указана")),
        pada=raw.get("pada"),
        retrograde=raw.get("retrograde"),
        source_path=source_path,
    )


def _cells_from_chart(raw_chart: dict[str, Any], title: str) -> tuple[list[ChartCell], dict[str, Any]]:
    raw_ascendant = raw_chart.get("ascendant")
    if not isinstance(raw_ascendant, dict) or "rasi_index" not in raw_ascendant:
        raise DomainError("CALCULATION_FAILED", "Расчёт не вернул лагну")
    ascendant_sign = int(raw_ascendant["rasi_index"])
    positions = [
        _planet_position(planet, ascendant_sign, f"sections.{title}.planets.{index}")
        for index, planet in enumerate(raw_chart.get("planets", []))
        if isinstance(planet, dict) and "rasi_index" in planet and "longitude_in_rasi" in planet
    ]
    stable_order = {code: index for index, code in enumerate(("SUN", "MOON", "MARS", "MERCURY", "JUPITER", "VENUS", "SATURN", "RAHU", "KETU", "URANUS", "NEPTUNE", "PLUTO"))}
    cells: list[ChartCell] = []
    for sign_index in range(12):
        cell_planets = sorted(
            [position for position in positions if position.sign_index == sign_index],
            key=lambda position: stable_order.get(position.planet_code, 99),
        )
        cells.append(
            ChartCell(
                sign_index=sign_index,
                sign_code=SIGN_CODES[sign_index],
                sign_label=SIGN_NAMES_RU[sign_index],
                house_number=((sign_index - ascendant_sign) % 12) + 1,
                is_lagna=sign_index == ascendant_sign,
                planets=cell_planets,
            )
        )
    ascendant = {
        "sign_index": ascendant_sign,
        "sign_label": SIGN_NAMES_RU[ascendant_sign],
        "longitude_in_sign": float(raw_ascendant["longitude_in_rasi"]),
        "nakshatra": raw_ascendant.get("nakshatra"),
    }
    return cells, ascendant


def _validate_canonical_d1(cells: list[ChartCell], ascendant: dict[str, Any]) -> None:
    if len(cells) != 12 or {cell.sign_index for cell in cells} != set(range(12)):
        raise DomainError("INVARIANT_VIOLATION", "Основная карта содержит неполный набор знаков", recoverable=False)
    if sum(1 for cell in cells if cell.is_lagna) != 1:
        raise DomainError("INVARIANT_VIOLATION", "Не удалось однозначно определить лагну", recoverable=False)
    expected = {"SUN", "MOON", "MARS", "MERCURY", "JUPITER", "VENUS", "SATURN", "RAHU", "KETU"}
    positions = [planet for cell in cells for planet in cell.planets]
    codes = [planet.planet_code for planet in positions]
    if not expected.issubset(codes) or len(codes) != len(set(codes)):
        raise DomainError("INVARIANT_VIOLATION", "Основная карта содержит неполный или повторяющийся набор планет", recoverable=False)
    lagna_cell = next(cell for cell in cells if cell.is_lagna)
    if lagna_cell.sign_index != int(ascendant["sign_index"]):
        raise DomainError("INVARIANT_VIOLATION", "Лагна не совпадает с сеткой знаков", recoverable=False)


def _panchanga(raw: dict[str, Any], birth: BirthInput) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key in ("tithi", "nakshatra", "yoga"):
        item = raw.get(key)
        if isinstance(item, dict) and "error" not in item:
            copy = dict(item)
            event_time = normalize_event_time(copy.pop("end_time", None), birth.local_datetime.date(), birth.place.tzid)
            if event_time:
                copy["end"] = event_time.model_dump(mode="json")
            normalized[key] = copy
    for key in ("karana", "masa", "samvatsara", "ritu"):
        if key in raw:
            normalized[key] = raw[key]
    # This is explicitly the civil weekday. A sunrise-based vaara would be a separate field.
    normalized["vaara"] = birth.local_datetime.strftime("%A")
    normalized["vaara_rule"] = "civil_local_date"
    return normalized


def calculate_instant(birth: BirthInput, chart_id: str, revision: int = 1) -> ChartSnapshot:
    api = _load_instant_pyjhora()
    input_value = _birth_data(birth, api)
    raw_d1 = api["get_rasi_chart"](input_value)
    if raw_d1.get("planets_error"):
        raise DomainError("CALCULATION_FAILED", "PyJHora не вернул положения планет")
    cells, ascendant = _cells_from_chart(raw_d1, "d1")
    _validate_canonical_d1(cells, ascendant)
    snapshot_id = f"cs_{hashlib.sha256(f'{chart_id}:{revision}:{birth.resolved_time.utc_datetime.isoformat()}'.encode()).hexdigest()[:24]}"
    public_birth = {
        "local_date": birth.local_datetime.date().isoformat(),
        "local_time": birth.local_datetime.time().isoformat(timespec="minutes"),
        "place": birth.place.display_name,
        "timezone": f"UTC{birth.resolved_time.utc_offset_seconds // 3600:+d}",
        "time_accuracy": birth.time_accuracy.value,
    }
    sections = {
        "d1": section_model("d1", SectionStatus.READY, {"title": "D1 · Основная карта", "cells": [cell.model_dump(mode="json") for cell in cells], "ascendant": ascendant}),
        "panchanga": section_model("panchanga", SectionStatus.QUEUED),
        "dashas": section_model("dashas", SectionStatus.QUEUED),
        "vargas": section_model("vargas", SectionStatus.QUEUED),
        "strength": section_model("strength", SectionStatus.QUEUED),
        "combinations": section_model("combinations", SectionStatus.QUEUED),
    }
    payload = {
        "snapshot_id": snapshot_id,
        "chart_id": chart_id,
        "revision": revision,
        "engine": {
            "package": "pyjhora-mcp",
            "package_version": "0.1.0",
            "pyjhora_version": "4.7.0",
            "swisseph_version": "2.10.3.2",
            "ephemeris_fingerprint": "runtime-verified",
            "rule_set_version": "vedicway-rules.v1",
        },
        "method": {"ayanamsa": "LAHIRI", "chart_style": "south_indian", "house_reference": "from_lagna"},
        "birth": public_birth,
        "cells": [cell.model_dump(mode="json") for cell in cells],
        "sections": sections,
        "created_at": datetime.now(UTC),
    }
    return ChartSnapshot(**payload, checksum=_checksum(payload))


def calculate_extended(birth: BirthInput, snapshot: ChartSnapshot) -> dict[str, dict[str, Any]]:
    api = _load_pyjhora()
    input_value = _birth_data(birth, api)
    results: dict[str, dict[str, Any]] = {}
    for divisor in (2, 4, 9, 10, 12, 24):
        key = f"D{divisor}"
        raw = api["get_divisional_chart"](input_value, divisor)
        try:
            cells, ascendant = _cells_from_chart(raw, key.lower())
            results[key] = section_model(key, SectionStatus.READY, {"title": key, "cells": [cell.model_dump(mode="json") for cell in cells], "ascendant": ascendant})
        except DomainError as exc:
            results[key] = section_model(key, SectionStatus.PARTIAL, None, {"code": exc.code, "message": exc.message, "recoverable": exc.recoverable})

    supplementary = {
        "special_lagnas": api["get_special_lagnas"],
        "ashtakavarga": api["get_ashtakavarga"],
        "bhava_chart": api["get_bhava_chart"],
        "shadbala": api["get_shadbala"],
        "bhava_bala": api["get_bhava_bala"],
        "vimsopaka_bala": api["get_vimsopaka_bala"],
        "yogas": api["get_yogas"],
        "doshas": api["get_doshas"],
        "raja_yogas": api["get_raja_yogas"],
    }
    data: dict[str, Any] = {}
    for name, function in supplementary.items():
        try:
            data[name] = function(input_value)
        except Exception as exc:
            data[name] = {"error": {"code": "CALCULATION_FAILED", "message": str(exc), "recoverable": True}}
    raw_panchanga = api["get_panchanga"](input_value)
    raw_dashas = api["get_vimsottari_dasha"](input_value)
    try:
        dashas = normalized_dasha_periods(raw_dashas.get("maha_dashas", []), birth.place.tzid)
        dashas_status = SectionStatus.READY if dashas else SectionStatus.PARTIAL
    except DomainError as exc:
        dashas = []
        dashas_status = SectionStatus.PARTIAL
        dashas_error = {"code": exc.code, "message": exc.message, "recoverable": exc.recoverable}
    else:
        dashas_error = None
    results["panchanga"] = section_model("panchanga", SectionStatus.READY, _panchanga(raw_panchanga, birth))
    results["dashas"] = section_model("dashas", dashas_status, {"maha_dashas": dashas}, dashas_error)
    results["strength"] = section_model("strength", SectionStatus.READY, {key: data[key] for key in ("shadbala", "bhava_bala", "vimsopaka_bala", "ashtakavarga")})
    results["combinations"] = section_model("combinations", SectionStatus.READY, {key: data[key] for key in ("yogas", "doshas", "raja_yogas", "special_lagnas", "bhava_chart")})
    return results


def calculate_expert_extended(birth: BirthInput, snapshot: ChartSnapshot) -> dict[str, dict[str, Any]]:
    """Optional exact-time profile; it never replaces canonical D1 or free evidence."""
    api = _load_pyjhora()
    input_value = _birth_data(birth, api)
    results: dict[str, dict[str, Any]] = {}
    for divisor in (3, 7, 16, 20, 27, 30, 40, 45, 60):
        key = f"D{divisor}"
        if divisor == 60 and birth.time_accuracy.value != "exact":
            results[key] = section_model(
                key,
                SectionStatus.UNAVAILABLE,
                {"reason": "Точная D60 доступна только при подтверждённом времени рождения."},
            )
            continue
        try:
            cells, ascendant = _cells_from_chart(api["get_divisional_chart"](input_value, divisor), key.lower())
            results[key] = section_model(key, SectionStatus.READY, {"title": key, "cells": [cell.model_dump(mode="json") for cell in cells], "ascendant": ascendant})
        except Exception as exc:
            results[key] = section_model(key, SectionStatus.PARTIAL, None, {"code": "CALCULATION_FAILED", "message": "Не удалось завершить расчёт варги", "recoverable": True})
    if os.environ.get("VEDICWAY_ENABLE_ASHTOTTARI") == "1":
        try:
            results["ashtottari"] = section_model(
                "ashtottari",
                SectionStatus.READY,
                {"data_only": True, "periods": api["get_ashtottari_dasha"](input_value)},
            )
        except Exception:
            results["ashtottari"] = section_model(
                "ashtottari", SectionStatus.PARTIAL, None, {"code": "CALCULATION_FAILED", "message": "Не удалось подготовить дополнительные периоды", "recoverable": True}
            )
    else:
        results["ashtottari"] = section_model(
            "ashtottari", SectionStatus.UNAVAILABLE, {"data_only": True, "reason": "Проверка применимости периода ещё не включена."}
        )
    return results
