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
from html import escape
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, File, Form, Header, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from .content_store import (
    ArticleRevisionConflict,
    ContentDatabase,
    User,
    fingerprint_hash,
    token_hash,
)
from .errors import DomainError
from .legal_config import public_legal_config
from .payment_security import effective_client_ip

ADMIN_COOKIE_DEV = "vw_admin"
CSRF_COOKIE_DEV = "vw_admin_csrf"
MAX_MEDIA_BYTES = 12 * 1024 * 1024
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "AVIF"}
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class LoginPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(min_length=8, max_length=512)


class ArticlePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=240)
    slug: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=120)
    excerpt: str = Field(default="", max_length=500)
    content: str = Field(default="", max_length=300_000)
    cover_media_id: str | None = Field(default=None, max_length=36)
    body_media_ids: list[str] = Field(default_factory=list, max_length=100)
    cover_image_url: str | None = Field(default=None, max_length=500)
    cover_image_alt: str = Field(default="", max_length=300)
    seo_title: str = Field(default="", max_length=180)
    meta_description: str = Field(default="", max_length=320)
    focus_keyphrase: str = Field(default="", max_length=180)
    canonical_url: str = Field(default="", max_length=500)
    author_name: str = Field(default="Редакция VedicWay", max_length=160)
    status: Literal["draft", "published"] = "draft"

    @field_validator("slug")
    @classmethod
    def valid_slug(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not SLUG_PATTERN.fullmatch(normalized):
            raise ValueError("Адрес должен состоять из латинских букв, цифр и дефисов")
        return normalized

    @field_validator("excerpt", "content", "meta_description", "cover_image_alt")
    @classmethod
    def publish_requirements_are_checked_by_route(cls, value: str) -> str:
        return value.strip()

    @field_validator("cover_media_id")
    @classmethod
    def valid_cover_media_id(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[a-f0-9-]{36}", value):
            raise ValueError("Некорректный идентификатор обложки")
        return value

    @field_validator("body_media_ids")
    @classmethod
    def valid_body_media_ids(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)) or any(
            not re.fullmatch(r"[a-f0-9-]{36}", value) for value in values
        ):
            raise ValueError("Некорректный список изображений статьи")
        return values

    @model_validator(mode="after")
    def valid_canonical_url(self) -> ArticlePayload:
        if not self.canonical_url.strip():
            self.canonical_url = ""
            return self
        origin = (os.environ.get("VEDICWAY_PUBLIC_ORIGIN") or "https://vedicway.ru").rstrip("/")
        expected = urlsplit(origin)
        canonical = urlsplit(self.canonical_url.strip())
        if (
            canonical.scheme != expected.scheme
            or canonical.netloc != expected.netloc
            or canonical.path.rstrip("/") != f"/guide/{self.slug}"
            or canonical.query
            or canonical.fragment
        ):
            raise ValueError("Canonical должен совпадать с публичным адресом этой статьи")
        self.canonical_url = self.canonical_url.strip()
        return self


def _database(request: Request) -> ContentDatabase:
    return request.app.state.content_db


def _production() -> bool:
    return os.environ.get("VEDICWAY_ENV", "development").casefold() == "production"


def _cookie_names() -> tuple[str, str]:
    if _production():
        return "__Host-vedicway-admin", "__Host-vedicway-csrf"
    return ADMIN_COOKIE_DEV, CSRF_COOKIE_DEV


def _set_auth_cookies(response: Response, session_token: str, csrf_token: str) -> None:
    admin_cookie, csrf_cookie = _cookie_names()
    options = {"secure": _production(), "samesite": "strict", "path": "/", "max_age": 8 * 60 * 60}
    response.set_cookie(admin_cookie, session_token, httponly=True, **options)
    response.set_cookie(csrf_cookie, csrf_token, httponly=False, **options)


def _clear_auth_cookies(response: Response) -> None:
    admin_cookie, csrf_cookie = _cookie_names()
    response.delete_cookie(admin_cookie, path="/", secure=_production(), samesite="strict")
    response.delete_cookie(csrf_cookie, path="/", secure=_production(), samesite="strict")


def _client_ip(request: Request) -> str | None:
    if request.client is None:
        return None
    return request.client.host


def _effective_client_ip(request: Request) -> str:
    settings = request.app.state.payment_settings
    return effective_client_ip(
        _client_ip(request) or "unknown",
        request.headers.get("X-Forwarded-For"),
        settings.trusted_proxy_networks,
    )


async def _enforce_admin_login_rate_limit(request: Request) -> None:
    bucket_key = fingerprint_hash(_effective_client_ip(request), "admin-login-rate-limit")
    retry_after = await asyncio.to_thread(
        request.app.state.store.record_rate_limit_hit,
        bucket_key,
        8,
        15 * 60,
    )
    if retry_after:
        raise DomainError(
            "RATE_LIMITED",
            "Слишком много попыток входа. Повторите позже.",
            status_code=429,
            detail={"retry_after_seconds": retry_after},
        )


def _assert_same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if not origin:
        return
    configured = os.environ.get("VEDICWAY_PUBLIC_ORIGIN", "").rstrip("/")
    allowed = {str(request.base_url).rstrip("/"), configured}
    if not _production():
        allowed.update({"http://localhost:5173", "http://127.0.0.1:5173", "http://testserver"})
    if origin.rstrip("/") not in {value for value in allowed if value}:
        raise DomainError(
            "ORIGIN_FORBIDDEN", "Источник запроса не разрешён", recoverable=False, status_code=403
        )


def _current_admin(request: Request) -> tuple[Any, User]:
    admin_cookie, _ = _cookie_names()
    resolved = _database(request).resolve_admin_session(request.cookies.get(admin_cookie))
    if not resolved:
        raise DomainError(
            "ADMIN_AUTH_REQUIRED", "Войдите в редакцию", recoverable=False, status_code=401
        )
    session, user = resolved
    if user.role != "admin":
        raise DomainError(
            "ADMIN_FORBIDDEN", "Недостаточно прав", recoverable=False, status_code=403
        )
    return session, user


def _assert_csrf(request: Request, session: Any, header_token: str | None) -> None:
    _, csrf_cookie = _cookie_names()
    cookie_token = request.cookies.get(csrf_cookie)
    if not header_token or not cookie_token or not hmac.compare_digest(header_token, cookie_token):
        raise DomainError(
            "CSRF_INVALID", "Защитный токен устарел. Обновите страницу.", status_code=403
        )
    if not hmac.compare_digest(token_hash(header_token), session.csrf_token_hash):
        raise DomainError(
            "CSRF_INVALID", "Защитный токен устарел. Обновите страницу.", status_code=403
        )
    _assert_same_origin(request)


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


def _article_dict(article: Any, database: ContentDatabase) -> dict[str, Any]:
    cover = database.get_media(article.cover_media_id) if article.cover_media_id else None
    body_media_ids = list(
        dict.fromkeys(re.findall(r"\{\{media:([a-f0-9-]{36})\}\}", article.content))
    )
    body = database.list_media(body_media_ids)
    return {
        "id": article.id,
        "title": article.title,
        "slug": article.slug,
        "category": article.category,
        "excerpt": article.excerpt,
        "content": article.content,
        "cover_media_id": article.cover_media_id,
        "body_media_ids": body_media_ids,
        "cover_image_url": article.cover_image_url,
        "cover_image_alt": article.cover_image_alt,
        "seo_title": article.seo_title,
        "meta_description": article.meta_description,
        "focus_keyphrase": article.focus_keyphrase,
        "canonical_url": article.canonical_url,
        "author_name": article.author_name,
        "status": article.status,
        "revision": article.revision,
        "created_at": article.created_at.isoformat(),
        "updated_at": article.updated_at.isoformat(),
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "coverImage": _media_dict(cover) if cover else None,
        "bodyMedia": [_media_dict(asset) for asset in body],
    }


def _absolute_public_url(origin: str, value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith("/"):
        return f"{origin}{value}"
    parsed = urlsplit(value)
    return value if parsed.scheme in {"http", "https"} and parsed.netloc else None


def _inline_article_html(value: str, origin: str) -> str:
    rendered: list[str] = []
    cursor = 0
    for match in re.finditer(r"\[([^\]\n]{1,240})\]\(([^\s)]+)\)", value):
        rendered.append(escape(value[cursor : match.start()]))
        label, url = match.group(1), match.group(2)
        parsed = urlsplit(url)
        if url.startswith("/") or (parsed.scheme in {"http", "https"} and parsed.netloc):
            absolute = f"{origin}{url}" if url.startswith("/") else url
            relation = "" if absolute.startswith(f"{origin}/") else ' rel="nofollow noopener noreferrer"'
            rendered.append(f'<a href="{escape(absolute)}"{relation}>{escape(label)}</a>')
        else:
            rendered.append(escape(match.group(0)))
        cursor = match.end()
    rendered.append(escape(value[cursor:]))
    return "".join(rendered)


def _article_content_html(content: str, database: ContentDatabase, origin: str) -> str:
    rendered: list[str] = []
    for block in re.split(r"\n{2,}", content.strip()):
        block = block.strip()
        if not block:
            continue
        media_match = re.fullmatch(r"\{\{media:([a-f0-9-]{36})\}\}", block)
        if media_match:
            asset = database.get_media(media_match.group(1))
            if asset:
                url = _absolute_public_url(origin, asset.public_url)
                if url:
                    caption = f"<figcaption>{escape(asset.caption)}</figcaption>" if asset.caption else ""
                    rendered.append(
                        f'<figure><img src="{escape(url)}" alt="{escape(asset.alt_text)}" '
                        f'width="{asset.width}" height="{asset.height}" loading="lazy" />{caption}</figure>'
                    )
            continue
        if block.startswith("### "):
            rendered.append(f"<h3>{_inline_article_html(block[4:].strip(), origin)}</h3>")
        elif block.startswith("## "):
            rendered.append(f"<h2>{_inline_article_html(block[3:].strip(), origin)}</h2>")
        elif all(line.startswith("- ") for line in block.splitlines() if line.strip()):
            items = "".join(
                f"<li>{_inline_article_html(line[2:].strip(), origin)}</li>"
                for line in block.splitlines()
                if line.strip()
            )
            rendered.append(f"<ul>{items}</ul>")
        else:
            rendered.append(
                f"<p>{'<br />'.join(_inline_article_html(line, origin) for line in block.splitlines())}</p>"
            )
    return "".join(rendered)


def _article_seo_html(article: Any, database: ContentDatabase) -> str:
    origin = os.environ.get("VEDICWAY_PUBLIC_ORIGIN", "https://vedicway.ru").rstrip("/")
    canonical = article.canonical_url or f"{origin}/guide/{article.slug}"
    title = article.seo_title or article.title
    description = article.meta_description or article.excerpt
    request_hash = _article_payload_hash(_stored_article_payload(article))
    cover = _absolute_public_url(origin, article.cover_image_url)
    schema: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": article.title,
        "description": description,
        "url": canonical,
        "mainEntityOfPage": {"@type": "WebPage", "@id": canonical},
        "inLanguage": "ru-RU",
        "datePublished": article.published_at.isoformat(),
        "dateModified": article.updated_at.isoformat(),
        "author": {"@type": "Person", "name": article.author_name or "Редакция VedicWay"},
        "publisher": {
            "@type": "Organization",
            "name": "VedicWay",
            "url": origin,
            "logo": {"@type": "ImageObject", "url": f"{origin}/assets/brand-mark.png"},
        },
    }
    if cover:
        schema["image"] = [cover]
    schema_json = json.dumps(schema, ensure_ascii=False, separators=(",", ":")).replace(
        "<", "\\u003c"
    )
    cover_html = (
        f'<figure><img src="{escape(cover)}" alt="{escape(article.cover_image_alt or article.title)}" /></figure>'
        if cover
        else ""
    )
    return f"""<!doctype html>
<html lang="ru">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="robots" content="index, follow, max-image-preview:large" />
    <meta name="description" content="{escape(description)}" />
    <meta name="vedicway-article-request-sha256" content="{request_hash}" />
    <meta property="og:locale" content="ru_RU" />
    <meta property="og:type" content="article" />
    <meta property="og:site_name" content="VedicWay" />
    <meta property="og:title" content="{escape(title)}" />
    <meta property="og:description" content="{escape(description)}" />
    <meta property="og:url" content="{escape(canonical)}" />
    {f'<meta property="og:image" content="{escape(cover)}" />' if cover else ''}
    <link rel="canonical" href="{escape(canonical)}" />
    <link rel="icon" type="image/png" href="/assets/brand-mark.png" />
    <link rel="stylesheet" href="/assets/seo-entry.css" />
    <script type="application/ld+json">{schema_json}</script>
    <title>{escape(title)}</title>
  </head>
  <body>
    <div id="root">
      <main class="seo-prerender" data-yandex-first-screen>
        <nav aria-label="Хлебные крошки"><a href="/">Главная</a><a href="/guide">Гид по астрологии</a></nav>
        <article itemscope itemtype="https://schema.org/Article">
          <header><span>{escape(article.category)}</span><h1 itemprop="headline">{escape(article.title)}</h1><p>{escape(article.excerpt)}</p></header>
          {cover_html}
          <section itemprop="articleBody">{_article_content_html(article.content, database, origin)}</section>
        </article>
      </main>
    </div>
    <script type="module" crossorigin src="/assets/seo-entry.js"></script>
  </body>
</html>"""


def _validate_publish(payload: ArticlePayload) -> None:
    if payload.status != "published":
        return
    missing: list[str] = []
    if len(payload.excerpt) < 40:
        missing.append("excerpt")
    if len(payload.content) < 120:
        missing.append("content")
    if len(payload.meta_description) < 70:
        missing.append("meta_description")
    if not (payload.cover_media_id or (payload.cover_image_url and payload.cover_image_alt)):
        missing.append("cover")
    if missing:
        raise DomainError(
            "ARTICLE_INCOMPLETE", f"Для публикации заполните: {', '.join(missing)}", status_code=422
        )


def _if_match_revision(value: str | None) -> int:
    if not value:
        raise DomainError(
            "ARTICLE_REVISION_REQUIRED",
            "Обновите материал перед сохранением",
            status_code=428,
        )
    matched = re.fullmatch(r'(?:W/)?"?([1-9][0-9]*)"?', value.strip())
    if not matched:
        raise DomainError("ARTICLE_REVISION_INVALID", "Некорректная версия материала", status_code=400)
    return int(matched.group(1))


def _article_values(payload: ArticlePayload, database: ContentDatabase) -> dict[str, Any]:
    values = payload.model_dump()
    marker_ids = list(
        dict.fromkeys(re.findall(r"\{\{media:([a-f0-9-]{36})\}\}", payload.content))
    )
    referenced_ids = (
        [payload.cover_media_id] if payload.cover_media_id else []
    ) + marker_ids
    assets = {asset.id: asset for asset in database.list_media(referenced_ids)}
    if any(asset_id not in assets for asset_id in referenced_ids):
        raise DomainError(
            "ARTICLE_MEDIA_NOT_FOUND",
            "Одно из изображений статьи больше недоступно",
            status_code=422,
        )
    if payload.cover_media_id:
        cover = assets[payload.cover_media_id]
        if cover.purpose != "cover":
            raise DomainError(
                "ARTICLE_COVER_INVALID",
                "Выберите изображение, загруженное как обложка",
                status_code=422,
            )
        values["cover_image_url"] = cover.public_url
        values["cover_image_alt"] = payload.cover_image_alt or cover.alt_text
    for asset_id in marker_ids:
        if assets[asset_id].purpose != "body":
            raise DomainError(
                "ARTICLE_BODY_MEDIA_INVALID",
                "Изображение текста загружено в неверном режиме",
                status_code=422,
            )
    values["body_media_ids"] = marker_ids
    return values


def _media_directory() -> Path:
    root = Path(
        os.environ.get(
            "VEDICWAY_MEDIA_DIR", Path(os.environ.get("VEDICWAY_DATA_DIR", ".data")) / "media"
        )
    )
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _assert_seo_agent(authorization: str | None) -> None:
    expected = os.environ.get("VEDICWAY_SEO_AGENT_TOKEN", "")
    if not expected or (_production() and len(expected.encode("utf-8")) < 32):
        raise DomainError(
            "SEO_AGENT_NOT_CONFIGURED",
            "Контур публикации SEO-агента не настроен",
            recoverable=True,
            status_code=503,
        )
    supplied = authorization.removeprefix("Bearer ") if authorization else ""
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise DomainError(
            "SEO_AGENT_AUTH_REQUIRED",
            "Доступ SEO-агента отклонен",
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


def _article_payload_hash(payload: ArticlePayload) -> str:
    raw = json.dumps(payload.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _stored_article_payload(article: Any) -> ArticlePayload:
    return ArticlePayload.model_validate(
        {
            "title": article.title,
            "slug": article.slug,
            "category": article.category,
            "excerpt": article.excerpt,
            "content": article.content,
            "cover_media_id": article.cover_media_id,
            "body_media_ids": article.body_media_ids,
            "cover_image_url": article.cover_image_url,
            "cover_image_alt": article.cover_image_alt,
            "seo_title": article.seo_title,
            "meta_description": article.meta_description,
            "focus_keyphrase": article.focus_keyphrase,
            "canonical_url": article.canonical_url,
            "author_name": article.author_name,
            "status": article.status,
        }
    )


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


def _article_matches(article: Any, values: dict[str, Any]) -> bool:
    fields = (
        "title", "slug", "category", "excerpt", "content", "cover_media_id",
        "body_media_ids", "cover_image_url", "cover_image_alt", "seo_title",
        "meta_description", "focus_keyphrase", "canonical_url", "author_name", "status",
    )
    return all(getattr(article, field) == values.get(field) for field in fields)


def _dzen_full_text(article: Any, database: ContentDatabase, origin: str) -> str:
    cover = _absolute_public_url(origin, article.cover_image_url)
    cover_html = (
        f'<figure><img src="{escape(cover)}" alt="{escape(article.cover_image_alt or article.title)}" /></figure>'
        if cover
        else ""
    )
    request_hash = _article_payload_hash(_stored_article_payload(article))
    return (
        f"<!--vedicway-request-sha256:{request_hash}-->"
        f"<h1>{escape(article.title)}</h1><p>{escape(article.excerpt)}</p>"
        f"{cover_html}{_article_content_html(article.content, database, origin)}"
    )


def _cdata(value: str) -> str:
    safe = value.replace("]]>", "]]]]><![CDATA[>")
    return f"<![CDATA[{safe}]]>"


def _store_article_media(
    raw: bytes,
    *,
    purpose: Literal["cover", "body"],
    alt: str,
    title: str,
    caption: str,
    database: ContentDatabase,
    uploaded_by: str | None,
    asset_id: str | None = None,
) -> Any:
    if len(raw) > MAX_MEDIA_BYTES:
        raise DomainError("MEDIA_TOO_LARGE", "Изображение должно быть не больше 12 МБ", status_code=413)
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
        raise DomainError("MEDIA_INVALID", "Загрузите JPEG, PNG, WebP или AVIF", status_code=422) from exc
    if source.format not in ALLOWED_IMAGE_FORMATS:
        raise DomainError("MEDIA_INVALID", "Загрузите JPEG, PNG, WebP или AVIF", status_code=422)
    image = source.convert("RGB")
    image.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
    if purpose == "cover" and image.width < 700:
        raise DomainError(
            "MEDIA_COVER_TOO_NARROW",
            "Обложка должна быть шириной не меньше 700 пикселей для сайта и Дзена",
            status_code=422,
        )
    resolved_id = asset_id or str(uuid.uuid4())
    existing = database.get_media(resolved_id)
    if existing:
        return existing
    asset_directory = _media_directory() / "articles" / resolved_id
    asset_directory.mkdir(parents=True, exist_ok=False)
    original = asset_directory / "original.webp"
    image.save(original, "WEBP", quality=90, method=6)
    variant_widths = sorted({min(image.width, width) for width in (640, 960, 1280, 1600)})
    sources: list[dict[str, Any]] = []
    for width in variant_widths:
        height = max(1, round(image.height * width / image.width))
        variant = image if width == image.width else image.resize((width, height), Image.Resampling.LANCZOS)
        variant_path = asset_directory / f"{width}.webp"
        variant.save(variant_path, "WEBP", quality=88, method=6)
        sources.append(
            {
                "url": f"/media/articles/{resolved_id}/{width}.webp",
                "width": width,
                "mimeType": "image/webp",
            }
        )
    primary = sources[-1]
    destination = asset_directory / f"{primary['width']}.webp"
    values = {
        "id": resolved_id,
        "storage_key": f"articles/{resolved_id}/original.webp",
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
        return database.add_media(values, uploaded_by)
    except Exception:
        shutil.rmtree(asset_directory, ignore_errors=True)
        raise


def build_admin_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/v1/legal/config")
    async def legal_config() -> dict[str, object]:
        return public_legal_config()

    @router.get("/api/v1/content/articles")
    async def public_articles(request: Request) -> dict[str, Any]:
        database = _database(request)
        return {
            "items": [
                _article_dict(item, database)
                for item in database.list_articles(include_drafts=False)
            ]
        }

    @router.get("/api/v1/content/articles/{slug}")
    async def public_article(slug: str, request: Request) -> dict[str, Any]:
        database = _database(request)
        article = database.get_published_article_by_slug(slug)
        if not article:
            raise DomainError(
                "ARTICLE_NOT_FOUND", "Материал не найден", recoverable=False, status_code=404
            )
        return _article_dict(article, database)

    @router.get("/api/v1/seo/dzen/status", include_in_schema=False)
    async def dzen_status(request: Request) -> dict[str, Any]:
        articles = _database(request).list_articles(include_drafts=False)
        now = datetime.now(UTC)
        recent = sum(
            1
            for article in articles
            if article.published_at
            and (article.published_at if article.published_at.tzinfo else article.published_at.replace(tzinfo=UTC))
            >= now - timedelta(days=30)
        )
        return {
            "article_count": len(articles),
            "published_last_30_days": recent,
            "rss_ready": len(articles) >= 10 and recent >= 3,
            "publication_mode": os.environ.get("VEDICWAY_DZEN_PUBLICATION_MODE", "native-draft"),
        }

    async def dzen_feed(request: Request) -> Response:
        database = _database(request)
        origin = os.environ.get("VEDICWAY_PUBLIC_ORIGIN", "https://vedicway.ru").rstrip("/")
        mode = os.environ.get("VEDICWAY_DZEN_PUBLICATION_MODE", "native-draft")
        if mode not in {"native-draft", "publish"}:
            mode = "native-draft"
        items: list[str] = []
        for article in database.list_articles(include_drafts=False)[:500]:
            canonical = article.canonical_url or f"{origin}/guide/{article.slug}"
            published_at = article.published_at
            if published_at is None:
                continue
            if published_at.tzinfo is None:
                published_at = published_at.replace(tzinfo=UTC)
            cover = _absolute_public_url(origin, article.cover_image_url)
            enclosure = (
                f'<enclosure url="{escape(cover, quote=True)}" type="image/webp" />'
                if cover
                else ""
            )
            categories = "<category>format-article</category><category>index</category>"
            if mode == "native-draft":
                categories += "<category>native-draft</category>"
            items.append(
                "<item>"
                f"<title>{escape(article.title)}</title>"
                f"<link>{escape(canonical)}</link>"
                f'<guid isPermaLink="true">{escape(canonical)}</guid>'
                f"<pubDate>{format_datetime(published_at)}</pubDate>"
                f"<description>{_cdata(article.excerpt)}</description>"
                f"<yandex:full-text>{_cdata(_dzen_full_text(article, database, origin))}</yandex:full-text>"
                f"{enclosure}{categories}</item>"
            )
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<rss version="2.0" xmlns:yandex="http://news.yandex.ru">'
            "<channel><title>VedicWay: Гид по астрологии</title>"
            f"<link>{escape(origin)}/guide</link>"
            "<description>Практический гид по натальной карте и ведической астрологии</description>"
            "<language>ru</language>"
            + "".join(items)
            + "</channel></rss>"
        )
        return Response(
            content=body,
            media_type="application/rss+xml; charset=utf-8",
            headers={"Cache-Control": "public, max-age=300"},
        )

    router.add_api_route(
        "/api/v1/seo/dzen.xml", dzen_feed, methods=["GET"], include_in_schema=False
    )
    router.add_api_route("/feed/dzen.xml", dzen_feed, methods=["GET"], include_in_schema=False)

    @router.get("/internal/seo-agent/health", include_in_schema=False)
    async def seo_agent_health(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, str]:
        _assert_seo_agent(authorization)
        return {"status": "ready", "database_boundary": "content-api-only"}

    @router.post("/internal/seo-agent/media", status_code=201, include_in_schema=False)
    async def seo_agent_media(
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
        _assert_seo_agent(authorization)
        key = _assert_idempotency_key(idempotency_key)
        raw = await file.read(MAX_MEDIA_BYTES + 1)
        actual_hash = hashlib.sha256(raw).hexdigest()
        if not x_content_sha256 or not hmac.compare_digest(x_content_sha256.casefold(), actual_hash):
            raise DomainError(
                "CONTENT_HASH_MISMATCH",
                "Контрольная сумма изображения не совпала",
                recoverable=False,
                status_code=400,
            )
        media_request_hash = _media_payload_hash(
            actual_hash, purpose, alt, title, caption
        )
        if not hmac.compare_digest(key.rsplit(":", 1)[-1], media_request_hash[:32]):
            raise DomainError(
                "IDEMPOTENCY_KEY_CONTENT_MISMATCH",
                "Idempotency-Key не связан с контрольной суммой изображения",
                recoverable=False,
                status_code=400,
            )
        asset_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"vedicway-seo:{key}:{actual_hash}"))
        existing = _database(request).get_media(asset_id)
        asset = existing or _store_article_media(
            raw,
            purpose=purpose,
            alt=alt,
            title=title,
            caption=caption,
            database=_database(request),
            uploaded_by=None,
            asset_id=asset_id,
        )
        return {"asset": _media_dict(asset), "idempotent_replay": existing is not None}

    @router.put("/internal/seo-agent/articles/{slug}", include_in_schema=False)
    async def seo_agent_article(
        slug: str,
        payload: ArticlePayload,
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        x_content_sha256: Annotated[str | None, Header(alias="X-Content-SHA256")] = None,
        if_match: Annotated[str | None, Header(alias="If-Match")] = None,
    ) -> dict[str, Any]:
        _assert_seo_agent(authorization)
        key = _assert_idempotency_key(idempotency_key)
        if slug != payload.slug:
            raise DomainError("ARTICLE_SLUG_MISMATCH", "Slug в адресе и теле запроса различается", status_code=400)
        if payload.status != "published":
            raise DomainError("ARTICLE_STATUS_INVALID", "SEO-агент передает на сайт только одобренные публикации", status_code=422)
        minimum = max(2000, min(30_000, int(os.environ.get("VEDICWAY_SEO_MIN_ARTICLE_CHARS", "4500"))))
        if len(payload.content) < minimum:
            raise DomainError(
                "ARTICLE_TOO_SHORT",
                f"Текст SEO-статьи короче технического порога {minimum} символов",
                status_code=422,
            )
        actual_hash = _article_payload_hash(payload)
        if not x_content_sha256 or not hmac.compare_digest(x_content_sha256.casefold(), actual_hash):
            raise DomainError("CONTENT_HASH_MISMATCH", "Контрольная сумма статьи не совпала", status_code=400)
        if not hmac.compare_digest(key.rsplit(":", 1)[-1], actual_hash[:32]):
            raise DomainError(
                "IDEMPOTENCY_KEY_CONTENT_MISMATCH",
                "Idempotency-Key не связан с контрольной суммой статьи",
                recoverable=False,
                status_code=400,
            )
        _validate_publish(payload)
        database = _database(request)
        values = _article_values(payload, database)
        existing = database.get_article_by_slug(slug)
        if existing and _article_matches(existing, values):
            return {"article": _article_dict(existing, database), "idempotent_replay": True}
        try:
            if existing:
                if existing.published_at is not None and existing.slug != payload.slug:
                    raise DomainError("ARTICLE_SLUG_IMMUTABLE", "Адрес опубликованной статьи нельзя изменить", status_code=409)
                article = database.save_article(
                    values,
                    None,
                    article_id=existing.id,
                    expected_revision=_if_match_revision(if_match),
                )
            else:
                if if_match:
                    raise DomainError("ARTICLE_REVISION_INVALID", "If-Match нельзя передавать при создании статьи", status_code=400)
                article = database.save_article(values, None)
        except ArticleRevisionConflict as exc:
            raise DomainError("ARTICLE_REVISION_CONFLICT", "Статья изменилась после начала публикации", status_code=409) from exc
        return {"article": _article_dict(article, database), "idempotent_replay": False}

    @router.get(
        "/internal/seo/articles/{slug}/page",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    async def published_article_page(slug: str, request: Request) -> HTMLResponse:
        article = _database(request).get_published_article_by_slug(slug)
        if not article:
            raise DomainError(
                "ARTICLE_NOT_FOUND", "Материал не найден", recoverable=False, status_code=404
            )
        return HTMLResponse(
            _article_seo_html(article, _database(request)),
            headers={"Cache-Control": "public, max-age=60, stale-while-revalidate=300"},
        )

    @router.get("/media/articles/{asset_id}/{filename}")
    async def public_media(asset_id: str, filename: str, request: Request) -> FileResponse:
        if not re.fullmatch(r"[a-f0-9-]{36}", asset_id) or not re.fullmatch(
            r"[1-9][0-9]{1,3}\.webp", filename
        ):
            raise DomainError(
                "MEDIA_NOT_FOUND", "Изображение не найдено", recoverable=False, status_code=404
            )
        if not _database(request).media_is_public(asset_id, filename):
            raise DomainError(
                "MEDIA_NOT_FOUND", "Изображение не найдено", recoverable=False, status_code=404
            )
        article_media = (_media_directory() / "articles" / asset_id).resolve()
        path = (article_media / filename).resolve()
        if path.parent != article_media or not path.is_file():
            raise DomainError(
                "MEDIA_NOT_FOUND", "Изображение не найдено", recoverable=False, status_code=404
            )
        return FileResponse(
            path,
            media_type="image/webp",
            headers={"Cache-Control": "public, max-age=300"},
        )

    async def sitemap_response(request: Request) -> Response:
        origin = os.environ.get("VEDICWAY_PUBLIC_ORIGIN", "https://vedicway.ru").rstrip("/")
        urls = [
            f"<url><loc>{escape(origin)}/</loc></url>",
            f"<url><loc>{escape(origin)}/guide</loc></url>",
        ]
        for article in _database(request).list_articles(include_drafts=False):
            location = f"{origin}/guide/{article.slug}"
            urls.append(
                f"<url><loc>{escape(location)}</loc><lastmod>{article.updated_at.date().isoformat()}</lastmod></url>"
            )
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            + '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + "".join(urls)
            + "</urlset>"
        )
        return Response(
            content=body,
            media_type="application/xml; charset=utf-8",
            headers={"Cache-Control": "public, max-age=300"},
        )

    router.add_api_route(
        "/api/v1/seo/sitemap.xml", sitemap_response, methods=["GET"], include_in_schema=False
    )
    router.add_api_route("/sitemap.xml", sitemap_response, methods=["GET"], include_in_schema=False)

    @router.post("/api/v1/admin/auth/login")
    async def admin_login(payload: LoginPayload, request: Request) -> JSONResponse:
        _assert_same_origin(request)
        if request.headers.get("X-Admin-Request") != "1":
            raise DomainError("ADMIN_REQUEST_INVALID", "Некорректный запрос входа", status_code=400)
        await _enforce_admin_login_rate_limit(request)
        user = _database(request).authenticate(str(payload.email), payload.password)
        if not user or user.role != "admin":
            raise DomainError("ADMIN_LOGIN_FAILED", "Неверная почта или пароль", status_code=401)
        session_token, csrf_token = _database(request).create_admin_session(
            user, request.headers.get("user-agent"), _effective_client_ip(request)
        )
        response = JSONResponse(
            {
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "name": user.display_name,
                    "role": user.role,
                }
            }
        )
        _set_auth_cookies(response, session_token, csrf_token)
        return response

    @router.get("/api/v1/admin/me")
    async def admin_me(request: Request) -> dict[str, Any]:
        _, user = _current_admin(request)
        return {
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.display_name,
                "role": user.role,
            }
        }

    @router.post("/api/v1/admin/auth/logout")
    async def admin_logout(
        request: Request, x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None
    ) -> Response:
        session, _ = _current_admin(request)
        _assert_csrf(request, session, x_csrf_token)
        admin_cookie, _ = _cookie_names()
        _database(request).revoke_admin_session(request.cookies.get(admin_cookie))
        response = Response(status_code=204)
        _clear_auth_cookies(response)
        response.headers["Clear-Site-Data"] = '"cache", "cookies", "storage"'
        return response

    @router.get("/api/v1/admin/articles")
    async def admin_articles(request: Request) -> dict[str, Any]:
        _current_admin(request)
        database = _database(request)
        return {
            "items": [
                _article_dict(item, database)
                for item in database.list_articles(include_drafts=True)
            ]
        }

    @router.post("/api/v1/admin/articles", status_code=201)
    async def create_article(
        payload: ArticlePayload,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        session, user = _current_admin(request)
        _assert_csrf(request, session, x_csrf_token)
        _validate_publish(payload)
        database = _database(request)
        if database.slug_exists(payload.slug):
            raise DomainError("ARTICLE_SLUG_TAKEN", "Такой адрес уже занят", status_code=409)
        article = database.save_article(_article_values(payload, database), user.id)
        return _article_dict(article, database)

    @router.put("/api/v1/admin/articles/{article_id}")
    async def update_article(
        article_id: str,
        payload: ArticlePayload,
        request: Request,
        if_match: Annotated[str | None, Header(alias="If-Match")] = None,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        session, user = _current_admin(request)
        _assert_csrf(request, session, x_csrf_token)
        database = _database(request)
        existing = database.get_article(article_id)
        if not existing:
            raise DomainError(
                "ARTICLE_NOT_FOUND", "Материал не найден", recoverable=False, status_code=404
            )
        if existing.published_at is not None and payload.slug != existing.slug:
            raise DomainError(
                "ARTICLE_SLUG_IMMUTABLE",
                "Адрес опубликованного материала нельзя изменить",
                status_code=409,
            )
        _validate_publish(payload)
        if database.slug_exists(payload.slug, except_id=article_id):
            raise DomainError("ARTICLE_SLUG_TAKEN", "Такой адрес уже занят", status_code=409)
        try:
            article = database.save_article(
                _article_values(payload, database),
                user.id,
                article_id=article_id,
                expected_revision=_if_match_revision(if_match),
            )
        except ArticleRevisionConflict as exc:
            raise DomainError(
                "ARTICLE_REVISION_CONFLICT",
                "Материал уже изменён в другой вкладке. Обновите редактор.",
                status_code=409,
            ) from exc
        return _article_dict(article, database)

    @router.delete("/api/v1/admin/articles/{article_id}", status_code=204)
    async def delete_article(
        article_id: str,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> Response:
        session, _ = _current_admin(request)
        _assert_csrf(request, session, x_csrf_token)
        if not _database(request).delete_article(article_id):
            raise DomainError(
                "ARTICLE_NOT_FOUND", "Материал не найден", recoverable=False, status_code=404
            )
        return Response(status_code=204)

    @router.post("/api/v1/admin/media", status_code=201)
    async def upload_media(
        request: Request,
        file: Annotated[UploadFile, File()],
        purpose: Annotated[Literal["cover", "body"], Form()],
        alt: Annotated[str, Form(min_length=1, max_length=300)],
        title: Annotated[str, Form(max_length=240)] = "",
        caption: Annotated[str, Form(max_length=500)] = "",
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        session, user = _current_admin(request)
        _assert_csrf(request, session, x_csrf_token)
        raw = await file.read(MAX_MEDIA_BYTES + 1)
        if len(raw) > MAX_MEDIA_BYTES:
            raise DomainError(
                "MEDIA_TOO_LARGE", "Изображение должно быть не больше 12 МБ", status_code=413
            )
        try:
            source = Image.open(io.BytesIO(raw))
            if source.width * source.height > 40_000_000:
                raise DomainError(
                    "MEDIA_DIMENSIONS_INVALID",
                    "Слишком большое разрешение изображения",
                    status_code=422,
                )
            source.load()
        except DomainError:
            raise
        except (Image.DecompressionBombError, UnidentifiedImageError, OSError) as exc:
            raise DomainError(
                "MEDIA_INVALID", "Загрузите JPEG, PNG, WebP или AVIF", status_code=422
            ) from exc
        if source.format not in ALLOWED_IMAGE_FORMATS:
            raise DomainError(
                "MEDIA_INVALID", "Загрузите JPEG, PNG, WebP или AVIF", status_code=422
            )
        image = source.convert("RGB")
        image.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
        asset_id = str(uuid.uuid4())
        asset_directory = _media_directory() / "articles" / asset_id
        asset_directory.mkdir(parents=True, exist_ok=False)
        original = asset_directory / "original.webp"
        image.save(original, "WEBP", quality=90, method=6)
        variant_widths = sorted({min(image.width, width) for width in (640, 960, 1280, 1600)})
        sources: list[dict[str, Any]] = []
        for width in variant_widths:
            height = max(1, round(image.height * width / image.width))
            variant = (
                image
                if width == image.width
                else image.resize((width, height), Image.Resampling.LANCZOS)
            )
            variant_path = asset_directory / f"{width}.webp"
            variant.save(variant_path, "WEBP", quality=88, method=6)
            sources.append(
                {
                    "url": f"/media/articles/{asset_id}/{width}.webp",
                    "width": width,
                    "mimeType": "image/webp",
                }
            )
        primary = sources[-1]
        destination = asset_directory / f"{primary['width']}.webp"
        primary_height = max(1, round(image.height * int(primary["width"]) / image.width))
        storage_key = f"articles/{asset_id}/original.webp"
        values = {
            "id": asset_id,
            "storage_key": storage_key,
            "public_url": primary["url"],
            "sources": sources,
            "purpose": purpose,
            "mime_type": "image/webp",
            "width": int(primary["width"]),
            "height": primary_height,
            "size_bytes": destination.stat().st_size,
            "alt_text": alt.strip(),
            "title": title.strip(),
            "caption": caption.strip(),
        }
        try:
            asset = _database(request).add_media(values, user.id)
        except Exception:
            shutil.rmtree(asset_directory, ignore_errors=True)
            raise
        return {
            "asset": {
                "id": asset.id,
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
        }

    @router.delete("/api/v1/admin/media/{asset_id}", status_code=204)
    async def delete_media(
        asset_id: str,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> Response:
        session, _ = _current_admin(request)
        _assert_csrf(request, session, x_csrf_token)
        database = _database(request)
        asset = database.get_media(asset_id)
        if not asset:
            raise DomainError(
                "MEDIA_NOT_FOUND", "Изображение не найдено", recoverable=False, status_code=404
            )
        if database.media_in_use(asset_id):
            raise DomainError(
                "MEDIA_IN_USE", "Сначала удалите изображение из статьи", status_code=409
            )
        media_root = (_media_directory() / "articles").resolve()
        storage_match = re.fullmatch(r"articles/([a-f0-9-]{36})/original\.webp", asset.storage_key)
        directory_id = storage_match.group(1) if storage_match else asset.id
        asset_directory = (media_root / directory_id).resolve()
        if asset_directory.parent != media_root:
            raise DomainError(
                "MEDIA_PATH_INVALID",
                "Некорректный путь медиаресурса",
                recoverable=False,
                status_code=500,
            )
        if asset_directory.exists():
            shutil.rmtree(asset_directory)
        database.delete_media(asset_id)
        return Response(status_code=204)

    return router
