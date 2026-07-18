from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .errors import DomainError
from .schemas import BirthInput, ChartCreateRequest, EventTime, ResolvedTime

_CLOCK_RE = re.compile(r"^(?P<sign>-)?(?P<hours>\d+):(?P<minutes>[0-5]\d):(?P<seconds>[0-5]\d)$")
_DASHA_RE = re.compile(
    r"^(?P<day>\d{4}-\d{2}-\d{2})\s+(?P<hour>\d{1,2}):(?P<minute>\d{2}):(?P<second>\d{2})\s*(?P<meridiem>AM|PM)?$",
    re.IGNORECASE,
)


def resolve_birth_input(request: ChartCreateRequest, place, tzdb_version: str = "iana-2026a") -> BirthInput:
    parts = [int(part) for part in request.local_time.split(":")]
    if len(parts) == 2:
        parts.append(0)
    naive = datetime(request.local_date.year, request.local_date.month, request.local_date.day, *parts)

    try:
        zone = ZoneInfo(place.tzid)
    except ZoneInfoNotFoundError as exc:
        raise DomainError("TIMEZONE_RESOLUTION_FAILED", "Не удалось определить часовой пояс города", detail={"tzid": place.tzid}) from exc

    candidates: list[tuple[int, datetime]] = []
    for fold in (0, 1):
        local = naive.replace(tzinfo=zone, fold=fold)
        round_trip = local.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
        if round_trip == naive:
            candidates.append((fold, local))

    if not candidates:
        raise DomainError(
            "NONEXISTENT_LOCAL_TIME",
            "Указанное местное время не существовало из-за перевода часов",
            detail={"local_datetime": naive.isoformat(), "tzid": place.tzid},
        )

    unique_offsets = {local.utcoffset() for _, local in candidates}
    if len(unique_offsets) > 1 and request.fold is None:
        options = [
            {"fold": fold, "utc_offset_seconds": int(local.utcoffset().total_seconds())}
            for fold, local in candidates
        ]
        raise DomainError(
            "AMBIGUOUS_LOCAL_TIME",
            "Для этого времени доступны два исторических смещения UTC",
            detail={"options": options},
        )

    selected_fold = request.fold or 0
    selected = next((local for fold, local in candidates if fold == selected_fold), None)
    if selected is None:
        raise DomainError(
            "TIMEZONE_RESOLUTION_FAILED",
            "Выбранный вариант времени не подходит для часового пояса",
            detail={"fold": selected_fold, "tzid": place.tzid},
        )

    offset = selected.utcoffset()
    if offset is None:
        raise DomainError("TIMEZONE_RESOLUTION_FAILED", "Не удалось получить смещение UTC")

    return BirthInput(
        local_datetime=naive,
        place=place,
        resolved_time=ResolvedTime(
            utc_offset_seconds=int(offset.total_seconds()),
            utc_datetime=selected.astimezone(UTC),
            resolution_source=tzdb_version,
            fold=selected_fold,
        ),
        time_accuracy=request.time_accuracy,
    )


def normalize_event_time(value: object, local_date: date, tzid: str) -> EventTime | None:
    """Convert PyJHora fractional or extended clock times to a date-aware API shape."""
    raw_hours: float | None
    if isinstance(value, (int, float)):
        raw_hours = float(value)
    elif isinstance(value, str):
        match = _CLOCK_RE.fullmatch(value.strip())
        if not match:
            return None
        hours = int(match.group("hours"))
        minutes = int(match.group("minutes"))
        seconds = int(match.group("seconds"))
        raw_hours = hours + minutes / 60 + seconds / 3600
        if match.group("sign"):
            raw_hours = -raw_hours
    else:
        return None

    total_seconds = int(round(raw_hours * 3600))
    day_offset, second_of_day = divmod(total_seconds, 24 * 3600)
    event_date = local_date + timedelta(days=day_offset)
    local_clock = (datetime.min + timedelta(seconds=second_of_day)).time().replace(microsecond=0)
    try:
        zone = ZoneInfo(tzid)
    except ZoneInfoNotFoundError as exc:
        raise DomainError("TIMEZONE_RESOLUTION_FAILED", "Не удалось нормализовать время панчанги") from exc
    event_datetime = datetime.combine(event_date, local_clock, tzinfo=zone)
    return EventTime(
        local_date=event_date,
        local_time=local_clock.isoformat(),
        day_offset=day_offset,
        iso_datetime=event_datetime,
        raw_hours=raw_hours,
    )


def parse_dasha_datetime(value: object, tzid: str) -> datetime | None:
    """Parse PyJHora's mixed 12/24 hour dasha strings into one ISO-safe datetime."""
    if not isinstance(value, str):
        return None
    match = _DASHA_RE.fullmatch(value.strip())
    if not match:
        return None
    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    second = int(match.group("second"))
    meridiem = (match.group("meridiem") or "").upper()
    if hour > 23:
        return None
    if meridiem and hour <= 12:
        if hour == 12:
            hour = 0
        if meridiem == "PM":
            hour += 12
    # PyJHora can append PM to an already valid 24-hour value. The numeric hour wins.
    day = date.fromisoformat(match.group("day"))
    try:
        zone = ZoneInfo(tzid)
    except ZoneInfoNotFoundError:
        return None
    return datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=zone)


def normalized_dasha_periods(periods: list[dict[str, object]], tzid: str) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    previous: datetime | None = None
    for period in periods:
        start = parse_dasha_datetime(period.get("start"), tzid)
        end = parse_dasha_datetime(period.get("end"), tzid)
        if start is None:
            continue
        if previous is not None and start < previous:
            raise DomainError("NORMALIZATION_FAILED", "Периоды Вимшоттари нарушают хронологический порядок")
        if end is not None and end < start:
            raise DomainError("NORMALIZATION_FAILED", "Конец периода Вимшоттари раньше начала")
        children = normalized_dasha_periods(period.get("sub_periods", []), tzid) if isinstance(period.get("sub_periods"), list) else []
        normalized.append(
            {
                "lord": period.get("lord"),
                "start": start.isoformat(),
                "end": end.isoformat() if end else None,
                "sub_periods": children,
            }
        )
        previous = start
    return normalized
