from __future__ import annotations

from enum import StrEnum


class DomainSlug(StrEnum):
    CHARACTER = "character"
    INNER_SUPPORT = "inner_support"
    RELATIONSHIPS = "relationships"
    FAMILY_HOME = "family_home"
    WORK = "work"
    MONEY = "money"
    LEARNING = "learning"
    CURRENT_PERIOD = "current_period"


DOMAIN_ORDER = [
    DomainSlug.CHARACTER,
    DomainSlug.INNER_SUPPORT,
    DomainSlug.RELATIONSHIPS,
    DomainSlug.FAMILY_HOME,
    DomainSlug.WORK,
    DomainSlug.MONEY,
    DomainSlug.LEARNING,
    DomainSlug.CURRENT_PERIOD,
]

DOMAIN_LABELS_RU = {
    DomainSlug.CHARACTER: "Характер",
    DomainSlug.INNER_SUPPORT: "Внутренние опоры",
    DomainSlug.RELATIONSHIPS: "Отношения",
    DomainSlug.FAMILY_HOME: "Семья и дом",
    DomainSlug.WORK: "Работа",
    DomainSlug.MONEY: "Деньги",
    DomainSlug.LEARNING: "Обучение",
    DomainSlug.CURRENT_PERIOD: "Текущий период",
}

VARGA_ALLOWLIST = ("D1", "D2", "D3", "D4", "D7", "D9", "D10", "D12", "D16", "D20", "D24", "D27", "D30", "D40", "D45", "D60")
REQUIRED_VARGAS = ("D1", "D2", "D9", "D10")

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

SIGN_CODES = (
    "ARIES",
    "TAURUS",
    "GEMINI",
    "CANCER",
    "LEO",
    "VIRGO",
    "LIBRA",
    "SCORPIO",
    "SAGITTARIUS",
    "CAPRICORN",
    "AQUARIUS",
    "PISCES",
)

PLANET_LABELS_RU = {
    "Sun": ("SUN", "Солнце", "Су"),
    "Moon": ("MOON", "Луна", "Лу"),
    "Mars": ("MARS", "Марс", "Ма"),
    "Mercury": ("MERCURY", "Меркурий", "Ме"),
    "Jupiter": ("JUPITER", "Юпитер", "Юп"),
    "Venus": ("VENUS", "Венера", "Ве"),
    "Saturn": ("SATURN", "Сатурн", "Са"),
    "Rahu": ("RAHU", "Раху", "Ра"),
    "Ketu": ("KETU", "Кету", "Ке"),
    "Uranus": ("URANUS", "Уран", "Ур"),
    "Neptune": ("NEPTUNE", "Нептун", "Не"),
    "Pluto": ("PLUTO", "Плутон", "Пл"),
}

CLASSICAL_PLANETS = frozenset({"SUN", "MOON", "MARS", "MERCURY", "JUPITER", "VENUS", "SATURN", "RAHU", "KETU"})
