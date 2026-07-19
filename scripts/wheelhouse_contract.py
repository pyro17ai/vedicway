from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

MANIFEST_NAME = "SHA256SUMS"
PYJHORA_WHEEL = re.compile(r"pyjhora_mcp-0\.1\.0-[^/\\]+\.whl", re.IGNORECASE)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_wheelhouse(path: Path) -> list[str]:
    errors: list[str] = []
    manifest = path / MANIFEST_NAME
    if not manifest.is_file() or manifest.is_symlink():
        return [f"wheelhouse manifest is missing or unsafe: {manifest}"]

    entries: dict[str, str] = {}
    for raw in manifest.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?([^/\\]+)", raw.strip())
        if not match:
            errors.append("SHA256SUMS contains an invalid line")
            continue
        expected, filename = match.groups()
        if filename == MANIFEST_NAME or filename in entries:
            errors.append(f"SHA256SUMS contains a duplicate or reserved entry: {filename}")
            continue
        entries[filename] = expected.casefold()

    actual: set[str] = set()
    for item in path.iterdir():
        if item.name == MANIFEST_NAME:
            continue
        if not item.is_file() or item.is_symlink():
            errors.append(f"wheelhouse contains a non-regular entry: {item.name}")
            continue
        actual.add(item.name)

    listed = set(entries)
    for filename in sorted(listed - actual):
        errors.append(f"wheel listed in SHA256SUMS is missing: {filename}")
    for filename in sorted(actual - listed):
        errors.append(f"wheelhouse file is not listed in SHA256SUMS: {filename}")
    for filename in sorted(actual & listed):
        if _sha256(path / filename).casefold() != entries[filename]:
            errors.append(f"wheel checksum mismatch: {filename}")

    if not any(PYJHORA_WHEEL.fullmatch(filename) for filename in listed):
        errors.append("SHA256SUMS must list pyjhora_mcp 0.1.0")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate an exact, checksummed wheelhouse")
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    errors = validate_wheelhouse(args.path.resolve())
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Wheelhouse exact-set contract passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
