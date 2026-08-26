from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import shutil
import sys
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from PIL import Image, ImageOps

from .db import AgentLedger, LedgerError
from .site_client import publish_bundle

CLAIM_ENTITIES = {
    "cluster",
    "draft",
    "dzen-article",
    "action",
    "vk-post",
    "pinterest-pin",
}
RECORD_TYPES = {
    "source-document",
    "tool-response",
    "query",
    "cluster",
    "brief",
    "draft",
    "serp-snapshot",
    "draft-quality",
    "media",
    "publication-attempt",
    "publication",
    "performance",
    "action",
    "action-result",
    "distribution-item",
    "distribution-attempt",
    "distribution-publication",
}
ALLOWED_ACTIONS = {
    "ledger-health",
    "ledger-due-lifecycle",
    "ledger-claim",
    "ledger-claim-pinterest-batch",
    "ledger-write",
    "build-pinterest-csv",
    "stage-dzen-media",
    "import-generated-image",
    "record-run-log",
    "record-result",
    "publish-site",
}

GENERATED_IMAGE_KINDS = {
    "article-cover": (1200, 630),
    "pinterest-card": (1000, 1500),
}
GENERATED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
MOSCOW = ZoneInfo("Europe/Moscow")


def _keys(
    payload: dict[str, Any],
    *,
    allowed: set[str],
    required: set[str] = frozenset(),
) -> None:
    unknown = set(payload).difference(allowed)
    missing = required.difference(payload)
    if unknown:
        raise LedgerError("Unsupported control fields: " + ", ".join(sorted(unknown)))
    if missing:
        raise LedgerError("Missing control fields: " + ", ".join(sorted(missing)))


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LedgerError(f"{name} must be a JSON object")
    return value


def _seo_data_dir() -> Path:
    return Path(
        os.environ.get("VEDICWAY_SEO_DATA_DIR", "/var/lib/vedicway/seo-agent")
    ).expanduser().resolve()


def _latest_unimported_generated_image(generated_root: Path, data_dir: Path) -> Path:
    run_id = os.environ.get("VEDICWAY_SEO_RUN_ID", "").strip()
    started_ns_raw = os.environ.get("VEDICWAY_IMAGEGEN_RUN_STARTED_NS", "").strip()
    if not run_id or not started_ns_raw:
        raise LedgerError(
            "Current run metadata is required when Image Gen does not return a source path"
        )
    try:
        started_ns = int(started_ns_raw)
    except ValueError as exc:
        raise LedgerError("Invalid Image Gen run start timestamp") from exc

    state_name = hashlib.sha256(run_id.encode("utf-8")).hexdigest() + ".json"
    state_path = data_dir / "runtime" / "imagegen-imports" / state_name
    consumed: set[str] = set()
    if state_path.is_file():
        try:
            stored = json.loads(state_path.read_text(encoding="utf-8"))
            consumed = {str(item) for item in stored.get("sources", [])}
        except (OSError, ValueError, AttributeError) as exc:
            raise LedgerError("Image Gen import state is unreadable") from exc

    candidates: list[tuple[int, Path]] = []
    if generated_root.is_dir():
        for candidate in generated_root.rglob("*"):
            if not candidate.is_file() or candidate.suffix.casefold() not in GENERATED_IMAGE_SUFFIXES:
                continue
            resolved = candidate.resolve()
            if str(resolved) in consumed:
                continue
            try:
                modified_ns = resolved.stat().st_mtime_ns
            except OSError:
                continue
            if modified_ns >= started_ns:
                candidates.append((modified_ns, resolved))
    if not candidates:
        raise LedgerError("No unimported Image Gen artifact exists for the current run")
    candidates.sort(key=lambda item: (item[0], str(item[1])), reverse=True)
    return candidates[0][1]


def _mark_generated_image_imported(source: Path, data_dir: Path) -> None:
    run_id = os.environ.get("VEDICWAY_SEO_RUN_ID", "").strip()
    if not run_id:
        return
    state_name = hashlib.sha256(run_id.encode("utf-8")).hexdigest() + ".json"
    state_path = data_dir / "runtime" / "imagegen-imports" / state_name
    sources: list[str] = []
    if state_path.is_file():
        try:
            stored = json.loads(state_path.read_text(encoding="utf-8"))
            sources = [str(item) for item in stored.get("sources", [])]
        except (OSError, ValueError, AttributeError) as exc:
            raise LedgerError("Image Gen import state is unreadable") from exc
    if str(source) not in sources:
        sources.append(str(source))
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = state_path.with_name(f".{state_path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps({"sources": sources}), encoding="utf-8")
    temporary.replace(state_path)


def _import_generated_image(payload: dict[str, Any]) -> dict[str, Any]:
    _keys(
        payload,
        allowed={"source_path", "kind", "output"},
        required={"kind", "output"},
    )
    kind = str(payload["kind"])
    if kind not in GENERATED_IMAGE_KINDS:
        raise LedgerError("Unsupported generated image kind")

    codex_home_raw = os.environ.get("CODEX_HOME", "").strip()
    if not codex_home_raw:
        raise LedgerError("CODEX_HOME is required to import generated images")
    generated_root = (Path(codex_home_raw).expanduser().resolve() / "generated_images").resolve()
    data_dir = _seo_data_dir()
    source_path = str(payload.get("source_path", "")).strip()
    source = (
        Path(source_path).expanduser().resolve()
        if source_path
        else _latest_unimported_generated_image(generated_root, data_dir)
    )
    try:
        source.relative_to(generated_root)
    except ValueError as exc:
        raise LedgerError("Image source must stay inside CODEX_HOME/generated_images") from exc
    if not source.is_file() or source.suffix.casefold() not in GENERATED_IMAGE_SUFFIXES:
        raise LedgerError("Generated image source is missing or unsupported")

    relative = Path(str(payload["output"]))
    if relative.is_absolute() or relative.suffix.casefold() != ".webp":
        raise LedgerError("Imported image output must be a relative .webp path")
    target = (data_dir / relative).resolve()
    try:
        target.relative_to(data_dir)
    except ValueError as exc:
        raise LedgerError("Imported image output must stay inside the SEO data directory") from exc
    if target.exists():
        raise LedgerError(
            "Imported image output already exists; choose a unique output path"
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    final_size = GENERATED_IMAGE_KINDS[kind]
    try:
        with Image.open(source) as image:
            rendered = ImageOps.fit(
                image.convert("RGB"), final_size, Image.Resampling.LANCZOS
            )
            rendered.save(temporary, "WEBP", quality=90, method=6)
        temporary.replace(target)
    except (OSError, ValueError) as exc:
        temporary.unlink(missing_ok=True)
        raise LedgerError("Generated image could not be imported") from exc

    raw = target.read_bytes()
    if not source_path:
        _mark_generated_image_imported(source, data_dir)
    return {
        "path": str(target),
        "source_path": str(source),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "width": final_size[0],
        "height": final_size[1],
        "generator": "codex-imagegen",
        "kind": kind,
    }


def _render_pinterest_csv(
    items: list[dict[str, Any]], board: str, *, now: datetime
) -> bytes:
    if len(items) != 10:
        raise LedgerError("Pinterest CSV requires exactly 10 claimed items")
    local_now = now.astimezone(MOSCOW)
    publish_day = local_now.date()
    if local_now.time() >= time(13, 0):
        publish_day += timedelta(days=1)
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        [
            "Title",
            "Media URL",
            "Pinterest board",
            "Thumbnail",
            "Description",
            "Link",
            "Publish date",
            "Keywords",
        ]
    )
    seen_media: set[str] = set()
    for index, item in enumerate(items):
        media_url = str(item["media_public_url"])
        if media_url in seen_media:
            raise LedgerError("Pinterest CSV media URLs must be unique")
        seen_media.add(media_url)
        slot = datetime.combine(
            publish_day, time(13 + index, 0), tzinfo=MOSCOW
        ).isoformat(timespec="seconds")
        writer.writerow(
            [
                str(item["title"]),
                media_url,
                board,
                "",
                str(item["body"]),
                str(item["target_url"]),
                slot,
                "астрология, натальная карта, VedicWay",
            ]
        )
    return output.getvalue().encode("utf-8-sig")


def _build_pinterest_csv(ledger: AgentLedger) -> dict[str, Any]:
    run_id = os.environ.get("VEDICWAY_SEO_RUN_ID", "").strip()
    board = os.environ.get("VEDICWAY_PINTEREST_BOARD_NAME", "").strip()
    if not run_id or not board:
        raise LedgerError("Pinterest run ID and board name are required")
    with ledger.connect() as connection:
        run = connection.execute(
            "SELECT job_name FROM cron_runs WHERE id=%s AND status='running'",
            (run_id,),
        ).fetchone()
        if not run or str(run["job_name"]) != "pinterest_daily_publish":
            raise LedgerError("Only pinterest_daily_publish may build Pinterest CSV")
        rows = connection.execute(
            """SELECT id,title,body,target_url,media_public_url,media_width,
            media_height,content_hash,claim_token,claim_expires_at
            FROM distribution_items
            WHERE claim_run_id=%s AND platform='pinterest' AND status='publishing'
            ORDER BY created_at,id""",
            (run_id,),
        ).fetchall()
    items = [dict(row) for row in rows]
    if any(
        (int(item["media_width"]), int(item["media_height"])) != (1000, 1500)
        or not str(item["media_public_url"]).startswith(
            "https://vedicway.ru/media/articles/"
        )
        or not str(item["target_url"]).startswith("https://vedicway.ru/blog/")
        or not item["claim_token"]
        for item in items
    ):
        raise LedgerError("Claimed Pinterest items do not satisfy the CSV contract")
    content = _render_pinterest_csv(items, board, now=datetime.now(UTC))
    digest = hashlib.sha256(content).hexdigest()
    item_ids = [str(item["id"]) for item in items]
    with ledger.connect() as connection:
        previous_failed = int(
            connection.execute(
                """SELECT COUNT(DISTINCT item_id) AS count
                FROM distribution_attempts
                WHERE item_id=ANY(%s) AND request_hash=%s AND status='failed'""",
                (item_ids, digest),
            ).fetchone()["count"]
        )
    workspace = ledger.data_dir / "browser-input" / "pinterest"
    workspace.mkdir(parents=True, exist_ok=True)
    filename = f"vedicway-pins-{hashlib.sha256(run_id.encode()).hexdigest()[:16]}.csv"
    target = workspace / filename
    if target.exists() and target.read_bytes() != content:
        raise LedgerError("Pinterest CSV output already exists with different bytes")
    if not target.exists():
        temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        temporary.write_bytes(content)
        temporary.replace(target)
    return {
        "filename": filename,
        "csv_sha256": digest,
        "batch_size": 10,
        "item_ids": item_ids,
        "pending_confirmation": previous_failed == 10,
    }


def _stage_dzen_media(ledger: AgentLedger) -> dict[str, Any]:
    run_id = os.environ.get("VEDICWAY_SEO_RUN_ID", "").strip()
    if not run_id:
        raise LedgerError("Dzen run ID is required")
    now = datetime.now(UTC).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )
    with ledger.connect() as connection:
        rows = connection.execute(
            """SELECT m.id AS media_id,m.draft_id,m.local_path,m.checksum,
            m.public_url,m.alt_text
            FROM article_media m
            JOIN article_drafts d ON d.id=m.draft_id
            JOIN cron_runs r ON r.id=d.claim_run_id
            WHERE d.claim_run_id=%s AND d.status='published'
              AND d.claim_expires_at>=%s AND r.status='running'
              AND r.job_name='dzen_daily_publish'
              AND m.purpose='cover' AND m.distribution_role IS NULL
            ORDER BY m.created_at,m.id""",
            (run_id, now),
        ).fetchall()
    if len(rows) != 1:
        raise LedgerError("Dzen media staging requires one claimed article cover")
    row = rows[0]
    source = (ledger.data_dir / str(row["local_path"])).resolve()
    try:
        source.relative_to(ledger.data_dir)
    except ValueError as exc:
        raise LedgerError("Dzen cover must stay inside VEDICWAY_SEO_DATA_DIR") from exc
    if not source.is_file():
        raise LedgerError("Claimed Dzen cover file is missing")
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != str(row["checksum"]):
        raise LedgerError("Claimed Dzen cover checksum changed")
    workspace = ledger.data_dir / "browser-input" / "dzen"
    workspace.mkdir(parents=True, exist_ok=True)
    filename = f"vedicway-dzen-cover-{digest[:16]}{source.suffix.casefold()}"
    target = workspace / filename
    if target.exists() and target.read_bytes() != raw:
        raise LedgerError("Dzen cover staging target contains different bytes")
    if not target.exists():
        temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        shutil.copyfile(source, temporary)
        temporary.replace(target)
    return {
        "filename": filename,
        "media_id": str(row["media_id"]),
        "draft_id": str(row["draft_id"]),
        "sha256": digest,
        "public_url": row["public_url"],
        "alt_text": str(row["alt_text"]),
    }


def dispatch(action: str, raw_payload: Any) -> dict[str, Any]:
    payload = _object(raw_payload, "Control payload")
    if action not in ALLOWED_ACTIONS:
        raise LedgerError(f"Unsupported control action: {action}")
    if action == "import-generated-image":
        return _import_generated_image(payload)
    ledger = AgentLedger()
    if action == "build-pinterest-csv":
        _keys(payload, allowed=set())
        return _build_pinterest_csv(ledger)
    if action == "stage-dzen-media":
        _keys(payload, allowed=set())
        return _stage_dzen_media(ledger)
    if action == "ledger-health":
        _keys(payload, allowed=set())
        return {"applied": ledger.initialize(), "health": ledger.health()}
    if action == "ledger-due-lifecycle":
        _keys(payload, allowed={"limit"})
        return {"items": ledger.due_lifecycle(limit=int(payload.get("limit", 25)))}
    if action == "ledger-claim":
        _keys(payload, allowed={"entity", "lease_seconds"}, required={"entity"})
        entity = str(payload["entity"])
        if entity not in CLAIM_ENTITIES:
            raise LedgerError("Unsupported claim entity")
        lease_seconds = int(payload.get("lease_seconds", 3900))
        return {"item": ledger.claim(entity, lease_seconds=lease_seconds)}
    if action == "ledger-claim-pinterest-batch":
        _keys(payload, allowed=set())
        items: list[dict[str, Any]] = []
        for _ in range(10):
            item = ledger.claim("pinterest-pin", lease_seconds=3900)
            if item is None:
                break
            items.append(item)
        return {
            "items": items,
            "batch_size": len(items),
            "complete": len(items) == 10,
        }
    if action == "ledger-write":
        _keys(
            payload,
            allowed={"record_type", "payload"},
            required={"record_type", "payload"},
        )
        record_type = str(payload["record_type"])
        if record_type not in RECORD_TYPES:
            raise LedgerError("Unsupported record type")
        return ledger.write_record(record_type, _object(payload["payload"], "Record payload"))
    if action == "record-run-log":
        _keys(payload, allowed={"log_text"}, required={"log_text"})
        run_id = os.environ.get("VEDICWAY_SEO_RUN_ID", "").strip()
        if not run_id:
            raise LedgerError("VEDICWAY_SEO_RUN_ID is required")
        return ledger.record_run_log(run_id, str(payload["log_text"]))
    if action == "record-result":
        _keys(
            payload,
            allowed={"outcome", "summary", "artifact"},
            required={"outcome", "summary"},
        )
        outcome = str(payload["outcome"])
        if outcome not in {"completed", "blocked", "skipped"}:
            raise LedgerError("Unsupported job outcome")
        run_id = os.environ.get("VEDICWAY_SEO_RUN_ID", "").strip()
        if not run_id:
            raise LedgerError("VEDICWAY_SEO_RUN_ID is required")
        result_id = ledger.record_result(
            run_id,
            outcome,
            str(payload["summary"]),
            payload.get("artifact", {}),
        )
        return {"result_id": result_id}
    if action == "publish-site":
        _keys(payload, allowed={"manifest"}, required={"manifest"})
        manifest = _object(payload["manifest"], "Publication manifest")
        digest = hashlib.sha256(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        manifest_path = ledger.data_dir / "manifests" / f"{digest}.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
        preview = publish_bundle(manifest_path, dry_run=True)
        publication = publish_bundle(manifest_path)
        return {"preview": preview, "publication": publication}
    raise LedgerError(f"Unsupported control action: {action}")


def main(argv: list[str] | None = None) -> int:
    arguments = list(argv if argv is not None else sys.argv[1:])
    if len(arguments) != 1:
        print(json.dumps({"status": "error", "error": "Exactly one control action is required"}))
        return 2
    try:
        raw = sys.stdin.read(2_000_001)
        if len(raw) > 2_000_000:
            raise LedgerError("Control request exceeds 2 MB")
        payload = json.loads(raw or "{}")
        print(json.dumps(dispatch(arguments[0], payload), ensure_ascii=False, sort_keys=True))
        return 0
    except (LedgerError, OSError, ValueError, json.JSONDecodeError) as error:
        print(
            json.dumps(
                {"status": "error", "error": str(error)},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2
    except Exception as error:
        detail = str(error).strip()
        message = f"Control action failed ({type(error).__name__})"
        if detail:
            message = f"{message}: {detail}"
        print(
            json.dumps(
                {"status": "error", "error": message[:2000]},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
