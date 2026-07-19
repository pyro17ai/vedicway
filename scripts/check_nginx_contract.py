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

REQUIRED_RECOVERY_GUARD = (
    '~^/access/recovery/?$ "noindex, nofollow, noarchive";',
    '~^/privacy/request/?$ "noindex, nofollow, noarchive";',
    "location = /access/recovery {",
    "try_files /access/recovery/index.html =404;",
    "location = /privacy/request {",
    "try_files /privacy/request/index.html =404;",
    "location ^~ /api/v1/magic-links/ {",
    "access_log off;",
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
    missing_recovery = [fragment for fragment in REQUIRED_RECOVERY_GUARD if fragment not in config]
    if missing_recovery:
        raise SystemExit(f"Recovery privacy guard is incomplete: {', '.join(missing_recovery)}")
    print("Nginx SEO and privacy guard contract passed.")


if __name__ == "__main__":
    main()
