from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend" / "src"))

from vedicway_backend.content_api import (  # noqa: E402
    ContentArticlePayload,
    _content_payload_hash,
    _media_payload_hash,
    _plain_text,
    sanitize_article_html,
)
from vedicway_backend.guide_catalog import (  # noqa: E402
    GUIDE_ARTICLE_SLOTS,
    GUIDE_CATEGORIES,
)


@dataclass(frozen=True, slots=True)
class CorpusArticle:
    slug: str
    directory: Path
    manifest: dict[str, Any]
    content_html: str
    cover_path: Path


MOJIBAKE_MARKERS = (
    "Рљ",
    "Р°",
    "Рµ",
    "РЅ",
    "Рѕ",
    "Рё",
    "С‚",
    "СЃ",
    "СЏ",
    "СЂ",
)
ALLOWED_CONTENT_ROUTES = {
    "/",
    "/#natal-chart-form",
    "/guide",
    "/blog",
    "/about",
    "/methodology",
    "/editorial-policy",
}
FIRST_INDEXABLE_COHORT = frozenset(
    {
        "algoritm-chteniya-natalnoy-karty",
        "ayanamsha-lahiri-raman-true-chitra",
        "bhava-i-lagna",
        "chto-izuchaet-dzhyotish",
        "dashi-v-dzhyotish",
        "dvenadcat-bhav",
        "dvenadcat-rashi",
        "dzhanma-nakshatra-luny",
        "graha-v-dzhyotishe",
        "hozyain-doma-ot-lagny",
        "kak-chitat-natalnuyu-kartu",
        "karta-bez-vremeni-rozhdeniya",
        "lagna-i-ascendent",
        "lagna-i-pervyy-dom",
        "lagna-na-granice-znaka",
        "nakshatra-v-dzhyotishe",
        "ogranicheniya-rascheta-natalnoj-karty",
        "pancha-mahapurusha-yoga",
        "pervyy-prohod-po-karte",
        "rashi-bhava-lagna-i-doma",
        "rashi-i-navamsha",
        "rashi-v-dzhyotishe",
        "shodashavarga-drobnie-karty",
        "siderealnyj-i-tropicheskij-zodiak",
        "sistemy-domov-v-sidereicheskoj-karte",
        "tranzity-i-natalnaya-karta",
        "vargi-drobnie-karty",
        "vybor-aynamshi-i-sistemy-domov",
        "yoga-v-dzhyotishe",
    }
)


def _assert_article_quality(
    slug: str,
    content_html: str,
    catalog_slugs: set[str],
) -> None:
    mojibake_hits = sum(content_html.count(marker) for marker in MOJIBAKE_MARKERS)
    if mojibake_hits >= 3:
        raise ValueError(f"{slug}: article.html содержит признаки битой кодировки")

    internal_routes = re.findall(r'href=["\'](?P<route>/[^"\']*)', content_html, flags=re.I)
    if not internal_routes:
        raise ValueError(f"{slug}: article.html не содержит внутренних ссылок")
    for route in internal_routes:
        clean_route = route.split("?", 1)[0]
        if clean_route.startswith("/guide/"):
            target = clean_route.removeprefix("/guide/").split("#", 1)[0].rstrip("/")
            if target not in catalog_slugs:
                raise ValueError(
                    f"{slug}: внутренняя ссылка ведёт на неизвестный {target}"
                )
            continue
        if clean_route not in ALLOWED_CONTENT_ROUTES:
            raise ValueError(f"{slug}: неизвестный внутренний маршрут {route}")

    plain = re.sub(r"\s+", " ", _plain_text(content_html)).strip()
    sentences = [
        sentence.strip().casefold()
        for sentence in re.split(r"(?<=[.!?])\s+", plain)
        if len(sentence.strip()) >= 60
    ]
    repeated = Counter(sentences)
    if repeated and max(repeated.values()) >= 10:
        raise ValueError(
            f"{slug}: одно предложение повторяется в статье не менее десяти раз"
        )


def _json_read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _cover_path(manifest: dict[str, Any], directory: Path) -> Path:
    cover = manifest.get("cover")
    if not isinstance(cover, dict):
        raise ValueError(f"{directory.name}: в manifest отсутствует cover")
    declared = str(cover.get("path") or "")
    path = REPOSITORY_ROOT / declared if declared else directory / "cover.webp"
    if not path.is_file():
        raise FileNotFoundError(f"{directory.name}: обложка не найдена: {path}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != str(cover.get("sha256") or "").casefold():
        raise ValueError(f"{directory.name}: SHA-256 обложки не совпал с manifest")
    with Image.open(path) as image:
        width, height = image.size
        if width < 1200 or height < 630:
            raise ValueError(f"{directory.name}: обложка меньше 1200×630")
        if (
            int(cover.get("width") or 0) != width
            or int(cover.get("height") or 0) != height
        ):
            raise ValueError(f"{directory.name}: размеры обложки не совпали с manifest")
    return path


def _schema_extra(manifest: dict[str, Any], slug: str) -> dict[str, Any]:
    value = manifest.get("schema_extra")
    if not isinstance(value, dict):
        raise ValueError(f"{slug}: schema_extra отсутствует")
    citations = value.get("citation")
    if not isinstance(citations, list) or not citations:
        raise ValueError(f"{slug}: Schema.org citation не содержит источников")
    return value


def _payload(article: CorpusArticle, cover_media_id: str) -> ContentArticlePayload:
    manifest = article.manifest
    seo = manifest.get("seo")
    cover = manifest.get("cover")
    if not isinstance(seo, dict) or not isinstance(cover, dict):
        raise ValueError(
            f"{article.slug}: manifest не соответствует публикационному контракту"
        )
    return ContentArticlePayload.model_validate(
        {
            "section": "guide",
            "difficulty": manifest["difficulty"],
            "title": manifest["title"],
            "slug": article.slug,
            "category": manifest["category"],
            "excerpt": seo["excerpt"],
            "content_html": article.content_html,
            "cover_media_id": cover_media_id,
            "cover_image_alt": cover["alt"],
            "seo_title": seo["seo_title"],
            "meta_description": seo["meta_description"],
            "focus_keyphrase": seo["focus_keyphrase"],
            "tags": manifest.get("tags") or [],
            "schema_extra": _schema_extra(manifest, article.slug),
            "author_name": "Редакция VedicWay",
        }
    )


def load_corpus(article_root: Path) -> list[CorpusArticle]:
    slots = {slot.slug: slot for slot in GUIDE_ARTICLE_SLOTS}
    directories = {path.name: path for path in article_root.iterdir() if path.is_dir()}
    if set(directories) != set(slots):
        missing = sorted(set(slots) - set(directories))
        unexpected = sorted(set(directories) - set(slots))
        raise ValueError(
            "Файлы и кодовый каталог расходятся: "
            f"missing={missing!r}, unexpected={unexpected!r}"
        )

    articles: list[CorpusArticle] = []
    seo_titles: list[str] = []
    meta_descriptions: list[str] = []
    focus_keyphrases: list[str] = []
    catalog_slugs = set(slots)
    for slot in GUIDE_ARTICLE_SLOTS:
        directory = directories[slot.slug]
        manifest = _json_read(directory / "manifest.json")
        if not isinstance(manifest, dict):
            raise ValueError(f"{slot.slug}: manifest должен быть объектом")
        if (
            manifest.get("slug") != slot.slug
            or manifest.get("title") != slot.label
            or manifest.get("category") != slot.category
            or manifest.get("difficulty") != slot.difficulty
        ):
            raise ValueError(f"{slot.slug}: manifest расходится с кодовым каталогом")
        if manifest.get("status") != "ready_for_import":
            raise ValueError(f"{slot.slug}: статья не имеет статуса ready_for_import")
        content_html = (directory / "article.html").read_text(encoding="utf-8").strip()
        if sanitize_article_html(content_html) != content_html:
            raise ValueError(
                f"{slot.slug}: article.html меняется после серверной очистки"
            )
        if re.search(r"<(?:h1|article|script|style|img)\b", content_html, flags=re.I):
            raise ValueError(f"{slot.slug}: article.html содержит запрещённую оболочку")
        if len(_plain_text(content_html)) < 4000:
            raise ValueError(f"{slot.slug}: article.html короче 4000 видимых символов")
        if len(re.findall(r"<h2\b", content_html, flags=re.I)) < 3:
            raise ValueError(f"{slot.slug}: article.html содержит меньше трёх H2")
        if re.search(r"\b(?:будущ\w*|планируем\w*)\s+стать", content_html, flags=re.I):
            raise ValueError(f"{slot.slug}: article.html ссылается на будущую статью")
        _assert_article_quality(slot.slug, content_html, catalog_slugs)

        seo = manifest.get("seo")
        if not isinstance(seo, dict):
            raise ValueError(f"{slot.slug}: отсутствует объект seo")
        seo_title = str(seo.get("seo_title") or "")
        meta_description = str(seo.get("meta_description") or "")
        excerpt = str(seo.get("excerpt") or "")
        focus_keyphrase = str(seo.get("focus_keyphrase") or "")
        if not 35 <= len(seo_title) <= 65:
            raise ValueError(f"{slot.slug}: SEO title должен занимать 35–65 символов")
        if not 120 <= len(meta_description) <= 170:
            raise ValueError(
                f"{slot.slug}: meta description должен занимать 120–170 символов"
            )
        if not 80 <= len(excerpt) <= 300:
            raise ValueError(f"{slot.slug}: excerpt должен занимать 80–300 символов")
        if seo.get("canonical_url") != f"https://vedicway.ru/guide/{slot.slug}":
            raise ValueError(f"{slot.slug}: canonical не совпадает с публичным адресом")
        if not focus_keyphrase:
            raise ValueError(f"{slot.slug}: focus keyphrase пуст")
        cover_path = _cover_path(manifest, directory)
        article = CorpusArticle(
            slug=slot.slug,
            directory=directory,
            manifest=manifest,
            content_html=content_html,
            cover_path=cover_path,
        )
        _payload(article, str(uuid.uuid5(uuid.NAMESPACE_URL, f"dry-run:{slot.slug}")))
        articles.append(article)
        seo_titles.append(seo_title.casefold())
        meta_descriptions.append(meta_description.casefold())
        focus_keyphrases.append(focus_keyphrase.casefold())

    for label, values in (
        ("SEO title", seo_titles),
        ("meta description", meta_descriptions),
        ("focus keyphrase", focus_keyphrases),
    ):
        duplicates = sorted(
            value for value, count in Counter(values).items() if count > 1
        )
        if duplicates:
            raise ValueError(f"{label} повторяется: {duplicates!r}")
    for category in GUIDE_CATEGORIES:
        levels = {
            article.manifest["difficulty"]
            for article in articles
            if article.manifest["category"] == category.name
        }
        if levels != {"beginner", "expert"}:
            raise ValueError(f"{category.name}: нужны материалы обоих уровней")
    return articles


def select_articles(
    corpus: list[CorpusArticle],
    requested_slugs: set[str] | None,
) -> list[CorpusArticle]:
    if requested_slugs is None:
        return corpus
    known_slugs = {article.slug for article in corpus}
    unknown = sorted(requested_slugs - known_slugs)
    if unknown:
        raise ValueError(f"Запрошены неизвестные статьи: {unknown!r}")
    selected = [article for article in corpus if article.slug in requested_slugs]
    selected_slugs = {article.slug for article in selected}
    leaked_links: list[str] = []
    for article in selected:
        routes = re.findall(
            r'href=["\'](?P<route>/guide/[^"\']+)',
            article.content_html,
            flags=re.I,
        )
        for citation in article.manifest.get("schema_extra", {}).get(
            "citation",
            [],
        ):
            match = re.match(
                r"https?://(?:www\.)?vedicway\.ru(?P<route>/guide/[^?#]+)",
                str(citation),
                flags=re.I,
            )
            if match:
                routes.append(match.group("route"))
        for route in routes:
            target = route.split("?", 1)[0].split("#", 1)[0].removeprefix(
                "/guide/"
            ).rstrip("/")
            if target and target not in selected_slugs:
                leaked_links.append(f"{article.slug} -> {target}")
    if leaked_links:
        raise ValueError(
            "Выбранная когорта содержит ссылки на неопубликованные статьи: "
            f"{sorted(set(leaked_links))!r}"
        )
    return selected


class Publisher:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.authorization = {"Authorization": f"Bearer {token}"}
        self.client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(120, connect=15),
            follow_redirects=False,
        )

    def close(self) -> None:
        self.client.close()

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_response: httpx.Response | None = None
        for attempt in range(3):
            try:
                response = self.client.request(method, url, **kwargs)
            except httpx.TransportError:
                if attempt == 2:
                    raise
                time.sleep(0.5 * (2**attempt))
                continue
            last_response = response
            if response.status_code < 500 or attempt == 2:
                return response
            time.sleep(0.5 * (2**attempt))
        if last_response is None:
            raise RuntimeError("HTTP-запрос не выполнился")
        return last_response

    def health(self) -> dict[str, Any]:
        response = self._request(
            "GET",
            "/internal/content-agent/health",
            headers=self.authorization,
        )
        response.raise_for_status()
        value = response.json()
        if value.get("guide_slots") != len(GUIDE_ARTICLE_SLOTS):
            raise RuntimeError("Backend запущен со старым кодовым каталогом")
        if value.get("guide_categories") != len(GUIDE_CATEGORIES):
            raise RuntimeError("Backend не сообщает четыре раздела гида")
        return value

    def upload_cover(self, article: CorpusArticle) -> tuple[str, bool]:
        raw = article.cover_path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        cover = article.manifest["cover"]
        title = str(article.manifest["title"])
        alt = str(cover["alt"])
        request_hash = _media_payload_hash(digest, "cover", alt, title, "")
        key = f"codex:guide-cover:{article.slug}:{request_hash[:32]}"
        response = self._request(
            "POST",
            "/internal/content-agent/media",
            headers={
                **self.authorization,
                "Idempotency-Key": key,
                "X-Content-SHA256": digest,
            },
            data={
                "purpose": "cover",
                "alt": alt,
                "title": title,
                "caption": "",
            },
            files={"file": (article.cover_path.name, raw, "image/webp")},
        )
        response.raise_for_status()
        value = response.json()
        return str(value["asset"]["id"]), bool(value["idempotent_replay"])

    def publish_article(
        self,
        article: CorpusArticle,
        cover_media_id: str,
    ) -> tuple[int, bool]:
        payload = _payload(article, cover_media_id)
        digest = _content_payload_hash(payload)
        headers = {
            **self.authorization,
            "Idempotency-Key": f"codex:guide:{article.slug}:{digest[:32]}",
            "X-Content-SHA256": digest,
        }
        current = self._request(
            "GET",
            f"/api/v1/content/guide/articles/{article.slug}",
        )
        if current.status_code == 200:
            headers["If-Match"] = str(current.json()["revision"])
        elif current.status_code != 404:
            current.raise_for_status()
        response = self._request(
            "PUT",
            f"/internal/content-agent/guide/articles/{article.slug}",
            headers=headers,
            json=payload.model_dump(mode="json"),
        )
        response.raise_for_status()
        value = response.json()
        return int(value["article"]["revision"]), bool(value["idempotent_replay"])


def _article_schema(page_html: str) -> dict[str, Any]:
    match = re.search(
        r'<script[^>]*data-vedicway-seo-schema="ssr"[^>]*>(.*?)</script>',
        page_html,
        flags=re.I | re.S,
    )
    if not match:
        raise ValueError("SSR-страница не содержит JSON-LD")
    schema = json.loads(html.unescape(match.group(1)))
    graph = schema.get("@graph") if isinstance(schema, dict) else None
    if not isinstance(graph, list):
        raise ValueError("JSON-LD статьи не содержит @graph")
    article = next(
        (
            item
            for item in graph
            if isinstance(item, dict) and item.get("@type") == "Article"
        ),
        None,
    )
    if not isinstance(article, dict):
        raise ValueError("JSON-LD не содержит Article")
    return article


def verify_publication(
    client: httpx.Client,
    articles: list[CorpusArticle],
) -> dict[str, Any]:
    listing_response = client.get("/api/v1/content/guide/articles")
    listing_response.raise_for_status()
    listing = listing_response.json()
    expected_slugs = [article.slug for article in articles]
    actual_slugs = [item["slug"] for item in listing.get("items", [])]
    if listing.get("total") != len(articles) or actual_slugs != expected_slugs:
        raise RuntimeError("Публичный список не совпал с кодовым каталогом")

    sitemap = client.get("/sitemap.xml")
    sitemap.raise_for_status()
    sitemap_text = sitemap.text
    missing_sitemap = [
        slug
        for slug in expected_slugs
        if f"https://vedicway.ru/guide/{slug}</loc>" not in sitemap_text
    ]
    if missing_sitemap:
        raise RuntimeError(f"Sitemap не содержит статьи: {missing_sitemap!r}")

    hub = client.get("/internal/seo/guide/page")
    hub.raise_for_status()
    if "Четыре раздела, единая библиотека" not in hub.text:
        raise RuntimeError("SSR-хаб не содержит новую структуру гида")
    if f'"numberOfItems":{len(articles)}' not in hub.text:
        raise RuntimeError("CollectionPage сообщает неверное число материалов")
    if sum(f'href="/guide/{slug}"' in hub.text for slug in expected_slugs) != len(
        articles
    ):
        raise RuntimeError("SSR-хаб не содержит ссылки на все статьи")

    categories = Counter()
    difficulties = Counter()
    cover_bytes = 0
    for index, article in enumerate(articles, start=1):
        response = client.get(f"/api/v1/content/guide/articles/{article.slug}")
        response.raise_for_status()
        value = response.json()
        if (
            value["title"] != article.manifest["title"]
            or value["category"] != article.manifest["category"]
            or value["difficulty"] != article.manifest["difficulty"]
            or value["canonical_url"] != f"https://vedicway.ru/guide/{article.slug}"
        ):
            raise RuntimeError(f"{article.slug}: публичные метаданные расходятся")
        if len(value.get("content_sections") or []) != 2:
            raise RuntimeError(
                f"{article.slug}: сервер не разделил статью для среднего CTA"
            )
        related = value.get("related") or []
        related_slugs = {item["slug"] for item in related}
        if (
            len(related) != 3
            or len(related_slugs) != 3
            or article.slug in related_slugs
        ):
            raise RuntimeError(
                f"{article.slug}: блок «Читать далее» содержит неверные статьи"
            )
        if any(not isinstance(item.get("coverImage"), dict) for item in related):
            raise RuntimeError(
                f"{article.slug}: статья в блоке «Читать далее» осталась без responsive-обложки"
            )
        cover = value.get("coverImage")
        if not isinstance(cover, dict) or not cover.get("sources"):
            raise RuntimeError(f"{article.slug}: responsive-обложка отсутствует")
        primary_cover = str(cover["url"])
        cover_response = client.get(primary_cover)
        cover_response.raise_for_status()
        if not cover_response.headers.get("content-type", "").startswith("image/webp"):
            raise RuntimeError(f"{article.slug}: медиашлюз вернул не WebP")
        cover_bytes += len(cover_response.content)

        page = client.get(f"/internal/seo/guide/articles/{article.slug}/page")
        page.raise_for_status()
        expected_canonical = (
            f'<link rel="canonical" href="https://vedicway.ru/guide/{article.slug}"'
        )
        if expected_canonical not in page.text:
            raise RuntimeError(f"{article.slug}: canonical отсутствует в первом HTML")
        if len(re.findall(r"<h1(?:\s|>)", page.text, flags=re.I)) != 1:
            raise RuntimeError(f"{article.slug}: SSR-страница должна содержать один H1")
        if page.text.count('data-content-cta="calculate-chart"') != 2:
            raise RuntimeError(f"{article.slug}: SSR-страница должна содержать два CTA")
        if 'data-reading-progress="true"' not in page.text:
            raise RuntimeError(f"{article.slug}: отсутствует прогресс чтения")
        if (
            'loading="eager"' not in page.text
            or 'fetchpriority="high"' not in page.text
        ):
            raise RuntimeError(
                f"{article.slug}: обложка не получила приоритет загрузки"
            )
        if page.text.count("article-related__media is-ready") != 3:
            raise RuntimeError(
                f"{article.slug}: SSR-блок «Читать далее» должен содержать три обложки"
            )
        schema = _article_schema(page.text)
        if (
            schema.get("headline") != article.manifest["title"]
            or schema.get("articleSection") != article.manifest["category"]
            or schema.get("educationalLevel")
            != (
                "Beginner"
                if article.manifest["difficulty"] == "beginner"
                else "Advanced"
            )
            or schema.get("description") != article.manifest["seo"]["meta_description"]
        ):
            raise RuntimeError(f"{article.slug}: Article schema расходится с manifest")
        image = schema.get("image")
        if not isinstance(image, dict) or int(image.get("width") or 0) < 1200:
            raise RuntimeError(
                f"{article.slug}: Article schema не содержит крупную обложку"
            )
        categories[value["category"]] += 1
        difficulties[value["difficulty"]] += 1
        if index % 20 == 0 or index == len(articles):
            print(f"verified {index}/{len(articles)}", flush=True)

    return {
        "articles": len(articles),
        "categories": dict(categories),
        "difficulties": dict(difficulties),
        "sitemap_urls": len(articles),
        "responsive_covers": len(articles),
        "cover_bytes_checked": cover_bytes,
        "article_schema": len(articles),
        "related_blocks": len(articles),
        "cta_pairs": len(articles),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and publish all code-owned astrology-guide articles"
    )
    parser.add_argument(
        "--content-root",
        type=Path,
        default=REPOSITORY_ROOT / "content" / "astrology-guide" / "articles",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get(
            "VEDICWAY_SEO_AGENT_BASE_URL",
            "http://127.0.0.1:8000",
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--publish", action="store_true")
    mode.add_argument("--verify-only", action="store_true")
    parser.add_argument(
        "--cohort",
        choices=("first-indexable",),
        help="Публиковать проверенную замкнутую когорту вместо всего корпуса",
    )
    parser.add_argument(
        "--slug",
        action="append",
        default=[],
        help="Выбрать конкретную статью; параметр можно повторять",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=REPOSITORY_ROOT
        / ".data"
        / "reports"
        / "astrology-guide-publication.json",
    )
    args = parser.parse_args()

    if args.cohort and args.slug:
        parser.error("--cohort нельзя сочетать с --slug")
    requested_slugs: set[str] | None = None
    if args.cohort == "first-indexable":
        requested_slugs = set(FIRST_INDEXABLE_COHORT)
    elif args.slug:
        requested_slugs = set(args.slug)

    corpus = load_corpus(args.content_root.resolve())
    articles = select_articles(corpus, requested_slugs)
    report: dict[str, Any] = {
        "status": "valid",
        "mode": "dry-run",
        "cohort": args.cohort or ("custom" if args.slug else "all"),
        "corpus_count": len(corpus),
        "article_count": len(articles),
        "categories": dict(Counter(a.manifest["category"] for a in articles)),
        "difficulties": dict(Counter(a.manifest["difficulty"] for a in articles)),
        "seo": {
            "unique_titles": len(articles),
            "unique_meta_descriptions": len(articles),
            "unique_focus_keyphrases": len(articles),
            "canonical_urls": len(articles),
        },
        "covers": len(articles),
        "internal_links": "valid",
    }
    if not args.publish and not args.verify_only:
        _json_write(args.report, report)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0

    token = os.environ.get("VEDICWAY_SEO_AGENT_TOKEN", "")
    if args.publish and len(token.encode("utf-8")) < 32:
        raise SystemExit("VEDICWAY_SEO_AGENT_TOKEN должен содержать минимум 32 байта")

    publisher: Publisher | None = None
    if args.publish:
        publisher = Publisher(args.base_url, token)
        try:
            publisher.health()
            media_replays = 0
            article_replays = 0
            revisions: dict[str, int] = {}
            for index, article in enumerate(articles, start=1):
                media_id, media_replay = publisher.upload_cover(article)
                revision, article_replay = publisher.publish_article(article, media_id)
                media_replays += int(media_replay)
                article_replays += int(article_replay)
                revisions[article.slug] = revision
                if index % 10 == 0 or index == len(articles):
                    print(f"published {index}/{len(articles)}", flush=True)
            report.update(
                {
                    "status": "published",
                    "mode": "publish",
                    "media_idempotent_replays": media_replays,
                    "article_idempotent_replays": article_replays,
                    "revisions": revisions,
                }
            )
        finally:
            publisher.close()

    with httpx.Client(
        base_url=args.base_url.rstrip("/"),
        timeout=httpx.Timeout(120, connect=15),
        follow_redirects=False,
    ) as public_client:
        report["verification"] = verify_publication(public_client, articles)
    report["status"] = "verified"
    if args.verify_only:
        report["mode"] = "verify-only"
    _json_write(args.report, report)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
