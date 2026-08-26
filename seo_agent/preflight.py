from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .db import AgentLedger, LedgerError


def check(*, online: bool = False) -> dict[str, object]:
    errors: list[str] = []
    warnings: list[str] = []
    host_id = os.environ.get("VEDICWAY_YANDEX_HOST_ID", "").strip()
    counter_id = os.environ.get("VEDICWAY_METRIKA_COUNTER_ID", "").strip()
    if not host_id:
        errors.append("VEDICWAY_YANDEX_HOST_ID is missing")
    elif not (host_id.startswith("http:") or host_id.startswith("https:")):
        warnings.append(
            "Webmaster host_id is not URL-shaped; verify the exact ID returned by list_hosts"
        )
    if not re.fullmatch(r"\d+", counter_id):
        errors.append("VEDICWAY_METRIKA_COUNTER_ID must be numeric")
    origin = os.environ.get("VEDICWAY_PUBLIC_ORIGIN", "").rstrip("/")
    if urlsplit(origin).scheme != "https" or not urlsplit(origin).hostname:
        errors.append("VEDICWAY_PUBLIC_ORIGIN must be an absolute HTTPS origin")
    secret_names = (
        "VEDICWAY_SEO_AGENT_TOKEN",
        "VEDICWAY_YANDEX_SEARCH_API_KEY",
        "VEDICWAY_YANDEX_FOLDER_ID",
        "VEDICWAY_YANDEX_WEBMASTER_TOKEN",
        "VEDICWAY_YANDEX_METRIKA_TOKEN",
    )
    missing_secrets = [name for name in secret_names if not os.environ.get(name)]
    errors.extend(f"{name} is missing" for name in missing_secrets)
    codex_home = Path(os.environ.get("CODEX_HOME", "")).expanduser()
    if not (codex_home / "auth.json").is_file():
        errors.append("Codex authentication is missing")
    if not (codex_home / "skills" / ".system" / "imagegen" / "SKILL.md").is_file():
        errors.append("Built-in Codex imagegen skill is missing")
    ledger_status: dict[str, object]
    try:
        ledger = AgentLedger()
        ledger.initialize()
        ledger_status = ledger.health()
        if ledger_status["status"] != "ok":
            errors.append("SEO ledger integrity failed")
    except (LedgerError, OSError) as error:
        ledger_status = {"status": "failed", "error": str(error)}
        errors.append(f"SEO ledger failed: {error}")
    site_status: dict[str, object] = {"status": "not_checked"}
    if (
        online
        and not missing_secrets
        and not any("PUBLIC_ORIGIN" in item for item in errors)
    ):
        base = os.environ.get(
            "VEDICWAY_SEO_AGENT_BASE_URL", "http://backend:8000"
        ).rstrip("/")
        try:
            response = httpx.get(
                f"{base}/internal/content-agent/health",
                headers={
                    "Authorization": f"Bearer {os.environ['VEDICWAY_SEO_AGENT_TOKEN']}"
                },
                timeout=10,
            )
            response.raise_for_status()
            site_status = response.json()
        except (httpx.HTTPError, ValueError) as error:
            errors.append(f"Site publication API failed: {error}")
            site_status = {"status": "failed", "error": str(error)}
    return {
        "status": "ready" if not errors else "blocked",
        "errors": errors,
        "warnings": warnings,
        "ledger": ledger_status,
        "site_api": site_status,
        "identity_guard": {
            "webmaster_host_id": host_id or None,
            "metrika_counter_id": counter_id or None,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="VedicWay SEO production preflight")
    parser.add_argument("--online", action="store_true")
    args = parser.parse_args()
    result = check(online=args.online)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
