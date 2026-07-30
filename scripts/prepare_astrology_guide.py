from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend" / "src"))

from vedicway_backend.content_api import _plain_text, sanitize_article_html  # noqa: E402

CATEGORIES = (
    "Основы астрологии",
    "Планеты и дома",
    "Время и циклы",
    "Практика чтения карты",
)
CATEGORY_DESCRIPTIONS = {
    "Основы астрологии": (
        "Термины, устройство сидерической карты и базовый язык джйотиша."
    ),
    "Планеты и дома": (
        "Грахи, бхавы и связи, из которых складывается предметное чтение карты."
    ),
    "Время и циклы": (
        "Даши, транзиты, панчанга и расчётные правила работы со временем."
    ),
    "Практика чтения карты": (
        "Пошаговые алгоритмы, проверка гипотез и продвинутый синтез показателей."
    ),
}
SLUG_RENAMES = {
    "лунная-priroda-natalnoy-karty": "lunnaya-priroda-natalnoy-karty",
}
LINK_RENAMES = {
    "/guide/лунная-priroda-natalnoy-karty": (
        "/guide/lunnaya-priroda-natalnoy-karty"
    ),
    "/guide/dostoinstva-planet-v-dzhyotishe": (
        "/guide/svakshetra-mulatrikona-uchcha"
    ),
    "/guide/rashi-v-dzhyotish": "/guide/rashi-v-dzhyotishe",
}
SEO_TITLE_OVERRIDES = {
    "hozyeva-rashi": "Хозяева раши: управление знаками в джйотише",
    "karana-polovina-titkhi": "Карана в панчанге: расчёт половины титхи",
    "navagraha-devyat-grah": "Наваграха в джйотише: девять грах карты",
    "titkhi-lunnyy-den": "Титхи в джйотише: как рассчитать лунный день",
    "trikony-v-dzhyotishe": "Триконы в джйотише: значение 5-го и 9-го домов",
    "vara-den-nedeli-v-panchange": "Вара в панчанге: день недели в джйотише",
}
FOCUS_KEYPHRASE_OVERRIDES = {
    "algoritm-chteniya-natalnoy-karty": "алгоритм чтения натальной карты",
    "kak-chitat-natalnuyu-kartu": "как читать натальную карту в джйотише",
    "luna-v-dzhyotish": "значение Луны в джйотише",
    "lunnaya-priroda-natalnoy-karty": "положение Луны в натальной карте",
    "solnce-v-dzhyotish": "базовые сигнификации Солнца",
    "solntse-v-dzhyotishe": "Солнце в натальной карте джйотиш",
    "upravitel-doma": "положение управителя дома",
    "znak-dom-upravitel": "связь знака дома и управителя",
}
EXPERT_SLUG_PARTS = (
    "algorithm",
    "algoritm",
    "antardasha",
    "argala",
    "arudha",
    "ashtakavarga",
    "ashtottari",
    "ayanamsha-lahiri",
    "balance-at-birth",
    "bphs-dasha",
    "calculation",
    "chara-dasha",
    "compare-vimshottari",
    "d1-i-drobnie",
    "d7-",
    "d9-",
    "d10-",
    "d12-",
    "d20-",
    "d24-",
    "d30-",
    "d60-",
    "dasha-i-tranzity",
    "dasha-reading",
    "drugie-sistemy-dash",
    "godovoy-prognoz",
    "hronologiya-sobytiy",
    "istoricheskiy-chasovoy",
    "jaimini",
    "karakamsha",
    "kogda-podklyuchat-drugie-vargi",
    "moon-based-and-lagna",
    "nested-periods",
    "ogranicheniya-rascheta",
    "prashna",
    "pratyantardasha",
    "rashi-dashi",
    "rashi-i-navamsha",
    "rektifikaciya",
    "sistema-jaimini",
    "sopostavlenie-dashi",
    "tajika",
    "upagraha",
    "upapada",
    "vargottama",
    "varshaphala",
    "vedha-v-tranzitah",
    "vimshopaka",
    "vimshottari-antardasha",
    "vimshottari-balance",
    "vimshottari-start",
    "when-to-use-pratyantardasha",
    "yogini-",
)
EXPERT_EXACT = {
    "bazovaya-muhurta-poryadok-proverki",
    "granica-nakshatry-luny",
    "granica-znaka-lagny",
    "lagna-na-granice-znaka",
    "mestnoe-zvezdnoe-vremya-i-lagna",
    "muhurta-v-dzhyotish",
    "ocenka-sily-doma",
    "ocenka-sily-planety",
    "panchanga-dlya-muhurty",
    "proverka-gipotezy-vremeni",
    "proverka-yogi",
    "rangirovanie-faktorov-karty",
    "retrogradnost-i-stacionarnost-grah",
    "shodashavarga-drobnie-karty",
    "sostavnoe-otnoshenie-grah",
    "tithi-nakshatra-yoga-raschet",
    "vimshottari-dasha",
    "vremennoe-druzhestvo-grah",
    "yoga-panchangi",
}
BEGINNER_EXACT = {
    "ayanamsha",
    "dashi-kak-kalendar",
    "dashi-v-dzhyotish",
    "dzhyotish-i-tropicheskaya-astrologiya",
    "gochara-transity-otnositelno-natalnoy-luny",
    "nakshatry-i-pady",
    "sistema-jaimini-dlya-nachinayushchih",
    "tranzity-i-natalnaya-karta",
    "vargi-drobnie-karty",
}


def _json_read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _repair_mojibake(value: str) -> str:
    markers = ("Р°", "Рµ", "Рё", "РЅ", "Рѕ", "С‚", "СЏ", "вЂ", "В°")
    if not any(marker in value for marker in markers):
        return value
    try:
        repaired = value.encode("cp1251").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value
    return repaired if repaired.count("Р") + repaired.count("С") < value.count("Р") + value.count("С") else value


def _repair_tree(value: Any) -> Any:
    if isinstance(value, str):
        return _repair_mojibake(value)
    if isinstance(value, list):
        return [_repair_tree(item) for item in value]
    if isinstance(value, dict):
        return {key: _repair_tree(item) for key, item in value.items()}
    return value


def _strip_markup(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def _truncate(value: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= limit:
        return value
    shortened = value[: limit + 1].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return shortened.rstrip(".") + "."


def _first_paragraphs(article_html: str) -> list[str]:
    return [
        _strip_markup(match)
        for match in re.findall(r"<p\b[^>]*>(.*?)</p>", article_html, flags=re.I | re.S)
        if _strip_markup(match)
    ]


def _excerpt(article_html: str) -> str:
    paragraphs = _first_paragraphs(article_html)
    if not paragraphs:
        raise ValueError("В статье нет вводного абзаца")
    return _truncate(" ".join(paragraphs[:2]), 280)


def _meta_description(article_html: str) -> str:
    paragraphs = _first_paragraphs(article_html)
    if not paragraphs:
        raise ValueError("В статье нет текста для meta description")
    candidate = paragraphs[0]
    if len(candidate) < 120 and len(paragraphs) > 1:
        candidate = f"{candidate} {paragraphs[1]}"
    return _truncate(candidate, 160)


def _normalize_links(value: str) -> str:
    for old, new in sorted(LINK_RENAMES.items(), key=lambda item: len(item[0]), reverse=True):
        value = re.sub(
            rf"{re.escape(old)}(?=[\"'\s)#?]|$)",
            new,
            value,
        )
    return value


def _normalize_future_copy(value: str) -> str:
    replacements = {
        "в будущую статью": "в отдельный материал",
        "В будущую статью": "В отдельный материал",
        "в будущей статье": "в статье",
        "В будущей статье": "В статье",
        "будущая статья": "статья",
        "будущую статью": "статью",
        "будущей статье": "статье",
        "в планируемой статье": "в статье",
        "В планируемой статье": "В статье",
        "можно будет прочитать": "можно прочитать",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    return value


def _article_body(raw_html: str) -> str:
    article_match = re.search(
        r"<article\b[^>]*>(?P<body>.*?)</article>",
        raw_html,
        flags=re.I | re.S,
    )
    body = article_match.group("body") if article_match else raw_html
    body = re.sub(r"<script\b[^>]*>.*?</script>", "", body, flags=re.I | re.S)
    body = re.sub(r"<style\b[^>]*>.*?</style>", "", body, flags=re.I | re.S)
    body = re.sub(
        r"<figure\b[^>]*>\s*<img\b[^>]*\bsrc=[\"'][^\"']*cover[^\"']*[\"'][^>]*>"
        r"\s*(?:<figcaption\b[^>]*>.*?</figcaption>\s*)?</figure>",
        "",
        body,
        flags=re.I | re.S,
    )
    body = re.sub(
        r"<img\b[^>]*\bsrc=[\"'][^\"']*cover[^\"']*[\"'][^>]*>",
        "",
        body,
        flags=re.I | re.S,
    )
    body = re.sub(
        r"<p\b[^>]*class=[\"'][^\"']*article-category[^\"']*[\"'][^>]*>.*?</p>",
        "",
        body,
        flags=re.I | re.S,
    )
    body = re.sub(r"<h1\b[^>]*>.*?</h1>", "", body, count=1, flags=re.I | re.S)
    body = re.sub(r"</?header\b[^>]*>", "", body, flags=re.I)
    body = re.sub(r"<i(\s[^>]*)?>", r"<em\1>", body, flags=re.I)
    body = re.sub(r"</i>", "</em>", body, flags=re.I)
    body = _normalize_future_copy(_normalize_links(body))
    sanitized = sanitize_article_html(body)
    headings = []
    for match in re.findall(r"<h2\b[^>]*>(.*?)</h2>", sanitized, flags=re.I | re.S):
        title = _truncate(_strip_markup(match), 100)
        if title and title not in headings:
            headings.append(title)
    if headings:
        summary = (
            '<aside data-kind="summary"><strong>В этой статье</strong><ul>'
            + "".join(f"<li>{html.escape(title)}</li>" for title in headings[:4])
            + "</ul></aside>"
        )
        sanitized = sanitize_article_html(summary + sanitized)
    return sanitized


def _difficulty(slug: str, priority: str | None) -> str:
    if slug in BEGINNER_EXACT:
        return "beginner"
    if slug in EXPERT_EXACT or any(part in slug for part in EXPERT_SLUG_PARTS):
        return "expert"
    if priority == "low":
        return "expert"
    return "beginner"


def _tags(category: str, focus_keyphrase: str, title: str) -> list[str]:
    tags = [category, focus_keyphrase]
    lowered = f"{title} {focus_keyphrase}".casefold()
    topic_tags = (
        ("наталь", "натальная карта"),
        ("накшатр", "накшатры"),
        ("планет", "планеты"),
        ("грах", "грахи"),
        ("дом", "дома"),
        ("бхав", "бхавы"),
        ("даш", "даши"),
        ("транзит", "транзиты"),
        ("джаймини", "Джаймини"),
        ("jaimini", "Джаймини"),
        ("варг", "варги"),
        ("панчанг", "панчанга"),
        ("лагн", "лагна"),
    )
    for needle, tag in topic_tags:
        if needle in lowered:
            tags.append(tag)
    return list(dict.fromkeys(tag for tag in tags if tag))[:6]


def _source_urls(sources: Any) -> list[str]:
    if not isinstance(sources, list):
        return []
    urls = []
    for source in sources:
        if isinstance(source, dict):
            url = str(source.get("url") or source.get("URL") or "").strip()
            if url.startswith(("https://", "http://")):
                urls.append(url)
    return list(dict.fromkeys(urls))


def _cover_path(source_root: Path, article_dir: Path, manifest: dict[str, Any]) -> Path:
    candidates: list[Path] = []
    cover = manifest.get("cover")
    if isinstance(cover, dict) and cover.get("path"):
        candidate = source_root.parents[1] / str(cover["path"])
        if candidate.is_file():
            candidates.append(candidate.resolve())
    for suffix in (".png", ".webp", ".jpg", ".jpeg"):
        candidate = article_dir / f"cover{suffix}"
        if candidate.is_file():
            candidates.append(candidate.resolve())
    media_dir = source_root / "media" / article_dir.name
    for suffix in (".png", ".webp", ".jpg", ".jpeg"):
        candidate = media_dir / f"cover{suffix}"
        if candidate.is_file():
            candidates.append(candidate.resolve())
    candidates = list(dict.fromkeys(candidates))
    if not candidates:
        raise FileNotFoundError(f"Обложка не найдена: {article_dir.name}")
    manifest_hash = (
        str(cover.get("sha256") or "").casefold()
        if isinstance(cover, dict)
        else ""
    )
    if manifest_hash:
        for candidate in candidates:
            digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
            if digest == manifest_hash:
                return candidate
    return candidates[0]


def _write_cover(source: Path, destination: Path) -> tuple[int, int, str]:
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
        if image.width < 1200 or image.height < 630:
            raise ValueError(
                f"Обложка меньше 1200×630: {source} ({image.width}×{image.height})"
            )
        if image.width > 1920:
            height = round(image.height * 1920 / image.width)
            image = image.resize((1920, height), Image.Resampling.LANCZOS)
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(destination, "WEBP", quality=90, method=6)
    raw = destination.read_bytes()
    return image.width, image.height, hashlib.sha256(raw).hexdigest()


def _topic_order(source_root: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    topic_map = _json_read(source_root / "research" / "topic-map.json")
    entries = topic_map.get("entries")
    if not isinstance(entries, list):
        raise ValueError("research/topic-map.json не содержит entries")
    by_slug = {
        SLUG_RENAMES.get(str(entry["slug"]), str(entry["slug"])): entry
        for entry in entries
    }
    order: list[str] = []
    for category in CATEGORIES:
        order.extend(
            SLUG_RENAMES.get(str(entry["slug"]), str(entry["slug"]))
            for entry in entries
            if entry.get("category") == category
        )
    return by_slug, order


def prepare(source_root: Path, destination_root: Path, catalog_output: Path) -> dict[str, Any]:
    article_root = source_root / "articles"
    if not article_root.is_dir():
        raise FileNotFoundError(f"Каталог статей не найден: {article_root}")
    topic_by_slug, ordered_slugs = _topic_order(source_root)
    rows: dict[str, dict[str, Any]] = {}
    validation_rows = []

    for article_dir in sorted(path for path in article_root.iterdir() if path.is_dir()):
        original_manifest = _json_read(article_dir / "manifest.json")
        manifest = _repair_tree(original_manifest)
        original_slug = str(original_manifest.get("slug") or article_dir.name)
        slug = SLUG_RENAMES.get(original_slug, original_slug)
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
            raise ValueError(f"Недопустимый slug после нормализации: {slug}")

        raw_html = (article_dir / "article.html").read_text(encoding="utf-8")
        body = _article_body(raw_html)
        plain_chars = len(_plain_text(body))
        if plain_chars < 4000:
            raise ValueError(f"{slug}: после очистки осталось {plain_chars} символов")
        title_match = re.search(r"<h1\b[^>]*>(.*?)</h1>", raw_html, flags=re.I | re.S)
        html_title = _strip_markup(title_match.group(1)) if title_match else ""
        title = _repair_mojibake(str(manifest.get("title") or "")) or html_title
        if "?" * 3 in title:
            title = html_title

        topic = topic_by_slug.get(slug, {})
        category = _repair_mojibake(
            str(manifest.get("category") or topic.get("category") or "")
        )
        if category not in CATEGORIES:
            raise ValueError(f"{slug}: неизвестная категория {category!r}")
        seo_source = manifest.get("seo") if isinstance(manifest.get("seo"), dict) else manifest
        seo_title = SEO_TITLE_OVERRIDES.get(
            slug,
            _repair_mojibake(str(seo_source.get("seo_title") or title)),
        )
        if len(seo_title) > 65:
            seo_title = _truncate(seo_title, 65)
        meta_description = _repair_mojibake(
            str(seo_source.get("meta_description") or "")
        )
        if not 120 <= len(meta_description) <= 170:
            meta_description = _meta_description(body)
        excerpt = _repair_mojibake(str(seo_source.get("excerpt") or ""))
        if not 80 <= len(excerpt) <= 300:
            excerpt = _excerpt(body)
        focus_keyphrase = FOCUS_KEYPHRASE_OVERRIDES.get(
            slug,
            _repair_mojibake(
                str(seo_source.get("focus_keyphrase") or title.split(":", 1)[0])
            ),
        )
        priority = str(topic.get("priority") or "") or None
        difficulty = _difficulty(slug, priority)
        sources = _repair_tree(_json_read(article_dir / "sources.json"))
        citations = _source_urls(sources)

        target_dir = destination_root / slug
        target_dir.mkdir(parents=True, exist_ok=True)
        cover_source = _cover_path(source_root, article_dir, original_manifest)
        cover_target = target_dir / "cover.webp"
        cover_width, cover_height, cover_hash = _write_cover(
            cover_source,
            cover_target,
        )
        cover_data = manifest.get("cover") if isinstance(manifest.get("cover"), dict) else {}
        cover_alt = _repair_mojibake(
            str(cover_data.get("alt") or f"Иллюстрация к статье «{title}»")
        )

        normalized_manifest = {
            **manifest,
            "slug": slug,
            "title": title,
            "category": category,
            "difficulty": difficulty,
            "status": "ready_for_import",
            "seo": {
                "seo_title": seo_title,
                "meta_description": meta_description,
                "focus_keyphrase": focus_keyphrase,
                "canonical_url": f"https://vedicway.ru/guide/{slug}",
                "excerpt": excerpt,
            },
            "canonical": f"https://vedicway.ru/guide/{slug}",
            "tags": _tags(category, focus_keyphrase, title),
            "schema_extra": {
                "about": [
                    {"@type": "Thing", "name": category},
                    {"@type": "Thing", "name": focus_keyphrase},
                ],
                "citation": citations,
                "learningResourceType": "Guide",
            },
            "cover": {
                **cover_data,
                "asset_id": f"cover-{slug}",
                "path": f"content/astrology-guide/articles/{slug}/cover.webp",
                "alt": cover_alt,
                "status": "ready",
                "width": cover_width,
                "height": cover_height,
                "sha256": cover_hash,
            },
        }
        _json_write(target_dir / "manifest.json", normalized_manifest)
        _json_write(target_dir / "sources.json", sources)
        (target_dir / "article.html").write_text(
            body + "\n",
            encoding="utf-8",
            newline="\n",
        )
        markdown = (article_dir / "article.md").read_text(encoding="utf-8")
        markdown = _normalize_future_copy(_normalize_links(markdown))
        (target_dir / "article.md").write_text(
            markdown.rstrip() + "\n",
            encoding="utf-8",
            newline="\n",
        )
        rows[slug] = {
            "slug": slug,
            "label": title,
            "category": category,
            "difficulty": difficulty,
        }
        validation_rows.append(
            {
                "slug": slug,
                "plain_chars": plain_chars,
                "cover": {
                    "width": cover_width,
                    "height": cover_height,
                    "sha256": cover_hash,
                },
                "citations": len(citations),
            }
        )

    extras = sorted(set(rows) - set(ordered_slugs))
    for extra in extras:
        category = rows[extra]["category"]
        category_tail = max(
            (index for index, slug in enumerate(ordered_slugs) if rows.get(slug, {}).get("category") == category),
            default=len(ordered_slugs) - 1,
        )
        ordered_slugs.insert(category_tail + 1, extra)
    missing = sorted(set(ordered_slugs) - set(rows))
    if missing:
        raise ValueError(f"В topic-map есть статьи без файлов: {', '.join(missing)}")
    if len(rows) != 202:
        raise ValueError(f"Ожидалось 202 статьи, найдено {len(rows)}")

    catalog = []
    for index, slug in enumerate(ordered_slugs, start=1):
        row = rows[slug]
        catalog.append({**row, "order": index * 10})
    _json_write(catalog_output, catalog)
    _json_write(
        destination_root.parent / "catalog.json",
        {
            "version": 1,
            "article_count": len(catalog),
            "categories": [
                {
                    "name": category,
                    "description": CATEGORY_DESCRIPTIONS[category],
                    "article_count": sum(row["category"] == category for row in catalog),
                    "difficulty": dict(
                        Counter(
                            row["difficulty"]
                            for row in catalog
                            if row["category"] == category
                        )
                    ),
                }
                for category in CATEGORIES
            ],
            "articles": catalog,
        },
    )
    report = {
        "status": "valid",
        "source": "VedicWay-work3/content/astrology-guide/articles",
        "article_count": len(catalog),
        "category_counts": dict(Counter(row["category"] for row in catalog)),
        "difficulty_counts": dict(Counter(row["difficulty"] for row in catalog)),
        "minimum_plain_chars": min(row["plain_chars"] for row in validation_rows),
        "covers": {
            "count": len(validation_rows),
            "minimum_width": min(row["cover"]["width"] for row in validation_rows),
            "minimum_height": min(row["cover"]["height"] for row in validation_rows),
        },
        "citations": sum(row["citations"] for row in validation_rows),
        "repairs": {
            "slug": SLUG_RENAMES,
            "internal_links": LINK_RENAMES,
            "manifest_mojibake": ["nakshatry-i-pady"],
        },
    }
    _json_write(destination_root.parent / "preparation-report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize the work3 astrology-guide corpus for the Codex gate"
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument(
        "--destination",
        type=Path,
        default=REPOSITORY_ROOT / "content" / "astrology-guide" / "articles",
    )
    parser.add_argument(
        "--catalog-output",
        type=Path,
        default=(
            REPOSITORY_ROOT
            / "backend"
            / "src"
            / "vedicway_backend"
            / "guide_catalog_data.json"
        ),
    )
    args = parser.parse_args()
    report = prepare(
        args.source.resolve(),
        args.destination.resolve(),
        args.catalog_output.resolve(),
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
