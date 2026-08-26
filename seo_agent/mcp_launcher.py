from __future__ import annotations

import argparse
import os
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path

from .db import LedgerError

MCP_CONTRACTS = {
    "search": {
        "entrypoint": "yandex-search-mcp/src/index.mjs",
        "required": {
            "YANDEX_SEARCH_API_KEY": "VEDICWAY_YANDEX_SEARCH_API_KEY",
            "YANDEX_FOLDER_ID": "VEDICWAY_YANDEX_FOLDER_ID",
        },
    },
    "wordstat": {
        "entrypoint": "yandex-wordstat-mcp/src/index.mjs",
        "required": {
            "YANDEX_SEARCH_API_KEY": "VEDICWAY_YANDEX_SEARCH_API_KEY",
            "YANDEX_FOLDER_ID": "VEDICWAY_YANDEX_FOLDER_ID",
        },
    },
    "webmaster": {
        "entrypoint": "yandex-webmaster-mcp/src/index.mjs",
        "required": {"YANDEX_WEBMASTER_TOKEN": "VEDICWAY_YANDEX_WEBMASTER_TOKEN"},
    },
    "metrika": {
        "entrypoint": "yandex-metrika-mcp/src/index.mjs",
        "required": {"YANDEX_METRIKA_TOKEN": "VEDICWAY_YANDEX_METRIKA_TOKEN"},
    },
    "vk": {
        "entrypoint": "../packages/vk-group-mcp/src/index.js",
        "required": {
            "VK_GROUP_ID": "VEDICWAY_VK_GROUP_ID",
            "VK_GROUP_ACCESS_TOKEN": "VEDICWAY_VK_GROUP_ACCESS_TOKEN",
            "VK_USER_ACCESS_TOKEN": "VEDICWAY_VK_USER_ACCESS_TOKEN",
        },
    },
    "control": {
        "entrypoint": "../packages/agent-control-mcp/src/index.mjs",
        "required": {},
    },
}

CONTROL_ENVIRONMENT = {
    "PATH",
    "PYTHONPATH",
    "VIRTUAL_ENV",
    "HOME",
    "CODEX_HOME",
    "TMPDIR",
    "TEMP",
    "TMP",
    "LANG",
    "LC_ALL",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "VEDICWAY_SEO_DATABASE_URL",
    "DATABASE_URL",
    "VEDICWAY_DATABASE_URL",
    "VEDICWAY_SEO_DATA_DIR",
    "VEDICWAY_SEO_RUN_ID",
    "VEDICWAY_SEO_JOB_NAME",
    "VEDICWAY_PINTEREST_BOARD_NAME",
    "VEDICWAY_IMAGEGEN_RUN_STARTED_NS",
    "VEDICWAY_SEO_AGENT_TOKEN",
    "VEDICWAY_SEO_AGENT_BASE_URL",
    "VEDICWAY_PUBLIC_ORIGIN",
    "VEDICWAY_SEO_JOB_TIMEOUT_SECONDS",
}

def isolated_environment(target: str, source: Mapping[str, str]) -> dict[str, str]:
    if target not in MCP_CONTRACTS:
        raise LedgerError(f"Unsupported VedicWay MCP target: {target}")
    contract = MCP_CONTRACTS[target]
    if target == "control":
        return {key: value for key, value in source.items() if key in CONTROL_ENVIRONMENT}
    mapping = contract["required"]
    optional = contract.get("optional", {})
    missing = [source_name for source_name in mapping.values() if not source.get(source_name)]
    if missing:
        raise LedgerError("Missing VedicWay-only MCP variables: " + ", ".join(missing))
    clean = {
        key: value
        for key, value in source.items()
        if not key.startswith(
            (
                "YANDEX_", "VEDICWAY_YANDEX_", "VK_", "VEDICWAY_VK_",
                "PINTEREST_", "VEDICWAY_PINTEREST_", "OPENAI_",
            )
        )
    }
    for destination, source_name in mapping.items():
        clean[destination] = source[source_name]
    for destination, source_name in optional.items():
        if source.get(source_name):
            clean[destination] = source[source_name]
    return clean


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Launch one MCP with isolated VedicWay credentials")
    parser.add_argument("target", choices=tuple(MCP_CONTRACTS))
    args = parser.parse_args(argv)
    try:
        entrypoint = MCP_CONTRACTS[args.target]["entrypoint"]
        script = Path(__file__).with_name("mcp") / "node_modules" / entrypoint
        node = shutil.which("node")
        if not node or not script.is_file():
            raise LedgerError("Pinned Node runtime or VedicWay MCP package is missing")
        environment = isolated_environment(args.target, os.environ)
        if args.target == "control":
            environment["PYTHON_EXECUTABLE"] = sys.executable
        os.execve(node, [node, str(script)], environment)
    except (LedgerError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 78
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
