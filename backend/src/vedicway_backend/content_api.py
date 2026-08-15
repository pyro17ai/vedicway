from __future__ import annotations

import asyncio
import hashlib
import hmac
import io
import json
import os
import re
import shutil
import uuid
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

import nh3
from fastapi import APIRouter, File, Form, Header, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .content_store import ArticleRevisionConflict, ContentDatabase, fingerprint_hash
from .errors import DomainError
from .guide_catalog import (
    GUIDE_ARTICLE_SLOTS,
    GUIDE_CATEGORIES,
    GUIDE_CATEGORY_COUNTS,
    GUIDE_ORDER,
    GUIDE_SLOT_BY_SLUG,
    GUIDE_SLUGS,
)
from .legal_config import public_legal_config
from .payment_security import effective_client_ip

ContentSection = Literal["guide", "blog"]
Difficulty = Literal["beginner", "expert"]

MAX_MEDIA_BYTES = 12 * 1024 * 1024
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "AVIF"}
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MEDIA_ID_PATTERN = re.compile(r"^[a-f0-9-]{36}$")
MEDIA_MARKER_PATTERN = re.compile(r'<figure data-media-id="([a-f0-9-]{36})">\s*</figure>')
PROTECTED_SCHEMA_KEYS = {
    "@context",
    "@id",
    "@type",
    "articleSection",
    "author",
    "commentCount",
    "dateModified",
    "datePublished",
    "description",
    "educationalLevel",
    "headline",
    "image",
    "inLanguage",
    "interactionStatistic",
    "isAccessibleForFree",
    "keywords",
    "mainEntityOfPage",
    "publisher",
    "url",
    "wordCount",
}
ALLOWED_SCHEMA_EXTRA_KEYS = {
    "about",
    "citation",
    "learningResourceType",
    "mentions",
}
DIFFICULTY_LABELS = {"beginner": "Новичок", "expert": "Эксперт"}
DIFFICULTY_SCHEMA = {"beginner": "Beginner", "expert": "Advanced"}

ALLOWED_HTML_TAGS = {
    "a",
    "aside",
    "blockquote",
    "br",
    "code",
    "dd",
    "details",
    "div",
    "dl",
    "dt",
    "em",
    "figcaption",
    "figure",
    "h2",
    "h3",
    "h4",
    "hr",
    "img",
    "li",
    "mark",
    "ol",
    "p",
    "pre",
    "small",
    "strong",
    "summary",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
}
REMOVED_WITH_CONTENT_TAGS = {
    "button",
    "embed",
    "form",
    "iframe",
    "input",
    "math",
    "object",
    "option",
    "script",
    "select",
    "style",
    "svg",
    "textarea",
}
ALLOWED_HTML_ATTRIBUTES = {
    "a": {"href", "title"},
    "aside": {"data-kind"},
    "figure": {"data-media-id"},
    "img": {
        "alt",
        "decoding",
        "height",
        "loading",
        "src",
        "title",
        "width",
    },
    "ol": {"start"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan", "scope"},
}


class ContentArticlePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section: ContentSection
    difficulty: Difficulty
    title: str = Field(min_length=1, max_length=240)
    slug: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=120)
    excerpt: str = Field(min_length=40, max_length=500)
    content_html: str = Field(min_length=120, max_length=300_000)
    cover_media_id: str | None = Field(default=None, max_length=36)
    cover_image_url: str | None = Field(default=None, max_length=500)
    cover_image_alt: str = Field(min_length=1, max_length=300)
    seo_title: str = Field(default="", max_length=180)
    meta_description: str = Field(min_length=70, max_length=320)
    focus_keyphrase: str = Field(default="", max_length=180)
    tags: list[str] = Field(default_factory=list, max_length=20)
    schema_extra: dict[str, Any] = Field(default_factory=dict)
    author_name: str = Field(default="Редакция VedicWay", min_length=1, max_length=160)

    @field_validator("slug")
    @classmethod
    def valid_slug(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not SLUG_PATTERN.fullmatch(normalized):
            raise ValueError("Адрес должен состоять из латинских букв, цифр и дефисов")
        return normalized

    @field_validator(
        "title",
        "category",
        "excerpt",
        "content_html",
        "cover_image_alt",
        "seo_title",
        "meta_description",
        "focus_keyphrase",
        "author_name",
        mode="before",
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("cover_media_id")
    @classmethod
    def valid_cover_media_id(cls, value: str | None) -> str | None:
        if value is not None and not MEDIA_ID_PATTERN.fullmatch(value):
            raise ValueError("Некорректный идентификатор обложки")
        return value

    @field_validator("tags")
    @classmethod
    def valid_tags(cls, values: list[str]) -> list[str]:
        normalized = [re.sub(r"\s+", " ", value).strip() for value in values]
        normalized = [value for value in normalized if value]
        if any(len(value) > 80 for value in normalized):
            raise ValueError("Тег не должен быть длиннее 80 символов")
        return list(dict.fromkeys(normalized))

    @field_validator("schema_extra")
    @classmethod
    def valid_schema_extra(cls, value: dict[str, Any]) -> dict[str, Any]:
        conflicts = sorted(PROTECTED_SCHEMA_KEYS.intersection(value))
        if conflicts:
            raise ValueError("Системные поля Schema.org формирует сервер: " + ", ".join(conflicts))
        unsupported = sorted(set(value).difference(ALLOWED_SCHEMA_EXTRA_KEYS))
        if unsupported:
            raise ValueError(
                "Допустимые дополнения Schema.org: " + ", ".join(sorted(ALLOWED_SCHEMA_EXTRA_KEYS))
            )
        encoded = json.dumps(value, ensure_ascii=False)
        if len(encoded) > 20_000:
            raise ValueError("Дополнение Schema.org превышает 20 КБ")
        return value

    @model_validator(mode="after")
    def valid_cover(self) -> ContentArticlePayload:
        if not self.cover_media_id and not self.cover_image_url:
            raise ValueError("Нужна обложка из медиашлюза или локальный URL")
        if self.cover_image_url:
            value = self.cover_image_url.strip()
            parsed = urlsplit(value)
            origin = urlsplit(_public_origin())
            is_local = value.startswith(("/assets/", "/media/articles/"))
            is_same_origin = (
                parsed.scheme == origin.scheme
                and parsed.netloc == origin.netloc
                and parsed.path.startswith(("/assets/", "/media/articles/"))
            )
            if not (is_local or is_same_origin):
                raise ValueError("Обложка должна находиться на VedicWay")
            self.cover_image_url = value
        return self


class CommentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=2, max_length=80)
    body: str = Field(min_length=8, max_length=3000)
    website: str = Field(default="", max_length=500)

    @field_validator("display_name", "body", "website", mode="before")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value).strip()


def _public_origin() -> str:
    return (os.environ.get("VEDICWAY_PUBLIC_ORIGIN") or "https://vedicway.ru").rstrip("/")


def _database(request: Request) -> ContentDatabase:
    return request.app.state.content_db


def _production() -> bool:
    return os.environ.get("VEDICWAY_ENV", "development").casefold() == "production"


def _client_ip(request: Request) -> str:
    direct = request.client.host if request.client else "unknown"
    settings = request.app.state.payment_settings
    return effective_client_ip(
        direct,
        request.headers.get("X-Forwarded-For"),
        settings.trusted_proxy_networks,
    )


def _assert_same_origin(request: Request) -> None:
    origin = request.headers.get("origin", "").rstrip("/")
    if not origin:
        return
    allowed = {_public_origin()}
    if not _production():
        allowed.update(
            {
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "http://testserver",
            }
        )
    if origin not in allowed:
        raise DomainError(
            "ORIGIN_FORBIDDEN",
            "Источник запроса не разрешён",
            recoverable=False,
            status_code=403,
        )


def _html_attribute_filter(tag: str, attribute: str, value: str) -> str | None:
    if attribute == "data-media-id":
        return value if MEDIA_ID_PATTERN.fullmatch(value) else None
    if attribute in {"width", "height", "start", "colspan", "rowspan"}:
        return value if re.fullmatch(r"[1-9][0-9]{0,3}", value) else None
    if attribute == "scope":
        return value if value in {"col", "row", "colgroup", "rowgroup"} else None
    if tag == "img" and attribute == "src":
        candidate = value.strip()
        parsed = urlsplit(candidate)
        public = urlsplit(_public_origin())
        local_path = candidate.startswith(("/assets/", "/media/articles/"))
        same_origin = (
            parsed.scheme == public.scheme
            and parsed.netloc == public.netloc
            and parsed.path.startswith(("/assets/", "/media/articles/"))
        )
        return candidate if local_path or same_origin else None
    return value


def _keep_relative_url(value: str) -> str | None:
    return value if value.startswith(("/", "#")) and not value.startswith("//") else None


def sanitize_article_html(value: str) -> str:
    return nh3.clean(
        value,
        tags=ALLOWED_HTML_TAGS,
        clean_content_tags=REMOVED_WITH_CONTENT_TAGS,
        attributes=ALLOWED_HTML_ATTRIBUTES,
        attribute_filter=_html_attribute_filter,
        strip_comments=True,
        link_rel="noopener noreferrer",
        tag_attribute_values={
            "aside": {"data-kind": {"note", "warning", "example", "summary"}},
        },
        set_tag_attribute_values={
            "img": {"loading": "lazy", "decoding": "async"},
        },
        url_schemes={"http", "https", "mailto"},
        url_relative=_keep_relative_url,
    ).strip()


def _plain_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def _cdata(value: str) -> str:
    return value.replace("]]>", "]]]]><![CDATA[>")


class _TopLevelBlockParser(HTMLParser):
    VOID_TAGS = {"br", "hr", "img"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.current: list[str] = []
        self.blocks: list[str] = []

    def _flush(self) -> None:
        value = "".join(self.current).strip()
        if value:
            self.blocks.append(value)
        self.current = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.current.append(self.get_starttag_text())
        if tag not in self.VOID_TAGS:
            self.depth += 1
        elif self.depth == 0:
            self._flush()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.current.append(self.get_starttag_text())
        if self.depth == 0:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        self.current.append(f"</{tag}>")
        self.depth = max(0, self.depth - 1)
        if self.depth == 0:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self.depth == 0 and data.strip() and not self.current:
            self.current.append("<p>")
            self.current.append(escape(data, quote=False))
            self.current.append("</p>")
            self._flush()
            return
        self.current.append(escape(data, quote=False))

    def close(self) -> None:
        super().close()
        self._flush()


def _split_content(value: str) -> tuple[str, str]:
    parser = _TopLevelBlockParser()
    parser.feed(value)
    parser.close()
    if not parser.blocks:
        return value, ""
    midpoint = max(1, (len(parser.blocks) + 1) // 2)
    return "".join(parser.blocks[:midpoint]), "".join(parser.blocks[midpoint:])


def _absolute_public_url(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith("/"):
        return f"{_public_origin()}{value}"
    parsed = urlsplit(value)
    return value if parsed.scheme in {"http", "https"} and parsed.netloc else None


def _media_dict(asset: Any) -> dict[str, Any]:
    return {
        "id": asset.id,
        "provider": "remote",
        "storageKey": asset.storage_key,
        "url": asset.public_url,
        "sources": asset.sources,
        "width": asset.width,
        "height": asset.height,
        "mimeType": asset.mime_type,
        "sizeBytes": asset.size_bytes,
        "alt": asset.alt_text,
        "title": asset.title,
        "caption": asset.caption,
        "createdAt": asset.created_at.isoformat(),
    }


def _responsive_media_html(
    asset: Any,
    *,
    eager: bool = False,
    class_name: str = "article-media-figure",
) -> str:
    sources = [
        source
        for source in (asset.sources or [])
        if isinstance(source, dict) and source.get("url") and source.get("width")
    ]
    srcset = ", ".join(
        f"{escape(str(source['url']), quote=True)} {int(source['width'])}w" for source in sources
    )
    loading = "eager" if eager else "lazy"
    priority = ' fetchpriority="high"' if eager else ""
    caption = f"<figcaption>{escape(asset.caption)}</figcaption>" if asset.caption else ""
    return (
        f'<figure class="{class_name}">'
        f'<img src="{escape(asset.public_url, quote=True)}" '
        f'{f"""srcset="{srcset}" """ if srcset else ""}'
        'sizes="(max-width: 760px) calc(100vw - 32px), 720px" '
        f'width="{asset.width}" height="{asset.height}" '
        f'alt="{escape(asset.alt_text, quote=True)}" loading="{loading}" '
        f'decoding="async"{priority} />{caption}</figure>'
    )


def _summary_cover_html(item: dict[str, Any]) -> str:
    asset = item.get("coverImage")
    if isinstance(asset, dict):
        source_url = asset.get("url")
        sources = [
            source
            for source in (asset.get("sources") or [])
            if isinstance(source, dict) and source.get("url") and source.get("width")
        ]
        width = int(asset.get("width") or 0)
        height = int(asset.get("height") or 0)
        alt = str(asset.get("alt") or item.get("cover_image_alt") or "")
    else:
        source_url = item.get("cover_image_url")
        sources = []
        width = 0
        height = 0
        alt = str(item.get("cover_image_alt") or "")

    if not source_url:
        return (
            '<span class="article-related__media article-related__media--empty" '
            'aria-hidden="true">✦</span>'
        )

    srcset = ", ".join(
        f"{escape(str(source['url']), quote=True)} {int(source['width'])}w" for source in sources
    )
    dimensions = f' width="{width}" height="{height}"' if width and height else ""
    return (
        '<span class="article-media article-related__media is-ready">'
        f'<img src="{escape(str(source_url), quote=True)}" '
        f'{f"""srcset="{srcset}" """ if srcset else ""}'
        'sizes="(max-width: 720px) calc(100vw - 32px), '
        '(max-width: 1100px) 50vw, 360px" '
        f'alt="{escape(alt, quote=True)}" loading="lazy" decoding="async"{dimensions} />'
        "</span>"
    )


def _render_body_media(value: str, database: ContentDatabase) -> str:
    def replace_marker(match: re.Match[str]) -> str:
        asset = database.get_media(match.group(1))
        return _responsive_media_html(asset) if asset else ""

    return MEDIA_MARKER_PATTERN.sub(replace_marker, value)


def _article_path(article: Any) -> str:
    return f"/{article.section}/{article.slug}"


def _canonical_url(article: Any) -> str:
    return article.canonical_url or f"{_public_origin()}{_article_path(article)}"


def _branded_seo_title(raw_title: str) -> str:
    if "VedicWay" in raw_title:
        return raw_title
    branded_title = f"{raw_title} | VedicWay"
    return branded_title if len(branded_title) <= 60 else raw_title


def _is_catalogued_article(article: Any) -> bool:
    return article.section != "guide" or article.slug in GUIDE_SLUGS


def _published_article(
    database: ContentDatabase,
    section: ContentSection,
    slug: str,
) -> Any | None:
    if section == "guide" and slug not in GUIDE_SLUGS:
        return None
    return database.get_article_by_path(section, slug, published_only=True)


def _article_summary(article: Any, database: ContentDatabase) -> dict[str, Any]:
    cover = database.get_media(article.cover_media_id) if article.cover_media_id else None
    return {
        "id": article.id,
        "section": article.section,
        "difficulty": article.difficulty,
        "difficulty_label": DIFFICULTY_LABELS[article.difficulty],
        "title": article.title,
        "slug": article.slug,
        "category": article.category,
        "excerpt": article.excerpt,
        "cover_image_url": article.cover_image_url,
        "cover_image_alt": article.cover_image_alt,
        "canonical_url": _canonical_url(article),
        "author_name": article.author_name,
        "tags": article.tags or [],
        "updated_at": article.updated_at.isoformat(),
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "coverImage": _media_dict(cover) if cover else None,
    }


def _related_articles(article: Any, database: ContentDatabase) -> list[dict[str, Any]]:
    candidates = [
        candidate
        for candidate in database.list_articles(
            include_drafts=False,
            section=article.section,
        )
        if candidate.id != article.id and _is_catalogued_article(candidate)
    ]

    def key(candidate: Any) -> tuple[int, int, str]:
        stable = hashlib.sha256(f"{article.slug}\0{candidate.slug}".encode()).hexdigest()
        return (
            0 if candidate.category == article.category else 1,
            0 if candidate.difficulty == article.difficulty else 1,
            stable,
        )

    return [_article_summary(candidate, database) for candidate in sorted(candidates, key=key)[:3]]


def _comment_dict(comment: Any) -> dict[str, Any]:
    return {
        "id": comment.id,
        "display_name": comment.display_name,
        "body": comment.body,
        "created_at": comment.created_at.isoformat(),
    }


def _article_dict(
    article: Any,
    database: ContentDatabase,
    *,
    include_related: bool = True,
) -> dict[str, Any]:
    body_ids = list(article.body_media_ids or [])
    body_assets = database.list_media(body_ids)
    rendered = _render_body_media(article.content, database)
    content_sections = list(_split_content(rendered))
    comments = database.list_comments(article.id)
    cover = database.get_media(article.cover_media_id) if article.cover_media_id else None
    word_count = len(_plain_text(rendered).split())
    value = {
        **_article_summary(article, database),
        "content_html": rendered,
        "content_sections": content_sections,
        "content_format": article.content_format,
        "body_media_ids": body_ids,
        "seo_title": article.seo_title,
        "meta_description": article.meta_description,
        "focus_keyphrase": article.focus_keyphrase,
        "schema_extra": article.schema_extra or {},
        "status": article.status,
        "revision": article.revision,
        "created_at": article.created_at.isoformat(),
        "word_count": word_count,
        "reading_minutes": max(1, (word_count + 179) // 180),
        "comment_count": len(comments),
        "cover_media_id": article.cover_media_id,
        "coverImage": _media_dict(cover) if cover else None,
        "bodyMedia": [_media_dict(asset) for asset in body_assets],
    }
    value["related"] = _related_articles(article, database) if include_related else []
    return value


def _article_schema(article: Any, database: ContentDatabase) -> dict[str, Any]:
    canonical = _canonical_url(article)
    cover = database.get_media(article.cover_media_id) if article.cover_media_id else None
    cover_url = _absolute_public_url(cover.public_url if cover else article.cover_image_url)
    comments = database.list_comments(article.id)
    article_type = "BlogPosting" if article.section == "blog" else "Article"
    hub_name = "Блог" if article.section == "blog" else "Гид по астрологии"
    hub_url = f"{_public_origin()}/{article.section}"
    rendered = _render_body_media(article.content, database)
    word_count = len(_plain_text(rendered).split())
    published = article.published_at or article.updated_at
    keywords = article.tags or ([article.focus_keyphrase] if article.focus_keyphrase else [])
    article_schema: dict[str, Any] = {
        "@type": article_type,
        "@id": f"{canonical}#article",
        "headline": article.title,
        "description": article.meta_description or article.excerpt,
        "url": canonical,
        "mainEntityOfPage": {"@type": "WebPage", "@id": canonical},
        "inLanguage": "ru-RU",
        "datePublished": published.isoformat(),
        "dateModified": article.updated_at.isoformat(),
        "educationalLevel": DIFFICULTY_SCHEMA[article.difficulty],
        "articleSection": article.category,
        "keywords": keywords,
        "wordCount": word_count,
        "isAccessibleForFree": True,
        "author": {
            "@type": "Organization",
            "@id": f"{_public_origin()}/about#organization",
            "name": article.author_name,
            "url": f"{_public_origin()}/about",
        },
        "publisher": {
            "@type": "Organization",
            "@id": f"{_public_origin()}/about#organization",
            "name": "VedicWay",
            "url": _public_origin(),
            "logo": {
                "@type": "ImageObject",
                "url": f"{_public_origin()}/assets/brand-mark.png",
            },
        },
        "commentCount": len(comments),
        "interactionStatistic": {
            "@type": "InteractionCounter",
            "interactionType": {"@type": "CommentAction"},
            "userInteractionCount": len(comments),
        },
        **(article.schema_extra or {}),
    }
    if cover_url:
        image: dict[str, Any] = {"@type": "ImageObject", "url": cover_url}
        if cover:
            image.update({"width": cover.width, "height": cover.height})
        article_schema["image"] = image
    return {
        "@context": "https://schema.org",
        "@graph": [
            article_schema,
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": 1,
                        "name": "Главная",
                        "item": f"{_public_origin()}/",
                    },
                    {
                        "@type": "ListItem",
                        "position": 2,
                        "name": hub_name,
                        "item": hub_url,
                    },
                    {
                        "@type": "ListItem",
                        "position": 3,
                        "name": article.title,
                        "item": canonical,
                    },
                ],
            },
        ],
    }


def _cta_html(position: str) -> str:
    if position == "middle":
        kicker = "Проверьте на своей карте"
        title = "Посмотрите, как символы складываются в вашей карте"
        text = "Расчёт займёт несколько минут и даст опорную схему для чтения статьи."
    else:
        kicker = "Следующий шаг"
        title = "Перейдите от теории к собственной карте"
        text = "Введите данные рождения и получите расчёт, к которому можно возвращаться."
    return (
        f'<aside class="article-cta article-cta--{position}" '
        'data-content-cta="calculate-chart">'
        '<span class="article-cta__mark" aria-hidden="true">✦</span><div>'
        f"<span>{escape(kicker)}</span><h2>{escape(title)}</h2>"
        f"<p>{escape(text)}</p></div>"
        '<a href="/">Рассчитать карту</a></aside>'
    )


def _cover_html(article: Any, database: ContentDatabase) -> str:
    if article.cover_media_id:
        asset = database.get_media(article.cover_media_id)
        if asset:
            return _responsive_media_html(
                asset,
                eager=True,
                class_name="article-reading__cover",
            )
    cover = _absolute_public_url(article.cover_image_url)
    if not cover:
        return ""
    return (
        '<figure class="article-reading__cover">'
        f'<img src="{escape(cover, quote=True)}" '
        f'alt="{escape(article.cover_image_alt or article.title, quote=True)}" '
        'loading="eager" decoding="async" fetchpriority="high" /></figure>'
    )


def _site_header_html(active: ContentSection) -> str:
    guide_active = ' class="is-active" aria-current="page"' if active == "guide" else ""
    blog_active = ' class="is-active" aria-current="page"' if active == "blog" else ""
    return (
        '<header class="site-header site-header--solid">'
        '<div class="site-header__inner">'
        '<a class="site-header__brand" href="/" aria-label="VedicWay, главная">'
        '<img class="site-header__brand-mark" src="/assets/brand-mark-light.png" '
        'alt="" width="40" height="40"><span>VedicWay</span></a>'
        '<nav class="site-header__nav" aria-label="Основная навигация">'
        '<a href="/">Главная</a>'
        f'<a href="/guide"{guide_active}>Гид по астрологии</a>'
        f'<a href="/blog"{blog_active}>Блог</a>'
        '<a href="/methodology">Метод</a>'
        "</nav></div></header>"
    )


def _material_count_label(value: int) -> str:
    last_two = value % 100
    last = value % 10
    if 11 <= last_two <= 14:
        word = "материалов"
    elif last == 1:
        word = "материал"
    elif 2 <= last <= 4:
        word = "материала"
    else:
        word = "материалов"
    return f"{value} {word}"


def _hub_seo_html(section: ContentSection, database: ContentDatabase) -> str:
    if section == "guide":
        title = "Гид по ведической астрологии | VedicWay"
        heading = "Гид по астрологии"
        eyebrow = "Библиотека знаний VedicWay"
        description = (
            "Практический гид по ведической астрологии с материалами "
            "о натальной карте, планетах, домах, аспектах "
            "и последовательном чтении джйотиш."
        )
        lead = description
        library_title = "Читайте по порядку или находите нужный приём"
        image = f"{_public_origin()}/assets/results-space-v2.png"
    else:
        title = "Блог об астрологии | VedicWay"
        heading = "Блог VedicWay"
        eyebrow = "Редакционный журнал VedicWay"
        description = (
            "Блог о ведической астрологии с материалами о натальных картах, "
            "планетах, прогнозах и практических методах чтения джйотиш."
        )
        lead = description
        library_title = "Свежие материалы и подробные разборы"
        image = f"{_public_origin()}/assets/hero-space-light.png"
    canonical = f"{_public_origin()}/{section}"
    articles = [
        article
        for article in database.list_articles(
            include_drafts=False,
            section=section,
        )
        if _is_catalogued_article(article)
    ]
    robots = (
        "index, follow, max-image-preview:large"
        if articles
        else "noindex, follow"
    )
    if section == "guide":
        articles.sort(key=lambda article: GUIDE_ORDER.get(article.slug, 10_000))
    item_list = [
        {
            "@type": "ListItem",
            "position": index,
            "url": _canonical_url(article),
            "name": article.title,
        }
        for index, article in enumerate(articles, start=1)
    ]
    schema = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "CollectionPage",
                "@id": f"{canonical}#collection",
                "name": heading,
                "description": description,
                "url": canonical,
                "inLanguage": "ru-RU",
                "mainEntity": {
                    "@type": "ItemList",
                    "numberOfItems": len(articles),
                    "itemListElement": item_list,
                },
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": 1,
                        "name": "Главная",
                        "item": f"{_public_origin()}/",
                    },
                    {
                        "@type": "ListItem",
                        "position": 2,
                        "name": heading,
                        "item": canonical,
                    },
                ],
            },
        ],
    }
    schema_json = json.dumps(
        schema,
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("<", "\\u003c")
    bootstrap_json = json.dumps(
        {
            "kind": "hub",
            "section": section,
            "articles": [_article_summary(article, database) for article in articles],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("<", "\\u003c")
    article_items: list[str] = []
    for article in articles:
        cover_asset = database.get_media(article.cover_media_id) if article.cover_media_id else None
        cover_url = _absolute_public_url(
            cover_asset.public_url if cover_asset else article.cover_image_url
        )
        dimensions = (
            f'width="{cover_asset.width}" height="{cover_asset.height}" ' if cover_asset else ""
        )
        cover_html = (
            f'<img src="{escape(cover_url, quote=True)}" '
            f'alt="{escape(article.cover_image_alt, quote=True)}" '
            f"{dimensions}"
            'loading="lazy" decoding="async">'
            if cover_url
            else '<span aria-hidden="true">✦</span>'
        )
        published = article.published_at or article.updated_at
        article_items.append(
            '<article class="content-card" data-content-card>'
            f'<a class="content-card__media" href="{escape(_article_path(article), quote=True)}" '
            f'aria-label="Открыть: {escape(article.title, quote=True)}">{cover_html}</a>'
            '<div class="content-card__body"><div class="content-card__meta">'
            f'<span class="difficulty-badge difficulty-badge--{article.difficulty}">'
            f"{escape(DIFFICULTY_LABELS[article.difficulty])}</span>"
            f"<span>{escape(article.category)}</span></div>"
            f"<h3>{escape(article.title)}</h3><p>{escape(article.excerpt)}</p>"
            f'<footer><time datetime="{published.isoformat()}">'
            f"{published.date().isoformat()}</time>"
            f'<a href="{escape(_article_path(article), quote=True)}">Читать</a>'
            "</footer></div></article>"
        )
    if section == "guide":
        empty_title = "Каталог гида готов к публикации"
        empty_text = "В коде закреплены 202 адреса и четыре раздела."
    else:
        empty_title = "Первый материал уже можно публиковать"
        empty_text = "Контентный шлюз и шаблон статьи готовы."
    library_html = (
        f'<div class="content-grid">{"".join(article_items)}</div>'
        if article_items
        else (
            '<div class="content-state content-state--empty" role="status">'
            f'<span aria-hidden="true">✦</span><h3>{escape(empty_title)}</h3>'
            f"<p>{escape(empty_text)}</p></div>"
        )
    )
    if section == "guide":
        published_guide_count = len(articles)
        guide_sections: list[str] = []
        for index, category in enumerate(GUIDE_CATEGORIES, start=1):
            category_articles = [
                article for article in articles if article.category == category.name
            ]
            beginner_count = sum(article.difficulty == "beginner" for article in category_articles)
            expert_count = sum(article.difficulty == "expert" for article in category_articles)
            total = GUIDE_CATEGORY_COUNTS[category.name]
            section_body = (
                "<header>"
                f'<span class="guide-route__chapter-number">{index:02d}</span>'
                '<span class="guide-route__chapter-glyph" aria-hidden="true">✦</span>'
                f'<span class="guide-route__chapter-state">{len(category_articles)} / {total}</span>'
                "</header>"
                '<span class="guide-route__chapter-kind">Раздел гида</span>'
                f"<h3>{escape(category.name)}</h3>"
                f"<p>{escape(category.description)}</p>"
                "<footer>"
                f"<span>{beginner_count} для новичков</span>"
                f"<span>{expert_count} для экспертов</span>"
                "</footer>"
            )
            guide_sections.append(
                '<li class="is-published">'
                f'<div data-guide-category="{escape(category.name, quote=True)}">'
                f"{section_body}</div></li>"
            )
        guide_publication_label = (
            f"Опубликовано {published_guide_count} из {len(GUIDE_ARTICLE_SLOTS)}"
        )
        guide_hero_html = f"""
          <section class="guide-atlas-hero" aria-labelledby="content-hub-title">
            <header class="guide-atlas-hero__masthead">
              <span class="content-eyebrow">{escape(eyebrow)}</span>
              <span>Маршрут 01 / 04</span>
            </header>
            <div class="guide-atlas-hero__body">
              <div class="guide-atlas-hero__copy">
                <h1 id="content-hub-title"><span>Гид по</span> <em>астрологии</em></h1>
                <p>{escape(lead)}</p>
                <a href="#guide-route">Смотреть структуру</a>
              </div>
              <div class="guide-atlas-hero__diagram" aria-hidden="true">
                <span class="guide-atlas-hero__north">N</span>
                <span class="guide-atlas-hero__coordinate">55°45′ · 37°37′</span>
                <svg viewBox="0 0 360 360" focusable="false">
                  <path class="guide-atlas-hero__route-shadow" d="M44 304 C104 270 74 205 152 186 C222 169 202 96 312 52"></path>
                  <path class="guide-atlas-hero__route" d="M44 304 C104 270 74 205 152 186 C222 169 202 96 312 52"></path>
                  <circle cx="44" cy="304" r="7"></circle>
                  <circle cx="128" cy="195" r="7"></circle>
                  <circle cx="232" cy="139" r="7"></circle>
                  <circle cx="312" cy="52" r="7"></circle>
                </svg>
                <span class="guide-atlas-hero__step guide-atlas-hero__step--one">01</span>
                <span class="guide-atlas-hero__step guide-atlas-hero__step--two">02</span>
                <span class="guide-atlas-hero__step guide-atlas-hero__step--three">03</span>
                <span class="guide-atlas-hero__step guide-atlas-hero__step--four">04</span>
                <span class="guide-atlas-hero__seal">Путь чтения</span>
              </div>
            </div>
            <footer class="guide-atlas-hero__footer">
              <span>Четыре раздела от терминов до синтеза карты</span>
              <span>{guide_publication_label}</span>
            </footer>
          </section>
        """
        guide_route_html = f"""
          <section class="guide-route" id="guide-route" aria-labelledby="guide-route-title">
            <header class="guide-route__header">
              <div class="guide-route__intro">
                <span class="content-eyebrow">Структура гида</span>
                <h2 id="guide-route-title">Четыре раздела, единая библиотека</h2>
                <p>Выберите область гида, затем уточните глубину материала. Категория и уровень работают вместе с поиском по всем статьям.</p>
              </div>
              <div class="guide-route__metrics" aria-label="Четыре раздела гида и два уровня сложности">
                <span><strong>4</strong>раздела гида</span>
                <i aria-hidden="true">×</i>
                <span><strong>2</strong>уровня сложности</span>
              </div>
              <div class="guide-route__publication" role="progressbar"
                aria-label="Опубликованные статьи гида" aria-valuemin="0"
                aria-valuemax="{len(GUIDE_ARTICLE_SLOTS)}"
                aria-valuenow="{published_guide_count}"
                aria-valuetext="{guide_publication_label}">
                <span>{guide_publication_label}</span>
                <div aria-hidden="true"><i style="width:{published_guide_count / len(GUIDE_ARTICLE_SLOTS) * 100}%"></i></div>
              </div>
            </header>
            <ol class="guide-route__chapters">{"".join(guide_sections)}</ol>
            <section class="guide-route__levels" aria-labelledby="guide-levels-title">
              <header><span>Глубина материала</span>
                <h3 id="guide-levels-title">Уровень виден до открытия статьи</h3>
              </header>
              <dl>
                <div><dt><span>01</span>Новичок</dt>
                  <dd>Термины объясняются с нуля, а порядок чтения разобран по шагам.</dd>
                </div>
                <div><dt><span>02</span>Эксперт</dt>
                  <dd>Материал требует базовых понятий и разбирает связи внутри карты глубже.</dd>
                </div>
              </dl>
            </section>
          </section>
        """
    else:
        guide_hero_html = f"""
          <section class="content-hub__hero" aria-labelledby="content-hub-title">
            <div><span class="content-eyebrow">{escape(eyebrow)}</span>
            <h1 id="content-hub-title">{escape(heading)}</h1><p>{escape(lead)}</p></div>
            <div class="content-hub__constellation" aria-hidden="true">
              <span></span><span></span><span></span><i></i>
            </div>
          </section>
        """
        guide_route_html = ""
    return f"""<!doctype html>
<html lang="ru">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="robots" content="{robots}" />
    <meta name="description" content="{escape(description, quote=True)}" />
    <meta property="og:locale" content="ru_RU" />
    <meta property="og:type" content="website" />
    <meta property="og:site_name" content="VedicWay" />
    <meta property="og:title" content="{escape(title, quote=True)}" />
    <meta property="og:description" content="{escape(description, quote=True)}" />
    <meta property="og:url" content="{escape(canonical, quote=True)}" />
    <meta property="og:image" content="{escape(image, quote=True)}" />
    <meta property="og:image:alt" content="{escape(heading, quote=True)}" />
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="{escape(title, quote=True)}" />
    <meta name="twitter:description" content="{escape(description, quote=True)}" />
    <meta name="twitter:image" content="{escape(image, quote=True)}" />
    <link rel="canonical" href="{escape(canonical, quote=True)}" />
    <link rel="icon" type="image/png" href="/assets/brand-mark.png" />
    <link rel="stylesheet" href="/assets/seo-entry.css" />
    <script type="application/ld+json" data-vedicway-seo-schema="ssr">{schema_json}</script>
    <title>{escape(title)}</title>
  </head>
  <body>
    <div id="root">
      <div class="content-site">
        {_site_header_html(section)}
        <main class="content-hub" data-yandex-first-screen>
          <nav class="content-breadcrumbs" aria-label="Хлебные крошки">
            <a href="/">Главная</a><span aria-hidden="true">/</span>
            <span aria-current="page">{escape(heading)}</span>
          </nav>
          {guide_hero_html}
          {guide_route_html}
          <section class="content-library" aria-labelledby="content-library-title">
            <header class="content-library__header"><div>
              <span class="content-eyebrow">Библиотека</span>
              <h2 id="content-library-title">{escape(library_title)}</h2>
            </div><p>{escape(_material_count_label(len(articles)))}</p></header>
            {library_html}
          </section>
        </main>
      </div>
    </div>
    <script id="vedicway-seo-bootstrap" type="application/json">{bootstrap_json}</script>
    <script type="module" crossorigin src="/assets/seo-entry.js"></script>
  </body>
</html>"""


def _article_seo_html(article: Any, database: ContentDatabase) -> str:
    canonical = _canonical_url(article)
    raw_title = article.seo_title or article.title
    title = _branded_seo_title(raw_title)
    description = article.meta_description or article.excerpt
    schema_json = json.dumps(
        _article_schema(article, database),
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("<", "\\u003c")
    rendered = _render_body_media(article.content, database)
    first, second = _split_content(rendered)
    hub_name = "Блог" if article.section == "blog" else "Гид по астрологии"
    related = _related_articles(article, database)
    related_html = "".join(
        f'<a href="/{article.section}/{escape(item["slug"], quote=True)}" '
        "data-related-card>"
        f"{_summary_cover_html(item)}"
        f'<span class="article-related__index">{str(index).zfill(2)}</span><div>'
        f"<small>{escape(item['difficulty_label'])}</small>"
        f"<h3>{escape(item['title'])}</h3>"
        f"<p>{escape(item['excerpt'])}</p></div></a>"
        for index, item in enumerate(related, start=1)
    )
    comments = database.list_comments(article.id)
    bootstrap_json = json.dumps(
        {
            "kind": "article",
            "section": article.section,
            "slug": article.slug,
            "article": _article_dict(article, database),
            "comments": [_comment_dict(comment) for comment in comments],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("<", "\\u003c")
    citations = [
        value
        for value in (article.schema_extra or {}).get("citation", [])
        if isinstance(value, str) and value.startswith(("https://", "http://"))
    ]
    citations_html = "".join(
        "<li>"
        f'<a href="{escape(value, quote=True)}" target="_blank" rel="noopener noreferrer">'
        f"{escape(urlsplit(value).hostname or value)}</a></li>"
        for value in citations
    )
    comments_html = "".join(
        "<li>"
        f"<div><span>{escape(comment.display_name[:1])}</span><div>"
        f"<strong>{escape(comment.display_name)}</strong>"
        f'<time datetime="{comment.created_at.isoformat()}">'
        f"{comment.created_at.date().isoformat()}</time></div></div>"
        f"<p>{escape(comment.body)}</p></li>"
        for comment in comments
    )
    tags_html = "".join(f"<span>{escape(tag)}</span>" for tag in (article.tags or [])[:4])
    cover = _absolute_public_url(article.cover_image_url)
    published = article.published_at or article.updated_at
    reading_minutes = max(1, (len(_plain_text(rendered).split()) + 179) // 180)
    return f"""<!doctype html>
<html lang="ru">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="robots" content="index, follow, max-image-preview:large" />
    <meta name="description" content="{escape(description, quote=True)}" />
    <meta property="og:locale" content="ru_RU" />
    <meta property="og:type" content="article" />
    <meta property="og:site_name" content="VedicWay" />
    <meta property="og:title" content="{escape(title, quote=True)}" />
    <meta property="og:description" content="{escape(description, quote=True)}" />
    <meta property="og:url" content="{escape(canonical, quote=True)}" />
    {f'<meta property="og:image" content="{escape(cover, quote=True)}" />' if cover else ""}
    {f'<meta property="og:image:alt" content="{escape(article.cover_image_alt or article.title, quote=True)}" />' if cover else ""}
    <meta property="article:published_time" content="{published.isoformat()}" />
    <meta property="article:modified_time" content="{article.updated_at.isoformat()}" />
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="{escape(title, quote=True)}" />
    <meta name="twitter:description" content="{escape(description, quote=True)}" />
    {f'<meta name="twitter:image" content="{escape(cover, quote=True)}" />' if cover else ""}
    <link rel="canonical" href="{escape(canonical, quote=True)}" />
    <link rel="icon" type="image/png" href="/assets/brand-mark.png" />
    <link rel="stylesheet" href="/assets/seo-entry.css" />
    <script type="application/ld+json" data-vedicway-seo-schema="ssr">{schema_json}</script>
    <title>{escape(title)}</title>
  </head>
  <body>
    <div id="root">
      <div class="content-site">
        <div class="article-reading-progress" data-reading-progress="true" aria-hidden="true"><span></span></div>
        {_site_header_html(article.section)}
        <main class="article-page" data-yandex-first-screen>
          <nav class="content-breadcrumbs" aria-label="Хлебные крошки">
            <a href="/">Главная</a><span aria-hidden="true">/</span>
            <a href="/{article.section}">{hub_name}</a><span aria-hidden="true">/</span>
            <span aria-current="page">{escape(article.title)}</span>
          </nav>
          <article class="article-reading" itemscope itemtype="https://schema.org/{"BlogPosting" if article.section == "blog" else "Article"}">
            <header class="article-reading__header">
              <div class="article-reading__meta">
                <span class="difficulty-badge difficulty-badge--{article.difficulty}">{escape(DIFFICULTY_LABELS[article.difficulty])}</span>
                <span>{escape(article.category)}</span>
              </div>
              <h1 itemprop="headline">{escape(article.title)}</h1>
              <p>{escape(article.excerpt)}</p>
              <div class="article-reading__byline">
                <a href="/about">{escape(article.author_name)}</a>
                <time datetime="{published.isoformat()}">{published.date().isoformat()}</time>
                <span>{reading_minutes} мин</span>
              </div>
            </header>
            {_cover_html(article, database)}
            <div class="article-reading__layout">
              <aside class="article-reading__rail" aria-label="О материале">
                <span>В материале</span><p>{escape(article.category)}</p><div>{tags_html}</div>
              </aside>
              <div class="article-reading__content" itemprop="articleBody">
                <section class="article-rich">{first}</section>{_cta_html("middle")}
                <section class="article-rich">{second}</section>{_cta_html("end")}
              </div>
            </div>
          </article>
          <section class="article-sources" aria-labelledby="article-sources-title">
            <header><span>Проверяемость материала</span>
              <h2 id="article-sources-title">Источники и редакция</h2>
              <p>Редакция отделяет расчётные данные от трактовки и указывает внешние материалы, на которых основана статья.</p>
            </header>
            {f"<ol>{citations_html}</ol>" if citations_html else "<p>Внешние источники для этой редакции ещё не указаны.</p>"}
            <a class="article-sources__policy" href="/editorial-policy">Как редакция проверяет материалы</a>
          </section>
          <section class="article-related" aria-labelledby="related-title">
            <header><span>Продолжить чтение</span><h2 id="related-title">Читать далее</h2></header>
            {f'<div class="article-related__grid">{related_html}</div>' if related_html else '<p class="article-related__empty">Следующие материалы появятся после публикации.</p>'}
          </section>
          <section class="article-comments" aria-labelledby="comments-title">
            <header><span>Открытое обсуждение</span><h2 id="comments-title">Комментарии</h2>
              <p>Авторизация не нужна. Имя и текст появятся сразу после отправки.</p>
            </header>
            {f'<ol class="article-comments__list">{comments_html}</ol>' if comments_html else '<p class="article-comments__empty">Здесь пока тихо. Начните обсуждение первым.</p>'}
          </section>
        </main>
      </div>
    </div>
    <script id="vedicway-seo-bootstrap" type="application/json">{bootstrap_json}</script>
    <script type="module" crossorigin src="/assets/seo-entry.js"></script>
  </body>
</html>"""


def _assert_content_agent(authorization: str | None) -> None:
    expected = os.environ.get("VEDICWAY_SEO_AGENT_TOKEN", "")
    if not expected or (_production() and len(expected.encode("utf-8")) < 32):
        raise DomainError(
            "CONTENT_AGENT_NOT_CONFIGURED",
            "Контур публикации Codex не настроен",
            status_code=503,
        )
    supplied = authorization.removeprefix("Bearer ") if authorization else ""
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise DomainError(
            "CONTENT_AGENT_AUTH_REQUIRED",
            "Доступ агента публикации отклонён",
            recoverable=False,
            status_code=401,
        )


def _assert_idempotency_key(value: str | None) -> str:
    if not value or not re.fullmatch(r"[A-Za-z0-9._:-]{16,160}", value):
        raise DomainError(
            "IDEMPOTENCY_KEY_INVALID",
            "Нужен стабильный Idempotency-Key длиной от 16 до 160 символов",
            recoverable=False,
            status_code=400,
        )
    return value


def _content_payload_hash(payload: ContentArticlePayload) -> str:
    raw = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _media_payload_hash(
    content_sha256: str,
    purpose: str,
    alt: str,
    title: str,
    caption: str,
) -> str:
    raw = json.dumps(
        {
            "content_sha256": content_sha256.casefold(),
            "purpose": purpose,
            "alt": alt.strip(),
            "title": title.strip(),
            "caption": caption.strip(),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _if_match_revision(value: str | None) -> int:
    if not value:
        raise DomainError(
            "ARTICLE_REVISION_REQUIRED",
            "Перед обновлением прочитайте актуальную версию материала",
            status_code=428,
        )
    matched = re.fullmatch(r'(?:W/)?"?([1-9][0-9]*)"?', value.strip())
    if not matched:
        raise DomainError(
            "ARTICLE_REVISION_INVALID",
            "Некорректная версия материала",
            status_code=400,
        )
    return int(matched.group(1))


def _article_values(
    payload: ContentArticlePayload,
    database: ContentDatabase,
) -> dict[str, Any]:
    sanitized = sanitize_article_html(payload.content_html)
    minimum = max(
        600,
        min(
            30_000,
            int(os.environ.get("VEDICWAY_SEO_MIN_ARTICLE_CHARS", "4000")),
        ),
    )
    if len(_plain_text(sanitized)) < minimum:
        raise DomainError(
            "ARTICLE_TOO_SHORT",
            f"Текст статьи короче технического порога {minimum} символов",
            status_code=422,
        )
    body_ids = list(dict.fromkeys(MEDIA_MARKER_PATTERN.findall(sanitized)))
    referenced_ids = ([payload.cover_media_id] if payload.cover_media_id else []) + body_ids
    assets = {asset.id: asset for asset in database.list_media(referenced_ids)}
    if any(asset_id not in assets for asset_id in referenced_ids):
        raise DomainError(
            "ARTICLE_MEDIA_NOT_FOUND",
            "Одно из изображений статьи недоступно",
            status_code=422,
        )
    cover_url = payload.cover_image_url
    cover_alt = payload.cover_image_alt
    if payload.cover_media_id:
        cover = assets[payload.cover_media_id]
        if cover.purpose != "cover":
            raise DomainError(
                "ARTICLE_COVER_INVALID",
                "Обложка загружена в неверном режиме",
                status_code=422,
            )
        cover_url = cover.public_url
        cover_alt = cover_alt or cover.alt_text
    for asset_id in body_ids:
        if assets[asset_id].purpose != "body":
            raise DomainError(
                "ARTICLE_BODY_MEDIA_INVALID",
                "Иллюстрация текста загружена в неверном режиме",
                status_code=422,
            )
    return {
        "section": payload.section,
        "difficulty": payload.difficulty,
        "title": payload.title,
        "slug": payload.slug,
        "category": payload.category,
        "excerpt": payload.excerpt,
        "content": sanitized,
        "content_format": "html.v1",
        "tags": payload.tags,
        "schema_extra": payload.schema_extra,
        "cover_media_id": payload.cover_media_id,
        "body_media_ids": body_ids,
        "cover_image_url": cover_url,
        "cover_image_alt": cover_alt,
        "seo_title": payload.seo_title,
        "meta_description": payload.meta_description,
        "focus_keyphrase": payload.focus_keyphrase,
        "canonical_url": f"{_public_origin()}/{payload.section}/{payload.slug}",
        "author_name": payload.author_name,
        "status": "published",
    }


def _article_matches(article: Any, values: dict[str, Any]) -> bool:
    return all(getattr(article, field) == value for field, value in values.items())


def _media_directory() -> Path:
    root = Path(
        os.environ.get(
            "VEDICWAY_MEDIA_DIR",
            Path(os.environ.get("VEDICWAY_DATA_DIR", ".data")) / "media",
        )
    )
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _store_article_media(
    raw: bytes,
    *,
    purpose: str,
    alt: str,
    title: str,
    caption: str,
    database: ContentDatabase,
    asset_id: str,
) -> Any:
    if len(raw) > MAX_MEDIA_BYTES:
        raise DomainError(
            "MEDIA_TOO_LARGE",
            "Изображение должно быть не больше 12 МБ",
            status_code=413,
        )
    try:
        source = Image.open(io.BytesIO(raw))
        if source.width * source.height > 40_000_000:
            raise DomainError(
                "MEDIA_DIMENSIONS_INVALID",
                "Разрешение изображения превышает 40 миллионов пикселей",
                status_code=422,
            )
        source.load()
    except DomainError:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError) as exc:
        raise DomainError(
            "MEDIA_INVALID",
            "Загрузите JPEG, PNG, WebP или AVIF",
            status_code=422,
        ) from exc
    if source.format not in ALLOWED_IMAGE_FORMATS:
        raise DomainError(
            "MEDIA_INVALID",
            "Загрузите JPEG, PNG, WebP или AVIF",
            status_code=422,
        )
    image = ImageOps.exif_transpose(source).convert("RGB")
    image.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
    if purpose == "cover" and image.width < 700:
        raise DomainError(
            "MEDIA_COVER_TOO_NARROW",
            "Обложка должна быть шириной не меньше 700 пикселей",
            status_code=422,
        )
    asset_directory = _media_directory() / "articles" / asset_id
    asset_directory.mkdir(parents=True, exist_ok=False)
    image.save(asset_directory / "original.webp", "WEBP", quality=90, method=6)
    widths = sorted({min(image.width, width) for width in (640, 960, 1280, 1600)})
    sources: list[dict[str, Any]] = []
    for width in widths:
        height = max(1, round(image.height * width / image.width))
        variant = (
            image
            if width == image.width
            else image.resize((width, height), Image.Resampling.LANCZOS)
        )
        path = asset_directory / f"{width}.webp"
        variant.save(path, "WEBP", quality=88, method=6)
        sources.append(
            {
                "url": f"/media/articles/{asset_id}/{width}.webp",
                "width": width,
                "mimeType": "image/webp",
            }
        )
    primary = sources[-1]
    destination = asset_directory / f"{primary['width']}.webp"
    values = {
        "id": asset_id,
        "storage_key": f"articles/{asset_id}/original.webp",
        "public_url": primary["url"],
        "sources": sources,
        "purpose": purpose,
        "mime_type": "image/webp",
        "width": int(primary["width"]),
        "height": max(1, round(image.height * int(primary["width"]) / image.width)),
        "size_bytes": destination.stat().st_size,
        "alt_text": alt.strip(),
        "title": title.strip(),
        "caption": caption.strip(),
    }
    try:
        return database.add_media(values)
    except Exception:
        shutil.rmtree(asset_directory, ignore_errors=True)
        raise


def build_content_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/v1/legal/config")
    async def legal_config() -> dict[str, object]:
        return public_legal_config()

    @router.get("/api/v1/content/{section}/articles")
    async def public_articles(
        section: ContentSection,
        request: Request,
        q: Annotated[str, Query(max_length=160)] = "",
        difficulty: Annotated[Difficulty | None, Query()] = None,
        category: Annotated[str, Query(max_length=120)] = "",
    ) -> dict[str, Any]:
        database = _database(request)
        articles = [
            article
            for article in database.list_articles(
                include_drafts=False,
                section=section,
            )
            if _is_catalogued_article(article)
        ]
        query = q.strip().casefold()
        if difficulty:
            articles = [article for article in articles if article.difficulty == difficulty]
        normalized_category = category.strip().casefold()
        if normalized_category:
            articles = [
                article
                for article in articles
                if article.category.casefold() == normalized_category
            ]
        if query:
            articles = [
                article
                for article in articles
                if query
                in " ".join(
                    [
                        article.title,
                        article.excerpt,
                        article.category,
                        *(article.tags or []),
                    ]
                ).casefold()
            ]
        if section == "guide":
            articles.sort(key=lambda article: GUIDE_ORDER.get(article.slug, 10_000))
        return {
            "items": [_article_summary(article, database) for article in articles],
            "total": len(articles),
        }

    @router.get("/api/v1/content/{section}/articles/{slug}")
    async def public_article(
        section: ContentSection,
        slug: str,
        request: Request,
    ) -> dict[str, Any]:
        article = _published_article(_database(request), section, slug)
        if not article:
            raise DomainError(
                "ARTICLE_NOT_FOUND",
                "Материал не найден",
                recoverable=False,
                status_code=404,
            )
        return _article_dict(article, _database(request))

    @router.get("/api/v1/content/{section}/articles/{slug}/comments")
    async def public_comments(
        section: ContentSection,
        slug: str,
        request: Request,
    ) -> dict[str, Any]:
        database = _database(request)
        article = _published_article(database, section, slug)
        if not article:
            raise DomainError(
                "ARTICLE_NOT_FOUND",
                "Материал не найден",
                recoverable=False,
                status_code=404,
            )
        return {"items": [_comment_dict(comment) for comment in database.list_comments(article.id)]}

    @router.post(
        "/api/v1/content/{section}/articles/{slug}/comments",
        status_code=201,
    )
    async def add_public_comment(
        section: ContentSection,
        slug: str,
        payload: CommentPayload,
        request: Request,
    ) -> dict[str, Any]:
        _assert_same_origin(request)
        database = _database(request)
        article = _published_article(database, section, slug)
        if not article:
            raise DomainError(
                "ARTICLE_NOT_FOUND",
                "Материал не найден",
                recoverable=False,
                status_code=404,
            )
        if payload.website:
            return {
                "id": "accepted",
                "display_name": payload.display_name,
                "body": "",
                "created_at": datetime.now(UTC).isoformat(),
            }
        rate_key = fingerprint_hash(
            f"{article.id}\0{_client_ip(request)}",
            "article-comment-rate-limit",
        )
        retry_after = await asyncio.to_thread(
            request.app.state.store.record_rate_limit_hit,
            rate_key,
            5,
            10 * 60,
        )
        if retry_after:
            raise DomainError(
                "COMMENT_RATE_LIMITED",
                "Новые комментарии с этого устройства временно ограничены",
                status_code=429,
                detail={"retry_after_seconds": retry_after},
            )
        comment = database.add_comment(
            article_id=article.id,
            display_name=payload.display_name,
            body=payload.body,
            ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
        return _comment_dict(comment)

    @router.get("/internal/content-agent/health", include_in_schema=False)
    async def content_agent_health(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        _assert_content_agent(authorization)
        return {
            "status": "ready",
            "input_format": "html.v1",
            "sections": ["guide", "blog"],
            "guide_slots": len(GUIDE_ARTICLE_SLOTS),
            "guide_categories": len(GUIDE_CATEGORIES),
            "database_boundary": "content-api-only",
        }

    @router.post(
        "/internal/content-agent/media",
        status_code=201,
        include_in_schema=False,
    )
    async def content_agent_media(
        request: Request,
        file: Annotated[UploadFile, File()],
        purpose: Annotated[Literal["cover", "body"], Form()],
        alt: Annotated[str, Form(min_length=1, max_length=300)],
        title: Annotated[str, Form(max_length=240)] = "",
        caption: Annotated[str, Form(max_length=500)] = "",
        authorization: Annotated[str | None, Header()] = None,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        x_content_sha256: Annotated[str | None, Header(alias="X-Content-SHA256")] = None,
    ) -> dict[str, Any]:
        _assert_content_agent(authorization)
        key = _assert_idempotency_key(idempotency_key)
        raw = await file.read(MAX_MEDIA_BYTES + 1)
        digest = hashlib.sha256(raw).hexdigest()
        if not x_content_sha256 or not hmac.compare_digest(
            x_content_sha256.casefold(),
            digest,
        ):
            raise DomainError(
                "CONTENT_HASH_MISMATCH",
                "Контрольная сумма изображения не совпала",
                recoverable=False,
                status_code=400,
            )
        request_hash = _media_payload_hash(digest, purpose, alt, title, caption)
        if not hmac.compare_digest(key.rsplit(":", 1)[-1], request_hash[:32]):
            raise DomainError(
                "IDEMPOTENCY_KEY_CONTENT_MISMATCH",
                "Idempotency-Key не связан с изображением",
                recoverable=False,
                status_code=400,
            )
        asset_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"vedicway-content:{key}:{digest}"))
        database = _database(request)
        existing = database.get_media(asset_id)
        asset = existing or _store_article_media(
            raw,
            purpose=purpose,
            alt=alt,
            title=title,
            caption=caption,
            database=database,
            asset_id=asset_id,
        )
        return {
            "asset": _media_dict(asset),
            "idempotent_replay": existing is not None,
        }

    @router.put(
        "/internal/content-agent/{section}/articles/{slug}",
        include_in_schema=False,
    )
    async def content_agent_article(
        section: ContentSection,
        slug: str,
        payload: ContentArticlePayload,
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        x_content_sha256: Annotated[str | None, Header(alias="X-Content-SHA256")] = None,
        if_match: Annotated[str | None, Header(alias="If-Match")] = None,
    ) -> dict[str, Any]:
        _assert_content_agent(authorization)
        key = _assert_idempotency_key(idempotency_key)
        if section != payload.section or slug != payload.slug:
            raise DomainError(
                "ARTICLE_PATH_MISMATCH",
                "Раздел или slug в адресе и теле запроса различаются",
                status_code=400,
            )
        if section == "guide" and slug not in GUIDE_SLUGS:
            raise DomainError(
                "GUIDE_SLOT_NOT_ALLOWED",
                "Новый адрес гида сначала добавляется в кодовый каталог",
                recoverable=False,
                status_code=409,
            )
        if section == "guide":
            slot = GUIDE_SLOT_BY_SLUG[slug]
            if (
                payload.title != slot.label
                or payload.category != slot.category
                or payload.difficulty != slot.difficulty
            ):
                raise DomainError(
                    "GUIDE_CATALOG_METADATA_MISMATCH",
                    "Заголовок, раздел и сложность статьи должны совпадать с кодовым каталогом",
                    recoverable=False,
                    status_code=409,
                )
        digest = _content_payload_hash(payload)
        if not x_content_sha256 or not hmac.compare_digest(
            x_content_sha256.casefold(),
            digest,
        ):
            raise DomainError(
                "CONTENT_HASH_MISMATCH",
                "Контрольная сумма статьи не совпала",
                status_code=400,
            )
        if not hmac.compare_digest(key.rsplit(":", 1)[-1], digest[:32]):
            raise DomainError(
                "IDEMPOTENCY_KEY_CONTENT_MISMATCH",
                "Idempotency-Key не связан со статьёй",
                recoverable=False,
                status_code=400,
            )
        database = _database(request)
        values = _article_values(payload, database)
        existing = database.get_article_by_path(section, slug)
        if existing and _article_matches(existing, values):
            return {
                "article": _article_dict(existing, database),
                "idempotent_replay": True,
            }
        try:
            if existing:
                article = database.save_article(
                    values,
                    article_id=existing.id,
                    expected_revision=_if_match_revision(if_match),
                )
            else:
                if if_match:
                    raise DomainError(
                        "ARTICLE_REVISION_INVALID",
                        "If-Match нельзя передавать при создании статьи",
                        status_code=400,
                    )
                article = database.save_article(values)
        except ArticleRevisionConflict as exc:
            raise DomainError(
                "ARTICLE_REVISION_CONFLICT",
                "Статья изменилась после начала публикации",
                status_code=409,
            ) from exc
        return {
            "article": _article_dict(article, database),
            "idempotent_replay": False,
        }

    @router.api_route(
        "/internal/seo/{section}/page",
        methods=["GET", "HEAD"],
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    async def published_content_hub(
        section: ContentSection,
        request: Request,
    ) -> HTMLResponse:
        return HTMLResponse(
            _hub_seo_html(section, _database(request)),
            headers={"Cache-Control": "public, max-age=60, stale-while-revalidate=300"},
        )

    @router.api_route(
        "/internal/seo/{section}/articles/{slug}/page",
        methods=["GET", "HEAD"],
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    async def published_article_page(
        section: ContentSection,
        slug: str,
        request: Request,
    ) -> HTMLResponse:
        article = _published_article(_database(request), section, slug)
        if not article:
            raise DomainError(
                "ARTICLE_NOT_FOUND",
                "Материал не найден",
                recoverable=False,
                status_code=404,
            )
        return HTMLResponse(
            _article_seo_html(article, _database(request)),
            headers={"Cache-Control": "public, max-age=60, stale-while-revalidate=300"},
        )

    @router.get("/media/articles/{asset_id}/{filename}")
    async def public_media(
        asset_id: str,
        filename: str,
        request: Request,
    ) -> FileResponse:
        if not MEDIA_ID_PATTERN.fullmatch(asset_id) or not re.fullmatch(
            r"[1-9][0-9]{1,3}\.webp",
            filename,
        ):
            raise DomainError(
                "MEDIA_NOT_FOUND",
                "Изображение не найдено",
                recoverable=False,
                status_code=404,
            )
        if not _database(request).media_is_public(asset_id, filename):
            raise DomainError(
                "MEDIA_NOT_FOUND",
                "Изображение не найдено",
                recoverable=False,
                status_code=404,
            )
        directory = (_media_directory() / "articles" / asset_id).resolve()
        path = (directory / filename).resolve()
        if path.parent != directory or not path.is_file():
            raise DomainError(
                "MEDIA_NOT_FOUND",
                "Изображение не найдено",
                recoverable=False,
                status_code=404,
            )
        return FileResponse(
            path,
            media_type="image/webp",
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )

    async def sitemap_response(request: Request) -> Response:
        origin = _public_origin()
        articles = [
            article
            for article in _database(request).list_articles(include_drafts=False)
            if _is_catalogued_article(article)
        ]
        urls = [
            f"<url><loc>{escape(origin)}/</loc></url>",
        ]
        for section in ("guide", "blog"):
            if any(article.section == section for article in articles):
                urls.append(f"<url><loc>{escape(origin)}/{section}</loc></url>")
        urls.extend(
            [
                f"<url><loc>{escape(origin)}/about</loc></url>",
                f"<url><loc>{escape(origin)}/methodology</loc></url>",
                f"<url><loc>{escape(origin)}/editorial-policy</loc></url>",
            ]
        )
        for article in articles:
            urls.append(
                f"<url><loc>{escape(_canonical_url(article))}</loc>"
                f"<lastmod>{article.updated_at.date().isoformat()}</lastmod></url>"
            )
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + "".join(urls)
            + "</urlset>"
        )
        return Response(
            content=body,
            media_type="application/xml; charset=utf-8",
            headers={"Cache-Control": "public, max-age=300"},
        )

    router.add_api_route(
        "/api/v1/seo/sitemap.xml",
        sitemap_response,
        methods=["GET", "HEAD"],
        include_in_schema=False,
    )
    router.add_api_route(
        "/sitemap.xml",
        sitemap_response,
        methods=["GET", "HEAD"],
        include_in_schema=False,
    )

    async def dzen_feed(request: Request) -> Response:
        database = _database(request)
        origin = _public_origin()
        mode = os.environ.get("VEDICWAY_DZEN_PUBLICATION_MODE", "native-draft")
        if mode not in {"native-draft", "publish"}:
            mode = "native-draft"
        items: list[str] = []
        public_articles = [
            article
            for article in database.list_articles(
                include_drafts=False,
                include_content=True,
            )
            if _is_catalogued_article(article)
        ]
        sections = {article.section for article in public_articles}
        channel_path = f"/{next(iter(sections))}" if len(sections) == 1 else "/"
        for article in public_articles[:500]:
            if not article.published_at:
                continue
            published_at = article.published_at
            if published_at.tzinfo is None:
                published_at = published_at.replace(tzinfo=UTC)
            categories = "<category>format-article</category><category>index</category>"
            if mode == "native-draft":
                categories += "<category>native-draft</category>"
            rendered = _render_body_media(article.content, database)
            items.append(
                "<item>"
                f"<title>{escape(article.title)}</title>"
                f"<link>{escape(_canonical_url(article))}</link>"
                f'<guid isPermaLink="true">{escape(_canonical_url(article))}</guid>'
                f"<pubDate>{format_datetime(published_at)}</pubDate>"
                f"<description><![CDATA[{_cdata(article.excerpt)}]]></description>"
                f"<yandex:full-text><![CDATA[{_cdata(rendered)}]]></yandex:full-text>"
                f"{categories}</item>"
            )
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<rss version="2.0" xmlns:yandex="http://news.yandex.ru">'
            "<channel><title>VedicWay: статьи об астрологии</title>"
            f"<link>{escape(origin + channel_path)}</link>"
            "<description>Гид и редакционные материалы VedicWay</description>"
            "<language>ru</language>" + "".join(items) + "</channel></rss>"
        )
        return Response(
            content=body,
            media_type="application/rss+xml; charset=utf-8",
            headers={"Cache-Control": "public, max-age=300"},
        )

    router.add_api_route(
        "/api/v1/seo/dzen.xml",
        dzen_feed,
        methods=["GET", "HEAD"],
        include_in_schema=False,
    )
    router.add_api_route(
        "/feed/dzen.xml",
        dzen_feed,
        methods=["GET", "HEAD"],
        include_in_schema=False,
    )

    @router.get("/api/v1/seo/dzen/status", include_in_schema=False)
    async def dzen_status(request: Request) -> dict[str, Any]:
        articles = [
            article
            for article in _database(request).list_articles(include_drafts=False)
            if _is_catalogued_article(article)
        ]
        now = datetime.now(UTC)
        recent = sum(
            1
            for article in articles
            if article.published_at
            and (
                article.published_at
                if article.published_at.tzinfo
                else article.published_at.replace(tzinfo=UTC)
            )
            >= now - timedelta(days=30)
        )
        return {
            "article_count": len(articles),
            "published_last_30_days": recent,
            "rss_ready": len(articles) >= 10 and recent >= 3,
            "publication_mode": os.environ.get(
                "VEDICWAY_DZEN_PUBLICATION_MODE",
                "native-draft",
            ),
        }

    return router
