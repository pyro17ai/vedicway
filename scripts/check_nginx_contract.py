from __future__ import annotations

import argparse
from pathlib import Path

REQUIRED_ARTICLE_GUARD = (
    "proxy_pass http://vedicway_backend/internal/seo/guide/articles/$article_slug/page;",
    "proxy_pass http://vedicway_backend/internal/seo/blog/articles/$blog_article_slug/page;",
    "proxy_pass http://vedicway_backend/internal/seo/guide/page;",
    "proxy_pass http://vedicway_backend/internal/seo/blog/page;",
    "proxy_intercept_errors on;",
    "error_page 404 =404 /404.html;",
    "location = /assets/seo-entry.js {",
    "location = /assets/seo-entry.css {",
)

REQUIRED_DZEN_GUARD = (
    "location = /feed/dzen.xml {",
    "proxy_pass http://vedicway_backend/api/v1/seo/dzen.xml;",
    "error_page 502 503 504 =503 /50x.html;",
)

REQUIRED_METRIKA_CSP = (
    "script-src 'self' https://mc.yandex.ru https://mc.yandex.com https://yastatic.net;",
)

REQUIRED_RECOVERY_GUARD = (
    '~^/access/recovery/?(?:\\?|$) "noindex, nofollow, noarchive";',
    '~^/access/confirm/?(?:\\?|$) "noindex, nofollow, noarchive";',
    '~^/privacy/request/?(?:\\?|$) "noindex, nofollow, noarchive";',
    "location = /access/recovery {",
    "try_files /access/recovery/index.html =404;",
    "location = /access/confirm {",
    "try_files /access/confirm/index.html =404;",
    "location = /privacy/request {",
    "try_files /privacy/request/index.html =404;",
    "location ^~ /api/v1/magic-links/ {",
    "access_log off;",
    "map $request_uri $referrer_policy {",
    '~^/access/confirm/?(?:\\?|$) "no-referrer";',
)

REQUIRED_LEGAL_GUARD = tuple(
    f"location = /legal/{slug} {{ try_files /legal/{slug}/index.html =404; expires -1; }}"
    for slug in (
        "offer",
        "privacy",
        "personal-data-consent",
        "cookies",
    )
) + (
    '~^/legal/(?:offer|privacy|personal-data-consent|cookies)/?(?:\\?|$) "noindex, follow, noarchive";',
    "location = /legal/user-agreement { return 308 /legal/offer; }",
    "location = /legal/privacy-policy { return 308 /legal/privacy; }",
    "location ^~ /legal/ { return 404; }",
)

REQUIRED_TRUST_ROUTES = tuple(
    f"location = /{slug} {{ try_files /{slug}/index.html =404; expires -1; }}"
    for slug in ("about", "methodology", "editorial-policy", "report-example")
)

REQUIRED_RECTIFICATION_GUARD = (
    "map $request_uri $x_robots_tag {",
    '~^/rectification(?:/|\\?|$) "noindex, nofollow, noarchive";',
    """location ~ ^/rectification/[^/]+/?$ {
      try_files /rectification/index.html =404;
      expires -1;
    }""",
)

REQUIRED_CHART_GUARD = (
    '~^/chart(?:/|\\?|$) "noindex, nofollow, noarchive";',
    """location ~ ^/chart/[^/]+/?$ {
      try_files /chart/index.html =404;
      expires -1;
    }""",
)

REQUIRED_MANIFEST_GUARD = (
    "location = /site.webmanifest {",
    "default_type application/manifest+json;",
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate fail-closed Nginx SEO routes"
    )
    parser.add_argument("config", type=Path)
    args = parser.parse_args()
    config = args.config.read_text(encoding="utf-8")

    missing = [
        fragment for fragment in REQUIRED_ARTICLE_GUARD if fragment not in config
    ]
    if missing:
        raise SystemExit(f"Article SEO proxy is incomplete: {', '.join(missing)}")
    if "location ~ ^/guide/[^/]+/?$" in config:
        raise SystemExit(
            "Legacy guide SPA fallback still returns 200 for unknown article slugs"
        )
    if "location ~ ^/blog/[^/]+/?$" in config:
        raise SystemExit(
            "Legacy blog SPA fallback still returns 200 for unknown article slugs"
        )
    if "location ~ ^/admin" in config:
        raise SystemExit("Removed manual editor is still exposed by Nginx")
    missing_dzen = [
        fragment for fragment in REQUIRED_DZEN_GUARD if fragment not in config
    ]
    if missing_dzen:
        raise SystemExit(f"Dzen RSS proxy is incomplete: {', '.join(missing_dzen)}")
    missing_csp = [
        fragment for fragment in REQUIRED_METRIKA_CSP if fragment not in config
    ]
    if missing_csp:
        raise SystemExit(
            "Metrika external-mode CSP is incomplete: " + ", ".join(missing_csp)
        )
    missing_recovery = [
        fragment for fragment in REQUIRED_RECOVERY_GUARD if fragment not in config
    ]
    if missing_recovery:
        raise SystemExit(
            f"Recovery privacy guard is incomplete: {', '.join(missing_recovery)}"
        )
    missing_legal = [
        fragment for fragment in REQUIRED_LEGAL_GUARD if fragment not in config
    ]
    if missing_legal:
        raise SystemExit(f"Legal SEO routing is incomplete: {', '.join(missing_legal)}")
    missing_trust = [
        fragment for fragment in REQUIRED_TRUST_ROUTES if fragment not in config
    ]
    if missing_trust:
        raise SystemExit(f"Trust-page routing is incomplete: {', '.join(missing_trust)}")
    missing_rectification = [
        fragment
        for fragment in REQUIRED_RECTIFICATION_GUARD
        if fragment not in config
    ]
    if missing_rectification:
        raise SystemExit(
            "Rectification privacy guard is incomplete: "
            + ", ".join(missing_rectification)
        )
    missing_chart = [
        fragment
        for fragment in REQUIRED_CHART_GUARD
        if fragment not in config
    ]
    if missing_chart:
        raise SystemExit(
            "Chart privacy guard is incomplete: "
            + ", ".join(missing_chart)
        )
    missing_manifest = [
        fragment for fragment in REQUIRED_MANIFEST_GUARD if fragment not in config
    ]
    if missing_manifest:
        raise SystemExit(
            "Web manifest MIME guard is incomplete: " + ", ".join(missing_manifest)
        )
    if "try_files $uri $uri/index.html /index.html" in config:
        raise SystemExit("Legal SPA fallback still returns a soft 404")
    print("Nginx SEO, legal and privacy guard contract passed.")


if __name__ == "__main__":
    main()
