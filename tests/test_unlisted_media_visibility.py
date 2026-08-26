from pathlib import Path
import hashlib
import json
import sys
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend" / "src"))

from vedicway_backend import content_store  # noqa: E402
from seo_agent.site_client import _media_request_hash  # noqa: E402


def test_public_unlisted_media_does_not_require_an_article_reference() -> None:
    policy = getattr(content_store, "_media_is_public", None)
    assert policy is not None, "media visibility policy is missing"
    asset = SimpleNamespace(
        id="11111111-1111-4111-8111-111111111111",
        public_url=(
            "/media/articles/11111111-1111-4111-8111-111111111111/1000.webp"
        ),
        sources=[],
        public_unlisted=True,
    )

    assert policy(asset, "1000.webp", []) is True


def test_regular_unreferenced_media_stays_private() -> None:
    policy = getattr(content_store, "_media_is_public", None)
    assert policy is not None, "media visibility policy is missing"
    asset = SimpleNamespace(
        id="22222222-2222-4222-8222-222222222222",
        public_url=(
            "/media/articles/22222222-2222-4222-8222-222222222222/1000.webp"
        ),
        sources=[],
        public_unlisted=False,
    )

    assert policy(asset, "1000.webp", []) is False


def test_pinterest_visibility_is_bound_to_the_media_idempotency_hash() -> None:
    media = {
        "purpose": "body",
        "alt_text": "Памятка по чтению домов",
        "title": "",
        "caption": "",
    }

    regular = _media_request_hash(media, "a" * 64)
    pinterest = _media_request_hash(
        {**media, "distribution_role": "pinterest"},
        "a" * 64,
    )

    assert regular != pinterest


def test_regular_media_keeps_its_existing_idempotency_hash() -> None:
    media = {
        "purpose": "body",
        "alt_text": "Схема чтения домов",
        "title": "",
        "caption": "",
    }
    expected = hashlib.sha256(
        json.dumps(
            {
                "content_sha256": "b" * 64,
                "purpose": "body",
                "alt": "Схема чтения домов",
                "title": "",
                "caption": "",
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    assert _media_request_hash(media, "b" * 64) == expected
