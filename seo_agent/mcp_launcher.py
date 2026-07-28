from __future__ import annotations

import argparse
import os
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path

from .db import LedgerError

MCP_CONTRACTS = {
    "search": (
        "yandex-search-mcp/src/index.mjs",
        {
            "YANDEX_SEARCH_API_KEY": "VEDICWAY_YANDEX_SEARCH_API_KEY",
            "YANDEX_FOLDER_ID": "VEDICWAY_YANDEX_FOLDER_ID",
        },
    ),
    "wordstat": (
        "yandex-wordstat-mcp/src/index.mjs",
        {
            "YANDEX_SEARCH_API_KEY": "VEDICWAY_YANDEX_SEARCH_API_KEY",
            "YANDEX_FOLDER_ID": "VEDICWAY_YANDEX_FOLDER_ID",
        },
    ),
    "webmaster": (
        "yandex-webmaster-mcp/src/index.mjs",
        {"YANDEX_WEBMASTER_TOKEN": "VEDICWAY_YANDEX_WEBMASTER_TOKEN"},
    ),
    "metrika": (
        "yandex-metrika-mcp/src/index.mjs",
        {"YANDEX_METRIKA_TOKEN": "VEDICWAY_YANDEX_METRIKA_TOKEN"},
    ),
}


def isolated_environment(target: str, source: Mapping[str, str]) -> dict[str, str]:
    if target not in MCP_CONTRACTS:
        raise LedgerError(f"Unsupported Yandex MCP target: {target}")
    _, mapping = MCP_CONTRACTS[target]
    missing = [source_name for source_name in mapping.values() if not source.get(source_name)]
    if missing:
        raise LedgerError("Missing VedicWay-only MCP variables: " + ", ".join(missing))
    clean = {
        key: value
        for key, value in source.items()
        if not key.startswith("YANDEX_") and not key.startswith("VEDICWAY_YANDEX_")
    }
    for destination, source_name in mapping.items():
        clean[destination] = source[source_name]
    return clean


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Launch one Yandex MCP with isolated VedicWay credentials")
    parser.add_argument("target", choices=tuple(MCP_CONTRACTS))
    args = parser.parse_args(argv)
    try:
        entrypoint, _ = MCP_CONTRACTS[args.target]
        script = Path(__file__).with_name("mcp") / "node_modules" / entrypoint
        node = shutil.which("node")
        if not node or not script.is_file():
            raise LedgerError("Pinned Node runtime or Yandex MCP package is missing")
        environment = isolated_environment(args.target, os.environ)
        os.execve(node, [node, str(script)], environment)
    except (LedgerError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 78
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
