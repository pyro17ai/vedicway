from __future__ import annotations

import json
import os
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from urllib.request import urlopen

from .db import LedgerError

PLATFORMS = {
    "dzen": {
        "endpoint_env": "VEDICWAY_DZEN_CDP_URL",
        "default_endpoint": "http://vedicway-seo-browser-dzen:9322",
        "origins": (
            "https://dzen.ru;https://*.dzen.ru;https://*.dzeninfra.ru;"
            "https://yandex.ru;https://*.yandex.ru"
        ),
    },
    "pinterest": {
        "endpoint_env": "VEDICWAY_PINTEREST_CDP_URL",
        "default_endpoint": "http://vedicway-seo-browser-pinterest:9325",
        "origins": (
            "https://ru.pinterest.com;https://www.pinterest.com;"
            "https://*.pinterest.com;https://*.pinimg.com;https://vedicway.ru;"
            "https://pinterest-anaheim.s3.amazonaws.com"
        ),
    },
}


def _validate_private_endpoint(platform: str, endpoint: str) -> None:
    parsed = urlsplit(endpoint)
    expected_host = f"vedicway-seo-browser-{platform}"
    if (
        parsed.scheme not in {"http", "ws"}
        or parsed.hostname != expected_host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"} and not parsed.path.startswith("/devtools/browser/")
        or parsed.query
        or parsed.fragment
    ):
        raise LedgerError("Browser CDP endpoint must use the private VedicWay service")


def resolve_browser_ws_endpoint(
    platform: str,
    endpoint: str,
    *,
    opener: Callable[..., object] = urlopen,
) -> str:
    if platform not in PLATFORMS:
        raise LedgerError(f"Unsupported browser platform: {platform}")
    _validate_private_endpoint(platform, endpoint)
    parsed_endpoint = urlsplit(endpoint)
    if parsed_endpoint.scheme == "ws":
        return endpoint
    version_url = f"{endpoint.rstrip('/')}/json/version"
    try:
        with opener(version_url, timeout=15.0) as response:  # type: ignore[attr-defined]
            payload = json.load(response)
    except (OSError, ValueError, TypeError) as error:
        raise LedgerError(f"Browser CDP discovery failed: {error}") from error
    debugger_url = payload.get("webSocketDebuggerUrl") if isinstance(payload, dict) else None
    parsed_debugger = urlsplit(debugger_url) if isinstance(debugger_url, str) else None
    if (
        parsed_debugger is None
        or parsed_debugger.scheme not in {"ws", "wss"}
        or not parsed_debugger.path.startswith("/devtools/browser/")
    ):
        raise LedgerError("Browser CDP discovery returned no browser WebSocket endpoint")
    return urlunsplit(
        (
            "ws",
            parsed_endpoint.netloc,
            parsed_debugger.path,
            parsed_debugger.query,
            "",
        )
    )


def build_browser_mcp_command(
    platform: str,
    *,
    data_dir: Path,
    node: str,
    cli: Path,
    endpoint: str,
) -> tuple[list[str], Path]:
    if platform not in PLATFORMS:
        raise LedgerError(f"Unsupported browser platform: {platform}")
    _validate_private_endpoint(platform, endpoint)
    workspace = data_dir / "browser-input" / platform
    output = data_dir / "browser-output" / platform
    workspace.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    command = [
        node,
        str(cli),
        "--cdp-endpoint",
        endpoint,
        "--cdp-timeout",
        "15000",
        "--allowed-origins",
        str(PLATFORMS[platform]["origins"]),
        "--output-dir",
        str(output),
        "--output-max-size",
        "67108864",
        "--image-responses",
        "omit",
        "--codegen",
        "none",
        "--console-level",
        "warning",
        "--grant-permissions",
        "clipboard-read",
        "clipboard-write",
    ]
    return command, workspace


def main(argv: list[str] | None = None) -> int:
    arguments = list(argv if argv is not None else sys.argv[1:])
    if len(arguments) != 1 or arguments[0] not in PLATFORMS:
        print("Exactly one supported browser platform is required", file=sys.stderr)
        return 78
    platform = arguments[0]
    data_dir = Path(os.environ.get("VEDICWAY_SEO_DATA_DIR", "/var/lib/vedicway/seo-agent")).resolve()
    node = shutil.which("node")
    cli = Path(__file__).with_name("browser_runtime") / "node_modules" / "@playwright" / "mcp" / "cli.js"
    if not node or not cli.is_file():
        print("Pinned Playwright MCP runtime is missing", file=sys.stderr)
        return 78
    endpoint = os.environ.get(
        str(PLATFORMS[platform]["endpoint_env"]),
        str(PLATFORMS[platform]["default_endpoint"]),
    )
    try:
        endpoint = resolve_browser_ws_endpoint(platform, endpoint)
        command, cwd = build_browser_mcp_command(
            platform,
            data_dir=data_dir,
            node=node,
            cli=cli,
            endpoint=endpoint,
        )
        clean = {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "HOME", "LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR"}
        }
        os.chdir(cwd)
        os.execve(node, command, clean)
    except (LedgerError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 78
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
