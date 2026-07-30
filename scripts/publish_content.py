from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend" / "src"))

from vedicway_backend.content_api import (  # noqa: E402
    ContentArticlePayload,
    _content_payload_hash,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Publish one raw HTML article through the VedicWay Codex gate"
    )
    parser.add_argument("metadata", type=Path)
    parser.add_argument("html", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--base-url",
        default=os.environ.get(
            "VEDICWAY_SEO_AGENT_BASE_URL",
            "http://127.0.0.1:8000",
        ),
    )
    args = parser.parse_args()

    metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise SystemExit("Metadata file must contain one JSON object")
    metadata["content_html"] = args.html.read_text(encoding="utf-8").strip()
    payload = ContentArticlePayload.model_validate(metadata)
    digest = _content_payload_hash(payload)
    section = payload.section
    slug = payload.slug
    public_origin = (
        os.environ.get("VEDICWAY_PUBLIC_ORIGIN") or "https://vedicway.ru"
    ).rstrip("/")

    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "valid",
                    "section": section,
                    "slug": slug,
                    "content_sha256": digest,
                    "public_url": f"{public_origin}/{section}/{slug}",
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0

    token = os.environ.get("VEDICWAY_SEO_AGENT_TOKEN", "")
    if len(token.encode("utf-8")) < 32:
        raise SystemExit("VEDICWAY_SEO_AGENT_TOKEN must contain at least 32 bytes")
    base_url = args.base_url.rstrip("/")
    authorization = {"Authorization": f"Bearer {token}"}
    headers = {
        **authorization,
        "Idempotency-Key": f"codex:{section}:{slug}:{digest[:32]}",
        "X-Content-SHA256": digest,
    }
    with httpx.Client(timeout=30) as client:
        health = client.get(
            f"{base_url}/internal/content-agent/health",
            headers=authorization,
        )
        health.raise_for_status()
        current = client.get(f"{base_url}/api/v1/content/{section}/articles/{slug}")
        if current.status_code == 200:
            headers["If-Match"] = str(current.json()["revision"])
        elif current.status_code != 404:
            current.raise_for_status()
        response = client.put(
            f"{base_url}/internal/content-agent/{section}/articles/{slug}",
            headers=headers,
            json=payload.model_dump(mode="json"),
        )
        response.raise_for_status()
        result = response.json()
    print(
        json.dumps(
            {
                "status": "published",
                "public_url": f"{public_origin}/{section}/{slug}",
                "revision": result["article"]["revision"],
                "idempotent_replay": result["idempotent_replay"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
