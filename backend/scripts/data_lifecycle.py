from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from vedicway_backend.retention import RetentionSettings, run_lifecycle  # noqa: E402
from vedicway_backend.store import Store  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="VedicWay retention and erasure lifecycle")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()
    result = run_lifecycle(Store(), RetentionSettings.from_environment(), apply=arguments.apply)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
