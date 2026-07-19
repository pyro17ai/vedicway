from __future__ import annotations

import argparse
from pathlib import Path

REQUIRED_ARTICLE_GUARD = (
    "proxy_pass http://vedicway_backend/internal/seo/articles/$article_slug/page;",
    "proxy_intercept_errors on;",
    "error_page 404 =404 /404.html;",
    "location = /assets/seo-entry.js {",
    "location = /assets/seo-entry.css {",
)

REQUIRED_METRIKA_CSP = (
    "script-src 'self' https://mc.yandex.ru https://mc.yandex.com https://yastatic.net;",
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate fail-closed Nginx SEO routes")
    parser.add_argument("config", type=Path)
    args = parser.parse_args()
    config = args.config.read_text(encoding="utf-8")

    missing = [fragment for fragment in REQUIRED_ARTICLE_GUARD if fragment not in config]
    if missing:
        raise SystemExit(f"Article SEO proxy is incomplete: {', '.join(missing)}")
    if "location ~ ^/guide/[^/]+/?$" in config:
        raise SystemExit("Legacy guide SPA fallback still returns 200 for unknown article slugs")
    missing_csp = [fragment for fragment in REQUIRED_METRIKA_CSP if fragment not in config]
    if missing_csp:
        raise SystemExit(
            "Metrika external-mode CSP is incomplete: " + ", ".join(missing_csp)
        )
    print("Nginx article SEO guard contract passed.")


if __name__ == "__main__":
    main()
