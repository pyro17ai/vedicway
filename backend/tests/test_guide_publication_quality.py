from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.publish_astrology_guide import (  # noqa: E402
    CorpusArticle,
    _assert_article_quality,
    select_articles,
)


def test_publication_quality_accepts_known_internal_routes() -> None:
    _assert_article_quality(
        "primer",
        '<h2>Раздел</h2><p>Проверяем текст.</p>'
        '<a href="/#natal-chart-form">Рассчитать карту</a>'
        '<a href="/guide/sosednyaya-statya">Продолжить чтение</a>',
        {"primer", "sosednyaya-statya"},
    )


def test_cohort_selection_checks_internal_schema_citations() -> None:
    article = CorpusArticle(
        slug="primer",
        directory=Path("primer"),
        manifest={
            "schema_extra": {
                "citation": ["https://vedicway.ru/guide/sosednyaya-statya"]
            }
        },
        content_html="<p>Текст.</p>",
        cover_path=Path("primer/cover.webp"),
    )
    neighbor = CorpusArticle(
        slug="sosednyaya-statya",
        directory=Path("sosednyaya-statya"),
        manifest={},
        content_html="<p>Текст.</p>",
        cover_path=Path("sosednyaya-statya/cover.webp"),
    )

    with pytest.raises(ValueError, match="ссылки на неопубликованные статьи"):
        select_articles([article, neighbor], {"primer"})
    assert select_articles(
        [article, neighbor],
        {"primer", "sosednyaya-statya"},
    ) == [article, neighbor]


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (
            '<p>РљР°Рє РїСЂРѕРІРµСЂРёС‚СЊ С‚РµРєСЃС‚</p>'
            '<a href="/#natal-chart-form">Карта</a>',
            "битой кодировки",
        ),
        (
            '<p>Проверяем текст.</p><a href="/chart">Карта</a>',
            "неизвестный внутренний маршрут",
        ),
    ],
)
def test_publication_quality_blocks_broken_content(
    content: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _assert_article_quality("primer", content, {"primer"})
