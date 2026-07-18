from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .schemas import Place


@dataclass(frozen=True)
class LocalPlace:
    """A place from the licensed, deployment-local place registry.

    Alternate names stay in the search index only. They are deliberately not
    exposed in the birth snapshot, which preserves one stable human-readable
    name and immutable coordinates for every completed chart.
    """

    place: Place
    alternate_names: tuple[str, ...] = ()

    @property
    def search_terms(self) -> tuple[str, ...]:
        return (self.place.display_name, *self.alternate_names)


def _place(
    place_id: str,
    display_name: str,
    country_code: str,
    latitude: float,
    longitude: float,
    tzid: str,
    *alternate_names: str,
) -> LocalPlace:
    return LocalPlace(
        Place(
            place_id=place_id,
            display_name=display_name,
            country_code=country_code,
            latitude=latitude,
            longitude=longitude,
            tzid=tzid,
        ),
        alternate_names,
    )


# Development seed only. Production requires VEDICWAY_PLACE_DATASET_PATH and
# never calls a public geocoding service at runtime. The deployed local dataset
# accepts every city supported by the licensed provider and keeps its timezone.
DEFAULT_LOCAL_PLACES: tuple[LocalPlace, ...] = (
    _place("ru-moscow-524901", "Москва, Россия", "RU", 55.7558, 37.6173, "Europe/Moscow", "Moscow", "г. Москва"),
    _place("ru-saint-petersburg-498817", "Санкт-Петербург, Россия", "RU", 59.9386, 30.3141, "Europe/Moscow", "Saint Petersburg", "St Petersburg", "Петербург"),
    _place("ru-novosibirsk-1496747", "Новосибирск, Россия", "RU", 55.0084, 82.9357, "Asia/Novosibirsk", "Novosibirsk"),
    _place("ru-vladivostok-2013348", "Владивосток, Россия", "RU", 43.1155, 131.8855, "Asia/Vladivostok", "Vladivostok"),
    _place("gb-london-2643743", "Лондон, Великобритания", "GB", 51.5072, -0.1276, "Europe/London", "London"),
    _place("fr-paris-2988507", "Париж, Франция", "FR", 48.8566, 2.3522, "Europe/Paris", "Paris"),
    _place("de-berlin-2950159", "Берлин, Германия", "DE", 52.52, 13.405, "Europe/Berlin", "Berlin"),
    _place("es-madrid-3117735", "Мадрид, Испания", "ES", 40.4168, -3.7038, "Europe/Madrid", "Madrid"),
    _place("it-rome-3169070", "Рим, Италия", "IT", 41.9028, 12.4964, "Europe/Rome", "Rome", "Roma"),
    _place("gr-athens-264371", "Афины, Греция", "GR", 37.9838, 23.7275, "Europe/Athens", "Athens"),
    _place("tr-istanbul-745044", "Стамбул, Турция", "TR", 41.0082, 28.9784, "Europe/Istanbul", "Istanbul"),
    _place("ae-dubai-292223", "Дубай, ОАЭ", "AE", 25.2048, 55.2708, "Asia/Dubai", "Dubai"),
    _place("us-new-york-5128581", "Нью-Йорк, США", "US", 40.7128, -74.006, "America/New_York", "New York", "NYC"),
    _place("us-los-angeles-5368361", "Лос-Анджелес, США", "US", 34.0522, -118.2437, "America/Los_Angeles", "Los Angeles", "LA"),
    _place("ca-toronto-6167865", "Торонто, Канада", "CA", 43.6532, -79.3832, "America/Toronto", "Toronto"),
    _place("mx-mexico-city-3530597", "Мехико, Мексика", "MX", 19.4326, -99.1332, "America/Mexico_City", "Mexico City", "Ciudad de Mexico"),
    _place("br-sao-paulo-3448439", "Сан-Паулу, Бразилия", "BR", -23.5505, -46.6333, "America/Sao_Paulo", "Sao Paulo", "São Paulo"),
    _place("ar-buenos-aires-3435910", "Буэнос-Айрес, Аргентина", "AR", -34.6037, -58.3816, "America/Argentina/Buenos_Aires", "Buenos Aires"),
    _place("in-delhi-1273294", "Дели, Индия", "IN", 28.6139, 77.209, "Asia/Kolkata", "Delhi", "New Delhi"),
    _place("in-mumbai-1275339", "Мумбаи, Индия", "IN", 19.076, 72.8777, "Asia/Kolkata", "Mumbai", "Bombay"),
    _place("cn-beijing-1816670", "Пекин, Китай", "CN", 39.9042, 116.4074, "Asia/Shanghai", "Beijing"),
    _place("jp-tokyo-1850147", "Токио, Япония", "JP", 35.6762, 139.6503, "Asia/Tokyo", "Tokyo"),
    _place("kr-seoul-1835848", "Сеул, Южная Корея", "KR", 37.5665, 126.978, "Asia/Seoul", "Seoul"),
    _place("th-bangkok-1609350", "Бангкок, Таиланд", "TH", 13.7563, 100.5018, "Asia/Bangkok", "Bangkok"),
    _place("id-jakarta-1642911", "Джакарта, Индонезия", "ID", -6.2088, 106.8456, "Asia/Jakarta", "Jakarta"),
    _place("au-sydney-2147714", "Сидней, Австралия", "AU", -33.8688, 151.2093, "Australia/Sydney", "Sydney"),
    _place("nz-auckland-2193733", "Окленд, Новая Зеландия", "NZ", -36.8485, 174.7633, "Pacific/Auckland", "Auckland"),
    _place("za-cape-town-3369157", "Кейптаун, ЮАР", "ZA", -33.9249, 18.4241, "Africa/Johannesburg", "Cape Town"),
    _place("eg-cairo-360630", "Каир, Египет", "EG", 30.0444, 31.2357, "Africa/Cairo", "Cairo"),
)

# Kept as a small compatibility export for the existing calculator tests.
PLACES = tuple(entry.place for entry in DEFAULT_LOCAL_PLACES)


def _dataset_records(payload: Any) -> Iterable[dict[str, Any]]:
    records = payload.get("places") if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError("Локальный справочник мест должен содержать JSON-массив places")
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Каждая запись локального справочника мест должна быть объектом")
        yield record


def load_local_places(dataset_path: str | Path) -> tuple[LocalPlace, ...]:
    """Load a versioned licensed registry without network access."""

    path = Path(dataset_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise RuntimeError(f"Не найден локальный справочник мест: {path}") from error
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Локальный справочник мест содержит некорректный JSON: {path}") from error

    entries: list[LocalPlace] = []
    place_ids: set[str] = set()
    for record in _dataset_records(payload):
        aliases = record.get("alternate_names", [])
        if not isinstance(aliases, list) or not all(isinstance(alias, str) for alias in aliases):
            raise ValueError("alternate_names должен быть массивом строк")
        place = Place.model_validate({key: value for key, value in record.items() if key != "alternate_names"})
        if place.place_id in place_ids:
            raise ValueError(f"Повторяющийся place_id в локальном справочнике: {place.place_id}")
        place_ids.add(place.place_id)
        entries.append(LocalPlace(place=place, alternate_names=tuple(alias.strip() for alias in aliases if alias.strip())))

    if not entries:
        raise ValueError("Локальный справочник мест не содержит записей")
    return tuple(entries)


class PlaceRegistry:
    def __init__(self, dataset_path: str | Path | None = None) -> None:
        configured_path = dataset_path or os.getenv("VEDICWAY_PLACE_DATASET_PATH")
        if configured_path:
            self._entries = load_local_places(configured_path)
        else:
            if os.getenv("VEDICWAY_ENV", "development").casefold() == "production":
                raise RuntimeError("Для production требуется VEDICWAY_PLACE_DATASET_PATH с лицензированным локальным справочником мест")
            self._entries = DEFAULT_LOCAL_PLACES
        self._by_id = {entry.place.place_id: entry.place for entry in self._entries}

    def search(self, query: str, limit: int = 8) -> list[Place]:
        needle = query.casefold().strip()
        if len(needle) < 2:
            return []
        bounded_limit = min(max(limit, 1), 20)

        def score(entry: LocalPlace) -> tuple[int, str]:
            terms = tuple(term.casefold() for term in entry.search_terms)
            exact = any(term == needle for term in terms)
            starts = any(term.startswith(needle) for term in terms)
            return (0 if exact else 1 if starts else 2, entry.place.display_name)

        matches = [entry for entry in self._entries if any(needle in term.casefold() for term in entry.search_terms)]
        return [entry.place for entry in sorted(matches, key=score)[:bounded_limit]]

    def get(self, place_id: str) -> Place | None:
        return self._by_id.get(place_id)
