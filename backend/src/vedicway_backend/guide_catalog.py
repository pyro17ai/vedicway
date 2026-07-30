"""Кодовый каталог гида.

Состав материалов генерируется из ``content/astrology-guide/articles`` командой
``scripts/prepare_astrology_guide.py`` и меняется только коммитом. Агент может
обновить статью из каталога, но не создать незарегистрированный адрес.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class GuideCategory:
    name: str
    order: int
    description: str


@dataclass(frozen=True, slots=True)
class GuideArticleSlot:
    slug: str
    order: int
    label: str
    category: str
    difficulty: str


GUIDE_CATEGORIES: tuple[GuideCategory, ...] = (
    GuideCategory(
        name="Основы астрологии",
        order=10,
        description="Термины, устройство сидерической карты и базовый язык джйотиша.",
    ),
    GuideCategory(
        name="Планеты и дома",
        order=20,
        description=(
            "Грахи, бхавы и связи, из которых складывается предметное чтение карты."
        ),
    ),
    GuideCategory(
        name="Время и циклы",
        order=30,
        description="Даши, транзиты, панчанга и расчётные правила работы со временем.",
    ),
    GuideCategory(
        name="Практика чтения карты",
        order=40,
        description=(
            "Пошаговые алгоритмы, проверка гипотез и продвинутый синтез показателей."
        ),
    ),
)

_catalog_path = Path(__file__).with_name("guide_catalog_data.json")
_catalog_data = json.loads(_catalog_path.read_text(encoding="utf-8"))
if not isinstance(_catalog_data, list):
    raise RuntimeError("guide_catalog_data.json должен содержать массив")

GUIDE_ARTICLE_SLOTS: tuple[GuideArticleSlot, ...] = tuple(
    GuideArticleSlot(
        slug=str(item["slug"]),
        order=int(item["order"]),
        label=str(item["label"]),
        category=str(item["category"]),
        difficulty=str(item["difficulty"]),
    )
    for item in _catalog_data
)

_category_names = {category.name for category in GUIDE_CATEGORIES}
_slugs = [slot.slug for slot in GUIDE_ARTICLE_SLOTS]
_orders = [slot.order for slot in GUIDE_ARTICLE_SLOTS]
if len(GUIDE_ARTICLE_SLOTS) != 202:
    raise RuntimeError("Кодовый каталог гида должен содержать 202 статьи")
if len(set(_slugs)) != len(_slugs):
    raise RuntimeError("В кодовом каталоге гида повторяется slug")
if len(set(_orders)) != len(_orders):
    raise RuntimeError("В кодовом каталоге гида повторяется порядок")
if any(not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug) for slug in _slugs):
    raise RuntimeError("Кодовый каталог гида содержит недопустимый slug")
if any(slot.category not in _category_names for slot in GUIDE_ARTICLE_SLOTS):
    raise RuntimeError("Статья гида привязана к неизвестному разделу")
if any(slot.difficulty not in {"beginner", "expert"} for slot in GUIDE_ARTICLE_SLOTS):
    raise RuntimeError("Статья гида содержит неизвестный уровень сложности")

GUIDE_SLUGS = frozenset(_slugs)
GUIDE_ORDER = {slot.slug: slot.order for slot in GUIDE_ARTICLE_SLOTS}
GUIDE_SLOT_BY_SLUG = {slot.slug: slot for slot in GUIDE_ARTICLE_SLOTS}
GUIDE_CATEGORY_COUNTS = {
    category.name: sum(slot.category == category.name for slot in GUIDE_ARTICLE_SLOTS)
    for category in GUIDE_CATEGORIES
}
