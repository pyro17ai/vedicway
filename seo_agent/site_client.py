from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx
from PIL import Image, UnidentifiedImageError

from .db import AgentLedger, LedgerError, canonical_json, utc_now
from .markdown_renderer import render_markdown
from .quality_gate import evaluate

MAX_MEDIA_BYTES = 12 * 1024 * 1024
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "AVIF"}


def _require_success(response: httpx.Response, operation: str) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        detail = response.text.strip().replace("\n", " ")[:1000]
        message = f"{operation} returned HTTP {response.status_code}"
        if detail:
            message = f"{message}: {detail}"
        raise LedgerError(message) from error


def _manifest_from_active_run_claim(
    ledger: AgentLedger, manifest: dict[str, Any]
) -> dict[str, Any]:
    run_id = os.environ.get("VEDICWAY_SEO_RUN_ID", "").strip()
    if not run_id:
        return manifest
    now = utc_now()
    with ledger.connect() as connection:
        rows = connection.execute(
            """SELECT d.id,d.claim_token,d.content_hash,d.slug,d.title,d.excerpt,
            d.content_markdown,d.seo_title,d.meta_description,d.focus_keyphrase,
            d.category,d.author_name
            FROM article_drafts d
            JOIN cron_runs r ON r.id=d.claim_run_id
            WHERE d.claim_run_id=%s AND d.status IN ('publishing','published')
              AND d.claim_expires_at>=%s AND r.status='running'
              AND r.job_name='article_site_publish'
            ORDER BY d.updated_at,d.id""",
            (run_id, now),
        ).fetchall()
    if len(rows) != 1:
        raise LedgerError(
            "Site publication requires exactly one active draft claim for this run"
        )
    draft = rows[0]
    supplied_article = manifest.get("article")
    if not isinstance(supplied_article, dict):
        raise LedgerError("Publication manifest must contain an article object")
    article = {
        "section": "blog",
        "difficulty": supplied_article.get("difficulty", "beginner"),
        "title": draft["title"],
        "slug": draft["slug"],
        "category": draft["category"],
        "excerpt": draft["excerpt"],
        "content_markdown": draft["content_markdown"],
        "seo_title": draft["seo_title"],
        "meta_description": draft["meta_description"],
        "focus_keyphrase": draft["focus_keyphrase"],
        "tags": supplied_article.get("tags", []),
        "schema_extra": supplied_article.get("schema_extra", {}),
        "author_name": draft["author_name"],
        "cover_image_alt": "pending canonical media",
    }
    return {
        "schema_version": "2.0",
        "draft_id": str(draft["id"]),
        "claim_token": str(draft["claim_token"]),
        "content_hash": str(draft["content_hash"]),
        "article": article,
        "media": [],
    }


def _owned_path(value: str, data_dir: Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = data_dir / path
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(data_dir)
    except ValueError as exc:
        raise LedgerError(
            "Publication media must stay inside VEDICWAY_SEO_DATA_DIR"
        ) from exc
    if not resolved.is_file():
        raise LedgerError(f"Publication media is missing: {resolved}")
    return resolved


def _article_payload(article: dict[str, Any]) -> tuple[dict[str, Any], str]:
    try:
        from vedicway_backend.content_api import (
            ContentArticlePayload,
            _content_payload_hash,
        )
    except ImportError as exc:
        raise LedgerError(
            "vedicway_backend must be installed in the SEO agent runtime"
        ) from exc
    parsed = ContentArticlePayload.model_validate(article)
    return parsed.model_dump(mode="json"), _content_payload_hash(parsed)


def _media_request_hash(item: dict[str, Any], content_sha256: str) -> str:
    try:
        from vedicway_backend.content_api import _media_payload_hash
    except ImportError as exc:
        raise LedgerError(
            "vedicway_backend must be installed in the SEO agent runtime"
        ) from exc
    return _media_payload_hash(
        content_sha256,
        str(item["purpose"]),
        str(item["alt_text"]),
        str(item.get("title", "")),
        str(item.get("caption", "")),
        item.get("distribution_role") == "pinterest",
    )


def _validate_media_file(item: dict[str, Any]) -> None:
    path = item["resolved_path"]
    if path.stat().st_size > MAX_MEDIA_BYTES:
        raise LedgerError(f"Publication media exceeds 12 MB: {path.name}")
    try:
        with Image.open(path) as source:
            image_format = source.format
            width, height = source.size
            if width * height > 40_000_000:
                raise LedgerError(
                    f"Publication media exceeds 40 million pixels: {path.name}"
                )
            source.verify()
    except LedgerError:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError) as exc:
        raise LedgerError(
            f"Publication media is not a valid supported image: {path.name}"
        ) from exc
    if image_format not in ALLOWED_IMAGE_FORMATS:
        raise LedgerError(f"Publication media format is not supported: {path.name}")
    if item.get("purpose") == "cover" and width < 1200:
        raise LedgerError("SEO agent cover must be at least 1200 pixels wide")
    if item.get("distribution_role") == "pinterest" and (width, height) != (
        1000,
        1500,
    ):
        raise LedgerError("Pinterest distribution media must be exactly 1000x1500")


def _manifest_media_from_ledger(
    ledger: AgentLedger, draft_id: str, claim_token: str
) -> list[dict[str, Any]]:
    with ledger.connect() as connection:
        rows = connection.execute(
            """SELECT m.id,m.local_path,m.purpose,m.alt_text,m.title,m.caption,
            m.source_kind,m.source_url,m.license_note,m.distribution_role,
            m.width,m.height
            FROM article_media m
            JOIN article_drafts d ON d.id=m.draft_id
            WHERE d.id=%s AND d.status IN ('publishing','published')
              AND d.claim_token=%s
            ORDER BY CASE m.purpose WHEN 'cover' THEN 0 ELSE 1 END,m.created_at,m.id""",
            (draft_id, claim_token),
        ).fetchall()
    media: list[dict[str, Any]] = []
    body_index = 0
    for row in rows:
        item = {
            "media_id": str(row["id"]),
            "local_path": str(row["local_path"]),
            "purpose": str(row["purpose"]),
            "alt_text": str(row["alt_text"]),
            "source_kind": str(row["source_kind"]),
            "license_note": str(row["license_note"]),
            "width": int(row["width"]),
            "height": int(row["height"]),
        }
        for name in ("title", "caption", "source_url", "distribution_role"):
            if row[name] not in {None, ""}:
                item[name] = row[name]
        if item["purpose"] == "body" and "distribution_role" not in item:
            body_index += 1
            item["placeholder"] = f"{{{{media:body-{body_index}}}}}"
        media.append(item)
    return media


def _validate_manifest_claim(
    ledger: AgentLedger,
    manifest: dict[str, Any],
    resolved_media: list[dict[str, Any]],
) -> None:
    expected_keys = {
        "schema_version",
        "draft_id",
        "claim_token",
        "content_hash",
        "article",
        "media",
    }
    if set(manifest) != expected_keys or manifest.get("schema_version") != "2.0":
        raise LedgerError("Publication manifest does not match schema version 2.0")
    report = evaluate(manifest)
    if not report["passed"]:
        raise LedgerError(
            "Publication manifest failed quality gate: " + ", ".join(report["failed"])
        )
    if manifest.get("content_hash") != report["content_hash"]:
        raise LedgerError("Manifest content_hash differs from its article content")
    article = manifest["article"]
    now = utc_now()
    with ledger.connect() as connection:
        draft = connection.execute(
            """SELECT id,status,claim_token,claim_expires_at,content_hash,slug,title,excerpt,
            content_markdown,seo_title,meta_description,focus_keyphrase,category,author_name
            FROM article_drafts WHERE id=%s""",
            (manifest["draft_id"],),
        ).fetchone()
        if (
            not draft
            or draft["status"] not in {"publishing", "published"}
            or draft["claim_token"] != manifest["claim_token"]
            or not draft["claim_expires_at"]
            or draft["claim_expires_at"] < now
        ):
            raise LedgerError("Publication manifest requires the active draft claim")
        if draft["content_hash"] != manifest["content_hash"]:
            raise LedgerError(
                "Publication manifest does not match the claimed draft hash"
            )
        fields = {
            "slug": "slug",
            "title": "title",
            "excerpt": "excerpt",
            "content_markdown": "content_markdown",
            "seo_title": "seo_title",
            "meta_description": "meta_description",
            "focus_keyphrase": "focus_keyphrase",
            "category": "category",
            "author_name": "author_name",
        }
        if any(article.get(name) != draft[column] for name, column in fields.items()):
            raise LedgerError(
                "Publication article fields differ from the claimed draft"
            )
        recorded_media = [
            dict(row)
            for row in connection.execute(
                "SELECT purpose,local_path,alt_text,source_kind,license_note,checksum,distribution_role FROM article_media WHERE draft_id=%s",
                (manifest["draft_id"],),
            )
        ]
    for item in resolved_media:
        digest = hashlib.sha256(item["resolved_path"].read_bytes()).hexdigest()
        match = next(
            (
                record
                for record in recorded_media
                if record["purpose"] == item.get("purpose")
                and record["checksum"] == digest
                and _owned_path(record["local_path"], ledger.data_dir)
                == item["resolved_path"]
            ),
            None,
        )
        if not match or any(
            item.get(name) != match[name]
            for name in ("alt_text", "source_kind", "license_note")
        ):
            raise LedgerError("Publication media differs from the draft media ledger")
        if item.get("distribution_role") != match["distribution_role"]:
            raise LedgerError("Publication media distribution role differs from the ledger")


def publish_bundle(
    manifest_path: str | Path,
    *,
    dry_run: bool = False,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    ledger = AgentLedger()
    data_dir = ledger.data_dir
    manifest_file = _owned_path(str(manifest_path), data_dir)
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("article"), dict):
        raise LedgerError("Publication manifest must contain an article object")
    manifest = _manifest_from_active_run_claim(ledger, manifest)
    if manifest["article"].get("section") != "blog":
        raise LedgerError("SEO agent publication is restricted to the VedicWay blog section")
    manifest["media"] = _manifest_media_from_ledger(
        ledger,
        str(manifest.get("draft_id", "")),
        str(manifest.get("claim_token", "")),
    )
    media = manifest["media"]
    if (
        not isinstance(media, list)
        or sum(
            item.get("purpose") == "cover" for item in media if isinstance(item, dict)
        )
        != 1
    ):
        raise LedgerError("Publication manifest must contain exactly one cover")
    manifest["article"]["cover_image_alt"] = next(
        str(item["alt_text"]) for item in media if item.get("purpose") == "cover"
    )
    required_media_keys = {
        "local_path",
        "purpose",
        "alt_text",
        "source_kind",
        "license_note",
    }
    allowed_media_keys = required_media_keys | {
        "media_id",
        "placeholder",
        "title",
        "caption",
        "source_url",
        "distribution_role",
        "width",
        "height",
    }
    if any(
        not isinstance(item, dict)
        or not required_media_keys.issubset(item)
        or set(item).difference(allowed_media_keys)
        for item in media
    ):
        raise LedgerError("Publication media does not match the manifest contract")
    distribution_only_media = [
        item
        for item in media
        if item.get("purpose") == "body" and item.get("distribution_role")
    ]
    if any(item.get("placeholder") for item in distribution_only_media):
        raise LedgerError("Distribution-only media must not appear in article HTML")
    placeholders = [
        str(item.get("placeholder", ""))
        for item in media
        if item.get("purpose") == "body" and not item.get("distribution_role")
    ]
    if any(
        not re.fullmatch(r"\{\{media:body-[1-9][0-9]*\}\}", value)
        for value in placeholders
    ) or len(placeholders) != len(set(placeholders)):
        raise LedgerError("Body media requires unique {{media:body-N}} placeholders")
    article_content = str(manifest["article"].get("content_markdown", ""))
    content_placeholders = re.findall(
        r"\{\{media:body-[1-9][0-9]*\}\}", article_content
    )
    if set(content_placeholders) != set(placeholders) or any(
        content_placeholders.count(value) != 1 for value in placeholders
    ):
        raise LedgerError(
            "Every body media placeholder must occur exactly once in the article"
        )
    resolved_media = [
        {**item, "resolved_path": _owned_path(str(item["local_path"]), data_dir)}
        for item in media
    ]
    for item in resolved_media:
        _validate_media_file(item)
    _validate_manifest_claim(ledger, manifest, resolved_media)
    preview = {
        "slug": manifest["article"].get("slug"),
        "draft_id": manifest.get("draft_id"),
        "media_count": len(resolved_media),
        "target": "site",
    }
    if dry_run:
        return {"dry_run": True, **preview}
    token = os.environ.get("VEDICWAY_SEO_AGENT_TOKEN", "")
    base_url = os.environ.get(
        "VEDICWAY_SEO_AGENT_BASE_URL", "http://backend:8000"
    ).rstrip("/")
    public_origin = os.environ.get("VEDICWAY_PUBLIC_ORIGIN", "").rstrip("/")
    if len(token) < 32 or not public_origin.startswith("https://"):
        raise LedgerError(
            "SEO agent token and HTTPS VEDICWAY_PUBLIC_ORIGIN are required"
        )
    timeout = httpx.Timeout(
        float(os.environ.get("VEDICWAY_SEO_HTTP_TIMEOUT_SECONDS", "30"))
    )
    article = dict(manifest["article"])
    article["content_html"] = render_markdown(str(article.pop("content_markdown")))
    uploaded: list[dict[str, Any]] = []
    with httpx.Client(
        timeout=timeout, follow_redirects=True, transport=transport
    ) as client:
        health = client.get(
            f"{base_url}/internal/content-agent/health",
            headers={"Authorization": f"Bearer {token}"},
        )
        _require_success(health, "Content-agent health check")
        if distribution_only_media and (
            health.json().get("capabilities", {}).get("public_unlisted_media")
            is not True
        ):
            raise LedgerError(
                "Content-agent does not support public-unlisted distribution media"
            )
        for index, item in enumerate(resolved_media, start=1):
            raw = item["resolved_path"].read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            media_request_hash = _media_request_hash(item, digest)
            key = (
                f"{manifest.get('draft_id', article.get('slug'))}:"
                f"media:{index}:{media_request_hash[:32]}"
            )
            response = client.post(
                f"{base_url}/internal/content-agent/media",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": key,
                    "X-Content-SHA256": digest,
                },
                files={
                    "file": (
                        item["resolved_path"].name,
                        raw,
                        mimetypes.guess_type(item["resolved_path"].name)[0]
                        or "application/octet-stream",
                    )
                },
                data={
                    "purpose": item["purpose"],
                    "alt": item["alt_text"],
                    "title": item.get("title", ""),
                    "caption": item.get("caption", ""),
                    "public_unlisted": (
                        "true"
                        if item.get("distribution_role") == "pinterest"
                        else "false"
                    ),
                },
            )
            _require_success(response, f"Media upload {index}")
            asset = response.json()["asset"]
            uploaded.append({"manifest": item, "asset": asset, "sha256": digest})
            if item["purpose"] == "cover":
                article["cover_media_id"] = asset["id"]
                article["cover_image_url"] = asset["url"]
                article["cover_image_alt"] = item["alt_text"]
            elif not item.get("distribution_role"):
                placeholder = str(item.get("placeholder", ""))
                if not placeholder or placeholder not in str(
                    article.get("content_html", "")
                ):
                    raise LedgerError(
                        f"Body media placeholder is missing from article: {placeholder}"
                    )
                article["content_html"] = str(article["content_html"]).replace(
                    placeholder,
                    f'<figure data-media-id="{asset["id"]}"></figure>',
                    1,
                )
        normalized, request_hash = _article_payload(article)
        slug = str(normalized["slug"])
        section = str(normalized["section"])
        headers = {
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": f"{manifest.get('draft_id', slug)}:article:{request_hash[:32]}",
            "X-Content-SHA256": request_hash,
        }
        current = client.get(f"{base_url}/api/v1/content/{section}/articles/{slug}")
        if current.status_code == 200:
            headers["If-Match"] = str(current.json()["revision"])
        elif current.status_code != 404:
            _require_success(current, "Current article lookup")
        published = client.put(
            f"{base_url}/internal/content-agent/{section}/articles/{slug}",
            headers=headers,
            json=normalized,
        )
        _require_success(published, "Article publication")
        public_url = f"{public_origin}/{section}/{slug}"
        page = client.get(public_url)
        _require_success(page, "Public article verification")
        sitemap = client.get(f"{public_origin}/sitemap.xml")
        _require_success(sitemap, "Sitemap verification")
        cover_url = urljoin(f"{public_origin}/", str(normalized["cover_image_url"]))
        public_article_media = uploaded
        media_responses: dict[str, httpx.Response] = {}
        for item in public_article_media:
            media_url = urljoin(f"{public_origin}/", str(item["asset"]["url"]))
            media_response = client.get(media_url)
            _require_success(media_response, "Public media verification")
            media_responses[media_url] = media_response
    checks = {
        "canonical": str(page.url).rstrip("/") == public_url
        and f'<link rel="canonical" href="{public_url}"' in page.text,
        "article_schema": (
            '"@type":"BlogPosting"' in page.text
            if str(normalized["section"]) == "blog"
            else False
        ),
        "title": str(normalized["title"]) in page.text,
        "request_hash": bool(request_hash),
        "sitemap": public_url in sitemap.text,
        "cover": media_responses[cover_url]
        .headers.get("content-type", "")
        .startswith("image/"),
        "all_media_public": len(media_responses) == len(public_article_media)
        and all(
            response.headers.get("content-type", "").startswith("image/")
            for response in media_responses.values()
        ),
    }
    if not all(checks.values()):
        raise LedgerError(
            "Public verification failed: "
            + ", ".join(name for name, ok in checks.items() if not ok)
        )
    for item in uploaded:
        manifest_item = item["manifest"]
        ledger.write_record(
            "media",
            {
                "draft_id": manifest["draft_id"],
                "purpose": manifest_item["purpose"],
                "local_path": str(manifest_item["resolved_path"]),
                "alt_text": manifest_item["alt_text"],
                "title": manifest_item.get("title", ""),
                "caption": manifest_item.get("caption", ""),
                "source_kind": manifest_item["source_kind"],
                "source_url": manifest_item.get("source_url"),
                "license_note": manifest_item["license_note"],
                "checksum": item["sha256"],
                "distribution_role": manifest_item.get("distribution_role"),
                "backend_media_id": item["asset"]["id"],
                "public_url": urljoin(f"{public_origin}/", item["asset"]["url"]),
            },
        )
    return {
        **preview,
        "request_hash": request_hash,
        "draft_content_hash": manifest.get("content_hash"),
        "public_url": public_url,
        "article": published.json()["article"],
        "uploaded_media": [
            {
                "media_id": item["manifest"]["media_id"],
                "backend_media_id": item["asset"]["id"],
                "public_url": urljoin(
                    f"{public_origin}/", str(item["asset"]["url"])
                ),
                "purpose": item["manifest"]["purpose"],
                "distribution_role": item["manifest"].get("distribution_role"),
                "width": item["manifest"]["width"],
                "height": item["manifest"]["height"],
                "sha256": item["sha256"],
            }
            for item in uploaded
        ],
        "evidence": {
            "checks": checks,
            "page_sha256": hashlib.sha256(page.content).hexdigest(),
            "sitemap_sha256": hashlib.sha256(sitemap.content).hexdigest(),
        },
        "manifest_hash": hashlib.sha256(
            canonical_json(manifest).encode("utf-8")
        ).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Publish one approved VedicWay SEO article"
    )
    parser.add_argument("manifest")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                publish_bundle(args.manifest, dry_run=args.dry_run),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    except (
        LedgerError,
        OSError,
        ValueError,
        json.JSONDecodeError,
        httpx.HTTPError,
    ) as error:
        print(
            json.dumps(
                {"status": "error", "error": str(error)},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
