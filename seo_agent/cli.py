from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import psycopg

from .db import AgentLedger, LedgerError


def emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def default_claim_lease_seconds() -> int:
    try:
        timeout = int(os.environ.get("VEDICWAY_SEO_JOB_TIMEOUT_SECONDS", "3600"))
    except ValueError:
        timeout = 3600
    return min(86_400, max(30, timeout + 300))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="VedicWay SEO ledger CLI")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    commands.add_parser("health")
    commands.add_parser("status")
    start = commands.add_parser("start-run")
    start.add_argument("--job", required=True)
    start.add_argument("--schedule-token", required=True)
    heartbeat = commands.add_parser("heartbeat")
    heartbeat.add_argument("--run-id", required=True)
    heartbeat.add_argument("--owner-token", required=True)
    result = commands.add_parser("record-result")
    result.add_argument("--run-id", required=True)
    result.add_argument("--outcome", choices=("completed", "blocked", "skipped"), required=True)
    result.add_argument("--summary", required=True)
    result.add_argument("--artifact-json", default="{}")
    finish = commands.add_parser("finish-run")
    finish.add_argument("--run-id", required=True)
    finish.add_argument("--owner-token", required=True)
    finish.add_argument("--failed-error")
    claim = commands.add_parser("claim")
    claim.add_argument("entity", choices=("cluster", "draft", "action"))
    claim.add_argument("--lease-seconds", type=int, default=default_claim_lease_seconds())
    write = commands.add_parser("write")
    write.add_argument(
        "record_type",
        choices=(
            "source-document", "tool-response", "query", "cluster", "brief", "draft",
            "serp-snapshot",
            "draft-quality", "media", "publication-attempt", "publication",
            "performance", "action",
            "action-result",
        ),
    )
    write.add_argument("--json-file", type=Path)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    ledger = AgentLedger()
    try:
        if args.command == "init":
            emit({"applied": ledger.initialize(), "health": ledger.health()})
        elif args.command == "health":
            emit(ledger.health())
        elif args.command == "status":
            emit(ledger.summary())
        elif args.command == "start-run":
            emit(ledger.start_run(args.job, args.schedule_token))
        elif args.command == "heartbeat":
            ledger.heartbeat(args.run_id, args.owner_token)
            emit({"status": "ok"})
        elif args.command == "record-result":
            emit({"result_id": ledger.record_result(args.run_id, args.outcome, args.summary, json.loads(args.artifact_json))})
        elif args.command == "finish-run":
            emit({"status": ledger.finish_run(args.run_id, args.owner_token, failed_error=args.failed_error)})
        elif args.command == "claim":
            emit({"item": ledger.claim(args.entity, lease_seconds=args.lease_seconds)})
        elif args.command == "write":
            raw = args.json_file.read_text(encoding="utf-8") if args.json_file else input()
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise LedgerError("Record payload must be a JSON object")
            emit(ledger.write_record(args.record_type, payload))
        return 0
    except (LedgerError, OSError, psycopg.Error, ValueError, json.JSONDecodeError) as error:
        emit({"status": "error", "error": str(error)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
