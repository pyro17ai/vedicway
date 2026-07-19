from __future__ import annotations

import argparse
import json

from .store import Store


def main() -> None:
    parser = argparse.ArgumentParser(description="VedicWay personal-data erasure operations")
    subcommands = parser.add_subparsers(dest="command", required=True)
    erase = subcommands.add_parser("erase-chart")
    erase.add_argument("chart_id")
    erase.add_argument("--confirm", required=True, help="Repeat chart_id to confirm")
    cleanup = subcommands.add_parser("cleanup-unpaid")
    cleanup.add_argument("--older-than-days", type=int, default=30)
    arguments = parser.parse_args()

    store = Store()
    if arguments.command == "erase-chart":
        if arguments.confirm != arguments.chart_id:
            parser.error("--confirm must exactly match chart_id")
        print(json.dumps(store.erase_chart_personal_data(arguments.chart_id), ensure_ascii=False))
        return
    removed = store.erase_expired_unpaid_charts(older_than_days=arguments.older_than_days)
    print(json.dumps({"erased_unpaid_charts": removed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
