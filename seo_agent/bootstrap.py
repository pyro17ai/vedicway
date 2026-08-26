from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from .db import AgentLedger, LedgerError

CLUSTERS = {
    "что такое дома в натальной карте": {
        "slug": "doma-v-natalnoy-karte",
        "title": "Дома в натальной карте: что означают и как их читать",
        "intent": "informational",
        "priority_score": 72,
    },
    "что такое аспекты в натальной карте": {
        "slug": "aspekty-v-natalnoy-karte",
        "title": "Аспекты в натальной карте: виды и порядок чтения",
        "intent": "informational",
        "priority_score": 66,
    },
}


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bootstrap(repo_root: Path | None = None) -> dict[str, Any]:
    root = (repo_root or Path(__file__).resolve().parents[1]).resolve()
    demand = root / "seo" / "yandex" / "keyword-demand.csv"
    serp = root / "seo" / "yandex" / "serp-evidence.md"
    if not demand.is_file() or not serp.is_file():
        raise LedgerError("Tracked Yandex seed evidence is missing")
    ledger = AgentLedger()
    ledger.initialize()
    with demand.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    source_ids = [
        ledger.write_record(
            "source-document",
            {
                "source_kind": "repository",
                "source_key": path.relative_to(root).as_posix(),
                "checksum": _checksum(path),
                "status": "active",
                "payload": {"path": path.relative_to(root).as_posix(), "rows": rows if path == demand else None},
            },
        )["id"]
        for path in (demand, serp)
    ]
    queries: dict[str, str] = {}
    for row in rows:
        phrase = str(row.get("query", "")).strip()
        if not phrase:
            continue
        intent = row.get("intent") or None
        if intent == "navigation":
            intent = "navigational"
        observed_at = f"{row.get('checked_at', '1970-01-01')}T00:00:00.000Z"
        query = ledger.write_record(
            "query",
            {
                "phrase": phrase,
                "region_id": str(row.get("region_id", "225")),
                "source": "seed",
                "intent": intent,
                "metrics": {
                    "monthly_queries": int(row.get("monthly_queries") or 0),
                    "region_name": row.get("region_name"),
                    "original_source": row.get("source"),
                    "target_page": row.get("target_page"),
                    "decision": row.get("decision"),
                    "source_document_id": source_ids[0],
                },
                "observed_at": observed_at,
            },
        )
        queries[phrase.casefold()] = str(query["id"])
    clusters: list[str] = []
    for phrase, contract in CLUSTERS.items():
        query_id = queries.get(phrase.casefold())
        if not query_id:
            continue
        result = ledger.write_record(
            "cluster",
            {
                **contract,
                "status": "candidate",
                "rationale": "Tracked repository seed; promote only after fresh Wordstat and Yandex SERP evidence",
                "query_ids": [query_id],
                "primary_query_id": query_id,
            },
        )
        clusters.append(str(result["id"]))
    return {
        "source_documents": source_ids,
        "queries": len(queries),
        "candidate_clusters": clusters,
    }


def main() -> int:
    try:
        print(json.dumps(bootstrap(), ensure_ascii=False, sort_keys=True))
        return 0
    except (LedgerError, OSError, ValueError) as error:
        print(json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
