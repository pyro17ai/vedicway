from __future__ import annotations

import io
import json

from seo_agent.browser_mcp_launcher import resolve_browser_ws_endpoint


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()


def test_resolver_keeps_the_private_service_and_uses_chromiums_websocket_path() -> None:
    observed: dict[str, object] = {}

    def open_version(url: str, *, timeout: float):
        observed.update(url=url, timeout=timeout)
        return _Response(
            json.dumps(
                {
                    "Browser": "Chrome/140",
                    "webSocketDebuggerUrl": (
                        "ws://127.0.0.1:9225/devtools/browser/browser-session-id"
                    ),
                }
            ).encode("utf-8")
        )

    resolved = resolve_browser_ws_endpoint(
        "pinterest",
        "http://vedicway-seo-browser-pinterest:9325",
        opener=open_version,
    )

    assert observed == {
        "url": "http://vedicway-seo-browser-pinterest:9325/json/version",
        "timeout": 15.0,
    }
    assert resolved == (
        "ws://vedicway-seo-browser-pinterest:9325/"
        "devtools/browser/browser-session-id"
    )
