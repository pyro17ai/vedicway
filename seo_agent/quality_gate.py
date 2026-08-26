from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .db import AgentLedger, LedgerError
from .markdown_renderer import render_markdown

BANNED_PATTERNS = {
    "guaranteed_prediction": re.compile(
        r"\b(?:гарантирует|точно предсказывает|неизбежно произойд[её]т)\b",
        re.IGNORECASE,
    ),
    "medical_claim": re.compile(
        r"\b(?:лечит|диагностирует|заменяет врача|медицинский диагноз)\b", re.IGNORECASE
    ),
    "filler_heading": re.compile(
        r"<h[23][^>]*>\s*(?:заключение|подводя итоги|важно понимать)\s*</h[23]>",
        re.IGNORECASE,
    ),
}

RUSSIAN_SUFFIXES = (
    "иями",
    "ями",
    "ами",
    "его",
    "ого",
    "ему",
    "ому",
    "ую",
    "юю",
    "ая",
    "яя",
    "ое",
    "ее",
    "ые",
    "ие",
    "ой",
    "ей",
    "ым",
    "им",
    "ых",
    "их",
    "а",
    "я",
    "у",
    "ю",
    "ы",
    "и",
    "е",
    "о",
)


def _search_words(value: str) -> list[str]:
    words = re.findall(r"[а-яёa-z0-9-]+", value.casefold())
    normalized: list[str] = []
    for word in words:
        if re.fullmatch(r"[а-яё]+", word):
            for suffix in RUSSIAN_SUFFIXES:
                if word.endswith(suffix) and len(word) - len(suffix) >= 3:
                    word = word[: -len(suffix)]
                    break
        normalized.append(word)
    return normalized


def _phrase_hits(words: list[str], phrase: list[str]) -> int:
    if not phrase:
        return 0
    return sum(
        1
        for index in range(len(words))
        if words[index : index + len(phrase)] == phrase
    )


def evaluate(manifest: dict[str, Any]) -> dict[str, Any]:
    article = manifest.get("article")
    media = manifest.get("media")
    if not isinstance(article, dict) or not isinstance(media, list):
        raise LedgerError("Manifest must contain article and media")
    source_content = str(
        article.get("content_markdown", article.get("content_html", ""))
    ).strip()
    content = (
        render_markdown(source_content)
        if "content_markdown" in article
        else source_content
    )
    title = str(article.get("title", "")).strip()
    meta = str(article.get("meta_description", "")).strip()
    excerpt = str(article.get("excerpt", "")).strip()
    focus = str(article.get("focus_keyphrase", "")).strip().casefold()
    plain_text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", content)).strip()
    paragraphs = [
        re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip()
        for value in re.findall(
            r"<p\b[^>]*>(.*?)</p>", content, re.IGNORECASE | re.DOTALL
        )
    ]
    normalized = [value.casefold() for value in paragraphs if value]
    repeated = [
        text
        for text, count in Counter(normalized).items()
        if count > 1 and len(text) > 80
    ]
    links = re.findall(r'<a\b[^>]*\bhref=["\']([^"\']+)["\']', content, re.IGNORECASE)
    internal_links = [
        value for value in links if value.startswith("/") and not value.startswith("//")
    ]
    source_links = [
        value for value in links if value.startswith(("http://", "https://"))
    ]
    words = _search_words(plain_text)
    focus_words = _search_words(focus)
    focus_hits = _phrase_hits(words, focus_words)
    density = focus_hits * max(1, len(focus_words)) / max(1, len(words))
    checks = {
        "content_min_4500": len(plain_text) >= 4500,
        "content_max_30000": len(plain_text) <= 30000,
        "title_length": 35 <= len(title) <= 100,
        "seo_title_length": 30 <= len(str(article.get("seo_title", ""))) <= 80,
        "meta_length": 80 <= len(meta) <= 200,
        "excerpt_length": 80 <= len(excerpt) <= 300,
        "focus_in_title": _phrase_hits(_search_words(title), focus_words) > 0,
        "focus_in_opening": _phrase_hits(
            _search_words(plain_text[:700]), focus_words
        )
        > 0,
        "focus_density_below_3_percent": density <= 0.03,
        "heading_count": len(re.findall(r"<h2\b", content, re.IGNORECASE)) >= 3,
        "internal_links": len(set(internal_links)) >= 2,
        "cta_owned_by_site": "data-content-cta" not in content,
        "source_links": len(set(source_links)) >= 2,
        "no_repeated_paragraphs": not repeated,
        "one_cover": sum(
            item.get("purpose") == "cover" for item in media if isinstance(item, dict)
        )
        == 1,
        "media_attribution": all(
            isinstance(item, dict)
            and item.get("alt_text")
            and item.get("source_kind") in {"generated", "licensed", "owned"}
            and item.get("license_note")
            for item in media
        ),
    }
    violations = [
        name for name, pattern in BANNED_PATTERNS.items() if pattern.search(content)
    ]
    checks["prohibited_claims"] = not violations
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "passed": not failed,
        "checks": checks,
        "failed": failed,
        "violations": violations,
        "metrics": {
            "characters": len(plain_text),
            "words": len(words),
            "headings_h2": len(re.findall(r"<h2\b", content, re.IGNORECASE)),
            "internal_links": len(set(internal_links)),
            "source_links": len(set(source_links)),
            "focus_density": round(density, 5),
            "repeated_paragraphs": len(repeated),
        },
        "content_hash": hashlib.sha256(source_content.encode("utf-8")).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic VedicWay SEO article quality gate"
    )
    parser.add_argument("manifest")
    args = parser.parse_args()
    ledger = AgentLedger()
    try:
        path = Path(args.manifest).expanduser().resolve()
        path.relative_to(ledger.data_dir)
        report = evaluate(json.loads(path.read_text(encoding="utf-8")))
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0 if report["passed"] else 1
    except (LedgerError, OSError, ValueError, json.JSONDecodeError) as error:
        print(
            json.dumps(
                {"passed": False, "error": str(error)},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
