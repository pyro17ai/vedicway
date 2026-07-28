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
from .quality_gate import evaluate

MAX_MEDIA_BYTES = 12 * 1024 * 1024
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "AVIF"}


def _owned_path(value: str, data_dir: Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = data_dir / path
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(data_dir)
    except ValueError as exc:
        raise LedgerError("Publication media must stay inside VEDICWAY_SEO_DATA_DIR") from exc
    if not resolved.is_file():
        raise LedgerError(f"Publication media is missing: {resolved}")
    return resolved


def _article_payload(article: dict[str, Any]) -> tuple[dict[str, Any], str]:
    try:
        from vedicway_backend.admin_api import ArticlePayload, _article_payload_hash
    except ImportError as exc:
        raise LedgerError("vedicway_backend must be installed in the SEO agent runtime") from exc
    parsed = ArticlePayload.model_validate(article)
    return parsed.model_dump(mode="json"), _article_payload_hash(parsed)


def _media_request_hash(item: dict[str, Any], content_sha256: str) -> str:
    try:
        from vedicway_backend.admin_api import _media_payload_hash
    except ImportError as exc:
        raise LedgerError("vedicway_backend must be installed in the SEO agent runtime") from exc
    return _media_payload_hash(
        content_sha256,
        str(item["purpose"]),
        str(item["alt_text"]),
        str(item.get("title", "")),
        str(item.get("caption", "")),
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
                raise LedgerError(f"Publication media exceeds 40 million pixels: {path.name}")
            source.verify()
    except LedgerError:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError) as exc:
        raise LedgerError(f"Publication media is not a valid supported image: {path.name}") from exc
    if image_format not in ALLOWED_IMAGE_FORMATS:
        raise LedgerError(f"Publication media format is not supported: {path.name}")
    if item.get("purpose") == "cover" and width < 1200:
        raise LedgerError("SEO agent cover must be at least 1200 pixels wide")


def _validate_manifest_claim(
    ledger: AgentLedger,
    manifest: dict[str, Any],
    resolved_media: list[dict[str, Any]],
) -> None:
    expected_keys = {"schema_version", "draft_id", "claim_token", "content_hash", "article", "media"}
    if set(manifest) != expected_keys or manifest.get("schema_version") != "1.0":
        raise LedgerError("Publication manifest does not match schema version 1.0")
    report = evaluate(manifest)
    if not report["passed"]:
        raise LedgerError("Publication manifest failed quality gate: " + ", ".join(report["failed"]))
    if manifest.get("content_hash") != report["content_hash"]:
        raise LedgerError("Manifest content_hash differs from its article content")
    article = manifest["article"]
    now = utc_now()
    with ledger.connect() as connection:
        draft = connection.execute(
            """SELECT id,status,claim_token,claim_expires_at,content_hash,slug,title,excerpt,
            content_markdown,seo_title,meta_description,focus_keyphrase,category,author_name
            FROM article_drafts WHERE id=?""",
            (manifest["draft_id"],),
        ).fetchone()
        if (
            not draft
            or draft["status"] != "publishing"
            or draft["claim_token"] != manifest["claim_token"]
            or not draft["claim_expires_at"]
            or draft["claim_expires_at"] < now
        ):
            raise LedgerError("Publication manifest requires the active draft claim")
        if draft["content_hash"] != manifest["content_hash"]:
            raise LedgerError("Publication manifest does not match the claimed draft hash")
        fields = {
            "slug": "slug",
            "title": "title",
            "excerpt": "excerpt",
            "content": "content_markdown",
            "seo_title": "seo_title",
            "meta_description": "meta_description",
            "focus_keyphrase": "focus_keyphrase",
            "category": "category",
            "author_name": "author_name",
        }
        if any(article.get(name) != draft[column] for name, column in fields.items()):
            raise LedgerError("Publication article fields differ from the claimed draft")
        recorded_media = [dict(row) for row in connection.execute(
            "SELECT purpose,local_path,alt_text,source_kind,license_note,checksum FROM article_media WHERE draft_id=?",
            (manifest["draft_id"],),
        )]
    for item in resolved_media:
        digest = hashlib.sha256(item["resolved_path"].read_bytes()).hexdigest()
        match = next(
            (
                record
                for record in recorded_media
                if record["purpose"] == item.get("purpose")
                and record["checksum"] == digest
                and _owned_path(record["local_path"], ledger.data_dir) == item["resolved_path"]
            ),
            None,
        )
        if not match or any(
            item.get(name) != match[name]
            for name in ("alt_text", "source_kind", "license_note")
        ):
            raise LedgerError("Publication media differs from the draft media ledger")


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
    media = manifest.get("media", [])
    if not isinstance(media, list) or sum(item.get("purpose") == "cover" for item in media if isinstance(item, dict)) != 1:
        raise LedgerError("Publication manifest must contain exactly one cover")
    required_media_keys = {
        "local_path",
        "purpose",
        "alt_text",
        "source_kind",
        "license_note",
    }
    allowed_media_keys = required_media_keys | {
        "placeholder",
        "title",
        "caption",
        "source_url",
    }
    if any(
        not isinstance(item, dict)
        or not required_media_keys.issubset(item)
        or set(item).difference(allowed_media_keys)
        for item in media
    ):
        raise LedgerError("Publication media does not match the manifest contract")
    placeholders = [
        str(item.get("placeholder", ""))
        for item in media
        if item.get("purpose") == "body"
    ]
    if (
        any(not re.fullmatch(r"\{\{media:body-[1-9][0-9]*\}\}", value) for value in placeholders)
        or len(placeholders) != len(set(placeholders))
    ):
        raise LedgerError("Body media requires unique {{media:body-N}} placeholders")
    article_content = str(manifest["article"].get("content", ""))
    content_placeholders = re.findall(r"\{\{media:body-[1-9][0-9]*\}\}", article_content)
    if set(content_placeholders) != set(placeholders) or any(
        content_placeholders.count(value) != 1 for value in placeholders
    ):
        raise LedgerError("Every body media placeholder must occur exactly once in the article")
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
        "target": "site+dzen-rss",
    }
    if dry_run:
        return {"dry_run": True, **preview}
    token = os.environ.get("VEDICWAY_SEO_AGENT_TOKEN", "")
    base_url = os.environ.get("VEDICWAY_SEO_AGENT_BASE_URL", "http://backend:8000").rstrip("/")
    public_origin = os.environ.get("VEDICWAY_PUBLIC_ORIGIN", "").rstrip("/")
    if len(token) < 32 or not public_origin.startswith("https://"):
        raise LedgerError("SEO agent token and HTTPS VEDICWAY_PUBLIC_ORIGIN are required")
    timeout = httpx.Timeout(float(os.environ.get("VEDICWAY_SEO_HTTP_TIMEOUT_SECONDS", "30")))
    article = dict(manifest["article"])
    article["body_media_ids"] = []
    uploaded: list[dict[str, Any]] = []
    with httpx.Client(timeout=timeout, follow_redirects=True, transport=transport) as client:
        health = client.get(f"{base_url}/internal/seo-agent/health", headers={"Authorization": f"Bearer {token}"})
        health.raise_for_status()
        for index, item in enumerate(resolved_media, start=1):
            raw = item["resolved_path"].read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            media_request_hash = _media_request_hash(item, digest)
            key = (
                f"{manifest.get('draft_id', article.get('slug'))}:"
                f"media:{index}:{media_request_hash[:32]}"
            )
            response = client.post(
                f"{base_url}/internal/seo-agent/media",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": key,
                    "X-Content-SHA256": digest,
                },
                files={
                    "file": (
                        item["resolved_path"].name,
                        raw,
                        mimetypes.guess_type(item["resolved_path"].name)[0] or "application/octet-stream",
                    )
                },
                data={
                    "purpose": item["purpose"],
                    "alt": item["alt_text"],
                    "title": item.get("title", ""),
                    "caption": item.get("caption", ""),
                },
            )
            response.raise_for_status()
            asset = response.json()["asset"]
            uploaded.append({"manifest": item, "asset": asset, "sha256": digest})
            if item["purpose"] == "cover":
                article["cover_media_id"] = asset["id"]
                article["cover_image_url"] = asset["url"]
                article["cover_image_alt"] = item["alt_text"]
            else:
                placeholder = str(item.get("placeholder", ""))
                if not placeholder or placeholder not in str(article.get("content", "")):
                    raise LedgerError(f"Body media placeholder is missing from article: {placeholder}")
                article["content"] = str(article["content"]).replace(
                    placeholder, f"{{{{media:{asset['id']}}}}}", 1
                )
                article["body_media_ids"].append(asset["id"])
        normalized, request_hash = _article_payload(article)
        slug = str(normalized["slug"])
        headers = {
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": f"{manifest.get('draft_id', slug)}:article:{request_hash[:32]}",
            "X-Content-SHA256": request_hash,
        }
        current = client.get(f"{base_url}/api/v1/content/articles/{slug}")
        if current.status_code == 200:
            headers["If-Match"] = str(current.json()["revision"])
        elif current.status_code != 404:
            current.raise_for_status()
        published = client.put(
            f"{base_url}/internal/seo-agent/articles/{slug}",
            headers=headers,
            json=normalized,
        )
        published.raise_for_status()
        public_url = f"{public_origin}/guide/{slug}"
        page = client.get(public_url)
        page.raise_for_status()
        sitemap = client.get(f"{public_origin}/sitemap.xml")
        sitemap.raise_for_status()
        feed = client.get(f"{public_origin}/feed/dzen.xml")
        feed.raise_for_status()
        cover_url = urljoin(f"{public_origin}/", str(normalized["cover_image_url"]))
        cover_response = client.get(cover_url)
        cover_response.raise_for_status()
    checks = {
        "canonical": str(page.url).rstrip("/") == public_url and f'<link rel="canonical" href="{public_url}"' in page.text,
        "article_schema": '"@type":"Article"' in page.text,
        "title": str(normalized["title"]) in page.text,
        "request_hash": f'<meta name="vedicway-article-request-sha256" content="{request_hash}"' in page.text,
        "sitemap": public_url in sitemap.text,
        "dzen_feed": public_url in feed.text and f"vedicway-request-sha256:{request_hash}" in feed.text,
        "cover": cover_response.headers.get("content-type", "").startswith("image/"),
    }
    if not all(checks.values()):
        raise LedgerError("Public verification failed: " + ", ".join(name for name, ok in checks.items() if not ok))
    return {
        **preview,
        "request_hash": request_hash,
        "draft_content_hash": manifest.get("content_hash"),
        "public_url": public_url,
        "article": published.json()["article"],
        "uploaded_media": [
            {"id": item["asset"]["id"], "url": item["asset"]["url"], "sha256": item["sha256"]}
            for item in uploaded
        ],
        "evidence": {
            "checks": checks,
            "page_sha256": hashlib.sha256(page.content).hexdigest(),
            "sitemap_sha256": hashlib.sha256(sitemap.content).hexdigest(),
            "dzen_feed_sha256": hashlib.sha256(feed.content).hexdigest(),
        },
        "manifest_hash": hashlib.sha256(canonical_json(manifest).encode("utf-8")).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish one approved VedicWay SEO article")
    parser.add_argument("manifest")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(publish_bundle(args.manifest, dry_run=args.dry_run), ensure_ascii=False, sort_keys=True))
        return 0
    except (LedgerError, OSError, ValueError, json.JSONDecodeError, httpx.HTTPError) as error:
        print(json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
