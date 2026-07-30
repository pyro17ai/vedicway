from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from .calculator import _birth_data, _load_pyjhora
from .errors import DomainError
from .schemas import BirthInput, ChartCreateRequest, Place, TimeAccuracy
from .time_normalization import parse_dasha_datetime, resolve_birth_input

SIGN_LORDS = (
    "Mars",
    "Venus",
    "Mercury",
    "Moon",
    "Sun",
    "Mercury",
    "Venus",
    "Mars",
    "Jupiter",
    "Saturn",
    "Saturn",
    "Jupiter",
)
SIGN_NAMES_RU = (
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
WINDOWS = {
    "unknown": (0, 23 * 60 + 50),
    "night": (0, 5 * 60 + 50),
    "morning": (6 * 60, 11 * 60 + 50),
    "day": (12 * 60, 17 * 60 + 50),
    "evening": (18 * 60, 23 * 60 + 50),
}
EVENT_RULES: dict[str, dict[str, Any]] = {
    "education": {"houses": {4, 5, 9}, "karakas": {"Mercury", "Jupiter"}, "varga": 24},
    "career": {"houses": {2, 6, 10, 11}, "karakas": {"Saturn", "Sun", "Mercury"}, "varga": 10},
    "marriage": {"houses": {2, 7, 11}, "karakas": {"Venus", "Jupiter"}, "varga": 9},
    "childbirth": {"houses": {5, 9}, "karakas": {"Jupiter"}, "varga": 7},
    "relocation": {"houses": {3, 4, 12}, "karakas": {"Moon", "Rahu"}, "varga": 4},
    "property": {"houses": {4, 11}, "karakas": {"Mars", "Venus", "Saturn"}, "varga": 4},
    "accident": {"houses": {6, 8, 12}, "karakas": {"Mars", "Saturn", "Ketu"}, "varga": None},
}


def _clock(total_minutes: int) -> str:
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def _candidate_birth(original: BirthInput, total_minutes: int) -> BirthInput:
    request = ChartCreateRequest(
        local_date=original.local_datetime.date(),
        local_time=_clock(total_minutes),
        place_id=original.place.place_id,
        place=original.place,
        time_accuracy=TimeAccuracy.EXACT,
        fold=0,
    )
    return resolve_birth_input(request, original.place)


def _event_birth(place: Place, event: dict[str, Any]) -> BirthInput:
    month = int(event.get("month") or 7)
    event_date = date(int(event["year"]), month, 15 if event.get("month") else 1)
    request = ChartCreateRequest(
        local_date=event_date,
        local_time="12:00",
        place_id=place.place_id,
        place=place,
        time_accuracy=TimeAccuracy.EXACT,
        fold=0,
    )
    return resolve_birth_input(request, place)


def _positions(raw_chart: dict[str, Any]) -> dict[str, int]:
    return {
        str(item["planet"]): int(item["rasi_index"])
        for item in raw_chart.get("planets", [])
        if isinstance(item, dict) and "planet" in item and "rasi_index" in item
    }


def _active_lords(raw_dashas: dict[str, Any], target: datetime, tzid: str) -> tuple[str, str] | None:
    periods = raw_dashas.get("maha_dashas")
    if not isinstance(periods, list):
        return None
    for index, period in enumerate(periods):
        if not isinstance(period, dict):
            continue
        start = parse_dasha_datetime(period.get("start"), tzid)
        next_start = (
            parse_dasha_datetime(periods[index + 1].get("start"), tzid)
            if index + 1 < len(periods) and isinstance(periods[index + 1], dict)
            else None
        )
        end = parse_dasha_datetime(period.get("end"), tzid) or next_start
        if start is None or target < start or (end is not None and target >= end):
            continue
        sub_periods = period.get("sub_periods")
        if isinstance(sub_periods, list):
            for sub_index, sub_period in enumerate(sub_periods):
                if not isinstance(sub_period, dict):
                    continue
                sub_start = parse_dasha_datetime(sub_period.get("start"), tzid)
                sub_next = (
                    parse_dasha_datetime(sub_periods[sub_index + 1].get("start"), tzid)
                    if sub_index + 1 < len(sub_periods)
                    and isinstance(sub_periods[sub_index + 1], dict)
                    else end
                )
                sub_end = parse_dasha_datetime(sub_period.get("end"), tzid) or sub_next
                if (
                    sub_start is not None
                    and target >= sub_start
                    and (sub_end is None or target < sub_end)
                ):
                    return str(period.get("lord")), str(sub_period.get("lord"))
        return str(period.get("lord")), str(period.get("lord"))
    return None


def _house(sign_index: int, reference_sign: int) -> int:
    return ((sign_index - reference_sign) % 12) + 1


def _relevant_planets(
    event_type: str,
    ascendant_sign: int,
    planet_signs: dict[str, int],
) -> set[str]:
    rule = EVENT_RULES[event_type]
    relevant = set(rule["karakas"])
    for house_number in rule["houses"]:
        relevant.add(SIGN_LORDS[(ascendant_sign + house_number - 1) % 12])
    for planet, sign_index in planet_signs.items():
        if _house(sign_index, ascendant_sign) in rule["houses"]:
            relevant.add(planet)
    return relevant


def _score_event(
    event: dict[str, Any],
    ascendant_sign: int,
    moon_sign: int,
    planet_signs: dict[str, int],
    active_lords: tuple[str, str] | None,
    transit_signs: dict[str, int],
    varga_lords: dict[int, str],
) -> tuple[float, float]:
    rule = EVENT_RULES[str(event["event_type"])]
    relevant = _relevant_planets(str(event["event_type"]), ascendant_sign, planet_signs)
    score = 0.0
    maximum = 8.0
    if active_lords:
        maha, antara = active_lords
        if maha in relevant:
            score += 2
        if antara in relevant:
            score += 4
        divisor = rule["varga"]
        if divisor is not None:
            maximum += 3
            varga_lord = varga_lords.get(divisor)
            if maha == varga_lord:
                score += 1
            if antara == varga_lord:
                score += 2
    for slow_planet in ("Jupiter", "Saturn"):
        transit_sign = transit_signs.get(slow_planet)
        if transit_sign is None:
            continue
        if (
            _house(transit_sign, ascendant_sign) in rule["houses"]
            or _house(transit_sign, moon_sign) in rule["houses"]
        ):
            score += 1
    certainty = 1.0 if event.get("month") else 0.7
    return score * certainty, maximum * certainty


def _score_candidate(
    original: BirthInput,
    total_minutes: int,
    events: list[dict[str, Any]],
    transits: dict[str, dict[str, int]],
    api: dict[str, Any],
) -> dict[str, Any]:
    birth = _candidate_birth(original, total_minutes)
    input_value = _birth_data(birth, api)
    raw_chart = api["get_rasi_chart"](input_value)
    ascendant = raw_chart.get("ascendant")
    if not isinstance(ascendant, dict) or "rasi_index" not in ascendant:
        raise DomainError("RECTIFICATION_CALCULATION_FAILED", "Не удалось рассчитать лагну кандидата")
    ascendant_sign = int(ascendant["rasi_index"])
    planet_signs = _positions(raw_chart)
    moon_sign = planet_signs.get("Moon")
    if moon_sign is None:
        raise DomainError("RECTIFICATION_CALCULATION_FAILED", "Не удалось рассчитать положение Луны")
    raw_dashas = api["get_vimsottari_dasha"](input_value, include_antara=True)
    divisors = {
        int(EVENT_RULES[str(event["event_type"])]["varga"])
        for event in events
        if EVENT_RULES[str(event["event_type"])]["varga"] is not None
    }
    varga_lords: dict[int, str] = {}
    for divisor in divisors:
        raw_varga = api["get_divisional_chart"](input_value, divisor)
        raw_varga_ascendant = raw_varga.get("ascendant")
        if isinstance(raw_varga_ascendant, dict) and "rasi_index" in raw_varga_ascendant:
            varga_lords[divisor] = SIGN_LORDS[int(raw_varga_ascendant["rasi_index"])]

    score = 0.0
    maximum = 0.0
    event_scores: list[float] = []
    for event in events:
        event_birth = _event_birth(original.place, event)
        active = _active_lords(
            raw_dashas,
            event_birth.resolved_time.utc_datetime.astimezone(ZoneInfo(original.place.tzid)),
            original.place.tzid,
        )
        event_score, event_maximum = _score_event(
            event,
            ascendant_sign,
            moon_sign,
            planet_signs,
            active,
            transits[str(event["event_type"])],
            varga_lords,
        )
        score += event_score
        maximum += event_maximum
        event_scores.append(event_score)
    return {
        "minutes": total_minutes,
        "time": _clock(total_minutes),
        "lagna": SIGN_NAMES_RU[ascendant_sign],
        "score": round(score, 4),
        "maximum": round(maximum, 4),
        "event_scores": event_scores,
    }


def _transits(
    place: Place,
    events: list[dict[str, Any]],
    api: dict[str, Any],
) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for event in events:
        event_type = str(event["event_type"])
        input_value = _birth_data(_event_birth(place, event), api)
        result[event_type] = _positions(api["get_rasi_chart"](input_value))
    return result


def _distinct_leaders(candidates: list[dict[str, Any]], count: int = 3) -> list[int]:
    leaders: list[int] = []
    for candidate in candidates:
        minute = int(candidate["minutes"])
        if all(abs(minute - selected) >= 20 for selected in leaders):
            leaders.append(minute)
        if len(leaders) == count:
            break
    return leaders


def calculate_rectification(original: BirthInput, answers: dict[str, Any]) -> dict[str, Any]:
    events = list(answers.get("events") or [])
    if len(events) < 3:
        raise DomainError(
            "RECTIFICATION_EVENTS_REQUIRED",
            "Для расчёта нужны даты минимум трёх жизненных событий",
            recoverable=False,
            status_code=422,
        )
    if any(str(event.get("event_type")) not in EVENT_RULES for event in events):
        raise DomainError(
            "RECTIFICATION_EVENT_INVALID",
            "Опрос содержит неизвестный тип события",
            recoverable=False,
            status_code=422,
        )
    birth_year = original.local_datetime.year
    current_year = date.today().year
    if any(not birth_year <= int(event["year"]) <= current_year for event in events):
        raise DomainError(
            "RECTIFICATION_EVENT_DATE_INVALID",
            "Дата жизненного события выходит за допустимый период",
            recoverable=False,
            status_code=422,
        )
    window = str(answers.get("time_window") or "")
    if window not in WINDOWS:
        raise DomainError(
            "RECTIFICATION_WINDOW_INVALID",
            "Выберите известную часть суток",
            recoverable=False,
            status_code=422,
        )

    holdout_events = [events[-1]]
    fit_events = events[:-1]
    api = _load_pyjhora()
    transits = _transits(original.place, events, api)
    start, end = WINDOWS[window]
    coarse_minutes = list(range(start, end + 1, 10))
    coarse = [
        _score_candidate(original, minute, fit_events, transits, api)
        for minute in coarse_minutes
    ]
    coarse.sort(key=lambda item: (-float(item["score"]), int(item["minutes"])))
    fine_minutes: set[int] = set()
    for leader in _distinct_leaders(coarse):
        fine_minutes.update(range(max(start, leader - 10), min(end, leader + 10) + 1, 2))
    all_minutes = sorted(set(coarse_minutes) | fine_minutes)
    by_minute = {int(candidate["minutes"]): candidate for candidate in coarse}
    for minute in fine_minutes:
        if minute not in by_minute:
            by_minute[minute] = _score_candidate(original, minute, fit_events, transits, api)
    ranked = sorted(
        by_minute.values(),
        key=lambda item: (-float(item["score"]), int(item["minutes"])),
    )
    if not ranked:
        raise DomainError(
            "RECTIFICATION_CALCULATION_FAILED",
            "Не удалось оценить варианты времени рождения",
            recoverable=True,
        )

    best = ranked[0]
    holdout_transits = _transits(original.place, holdout_events, api)
    holdout = _score_candidate(
        original,
        int(best["minutes"]),
        holdout_events,
        holdout_transits,
        api,
    )
    holdout_ratio = (
        float(holdout["score"]) / float(holdout["maximum"])
        if float(holdout["maximum"])
        else 0.0
    )
    best_ratio = (
        float(best["score"]) / float(best["maximum"])
        if float(best["maximum"])
        else 0.0
    )
    second_score = float(ranked[1]["score"]) if len(ranked) > 1 else 0.0
    margin = (
        (float(best["score"]) - second_score) / float(best["maximum"])
        if float(best["maximum"])
        else 0.0
    )
    near_best = [
        candidate
        for candidate in ranked
        if float(candidate["score"]) >= max(float(best["score"]) * 0.9, float(best["score"]) - 1)
    ]
    uncertainty = max(
        5,
        min(
            120,
            max(abs(int(candidate["minutes"]) - int(best["minutes"])) for candidate in near_best),
        ),
    )
    medium = (
        len(events) >= 4
        and best_ratio >= 0.45
        and holdout_ratio >= 0.35
        and (margin >= 0.03 or uncertainty <= 30)
    )
    confidence = "medium" if medium else "low"

    alternatives: list[dict[str, Any]] = []
    for candidate in ranked[1:]:
        candidate_minute = int(candidate["minutes"])
        if abs(candidate_minute - int(best["minutes"])) < 10 or any(
            abs(candidate_minute - int(existing["minutes"])) < 10 for existing in alternatives
        ):
            continue
        alternatives.append(
            {
                "time": candidate["time"],
                "lagna": candidate["lagna"],
                "score_percent": round(
                    100 * float(candidate["score"]) / float(candidate["maximum"])
                )
                if float(candidate["maximum"])
                else 0,
                "minutes": candidate_minute,
            }
        )
        if len(alternatives) == 3:
            break
    for alternative in alternatives:
        alternative.pop("minutes", None)

    return {
        "selected_time": best["time"],
        "confidence": confidence,
        "uncertainty_minutes": uncertainty,
        "score_percent": round(best_ratio * 100),
        "candidate_count_expected": len(all_minutes),
        "candidate_count_scored": len(ranked),
        "fit_event_count": len(fit_events),
        "holdout_event_count": len(holdout_events),
        "holdout_supported": holdout_ratio >= 0.35,
        "lagna": best["lagna"],
        "alternatives": alternatives,
        "algorithm_version": "rectification.v1",
        "disclaimer": (
            "Результат показывает наиболее согласованное с указанными событиями время. "
            "Астрологическая ректификация не доказывает точную минуту рождения и не заменяет запись из роддома."
        ),
    }
