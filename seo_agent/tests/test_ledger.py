from __future__ import annotations

import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from seo_agent.db import AgentLedger, LedgerError, canonical_json, utc_now


def ledger(tmp_path: Path) -> AgentLedger:
    instance = AgentLedger(data_dir=tmp_path)
    instance.initialize()
    return instance


def brief_payload(cluster_id: str, claim_token: str) -> dict[str, object]:
    contract = {
        "title": "Lease test article",
        "primary_query": "lease test",
        "audience_problem": "read the chart",
        "search_intent": "informational",
        "outline": ["answer", "context", "method", "example"],
        "evidence": ["source-one", "source-two"],
        "internal_links": ["/guide", "/chart/new"],
        "prohibited_claims": ["guaranteed prediction"],
    }
    checksum = hashlib.sha256(canonical_json(contract).encode("utf-8")).hexdigest()
    return {"cluster_id": cluster_id, "claim_token": claim_token, **contract, "checksum": checksum}


def passed_report(content_hash: str) -> dict[str, object]:
    return {
        "passed": True,
        "content_hash": content_hash,
        "manual_checks": {
            "brief_alignment": True,
            "evidence_verified": True,
            "originality_reviewed": True,
            "prohibited_claims_reviewed": True,
        },
    }


def test_migrations_are_idempotent_and_checksummed(tmp_path: Path) -> None:
    instance = ledger(tmp_path)
    assert instance.initialize() == []
    health = instance.health()
    assert health["status"] == "ok"
    assert health["foreign_key_violations"] == 0
    with instance.connect() as connection:
        connection.execute("UPDATE schema_migrations SET checksum='tampered'")
    with pytest.raises(LedgerError, match="checksum changed"):
        instance.initialize()


def test_database_path_cannot_escape_its_owned_directory(tmp_path: Path) -> None:
    with pytest.raises(LedgerError, match="must stay inside"):
        AgentLedger(tmp_path.parent / "foreign.sqlite3", data_dir=tmp_path)


def test_run_lease_and_durable_result_contract(tmp_path: Path) -> None:
    instance = ledger(tmp_path)
    run = instance.start_run("article_publish", "2026-07-21T12")
    with pytest.raises(LedgerError):
        instance.start_run("article_publish", "2026-07-21T12")
    assert instance.finish_run(run["run_id"], run["owner_token"]) == "failed"
    second = instance.start_run("article_publish", "2026-07-21T13")
    with pytest.raises(LedgerError, match="durable artifact"):
        instance.record_result(second["run_id"], "completed", "published", {})
    instance.record_result(second["run_id"], "completed", "published", {"url": "https://vedicway.ru/guide/test"})
    assert instance.finish_run(second["run_id"], second["owner_token"]) == "completed"
    with pytest.raises(LedgerError):
        instance.heartbeat(second["run_id"], second["owner_token"])


def test_finished_run_releases_owned_claim_and_rejects_false_completion(
    tmp_path: Path, monkeypatch
) -> None:
    instance = ledger(tmp_path)
    now = utc_now()
    with instance.transaction(immediate=True) as connection:
        connection.execute(
            "INSERT INTO keyword_clusters(id,slug,title,intent,status,created_at,updated_at) VALUES ('owned','owned-topic','Owned topic','informational','ready',?,?)",
            (now, now),
        )
    run = instance.start_run("article_content_production", "2026-07-21T14:00")
    monkeypatch.setenv("VEDICWAY_SEO_RUN_ID", run["run_id"])
    claimed = instance.claim("cluster")
    assert claimed is not None
    assert claimed["claim_run_id"] == run["run_id"]
    instance.record_result(run["run_id"], "completed", "incorrect completion", {"id": "owned"})

    assert instance.finish_run(run["run_id"], run["owner_token"]) == "failed"
    with instance.connect() as connection:
        cluster = connection.execute(
            "SELECT status,claim_token,claim_run_id FROM keyword_clusters WHERE id='owned'"
        ).fetchone()
        finished = connection.execute(
            "SELECT error_code FROM cron_runs WHERE id=?", (run["run_id"],)
        ).fetchone()
    assert tuple(cluster) == ("ready", None, None)
    assert finished["error_code"] == "CLAIM_UNFINISHED"


def test_atomic_cluster_claim_has_one_winner(tmp_path: Path) -> None:
    instance = ledger(tmp_path)
    now = utc_now()
    with instance.transaction(immediate=True) as connection:
        connection.execute(
            "INSERT INTO keyword_clusters(id,slug,title,intent,status,priority_score,created_at,updated_at) VALUES ('one','first-house','First house','informational','ready',10,?,?)",
            (now, now),
        )
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: instance.claim("cluster"), range(8)))
    winners = [result for result in results if result]
    assert len(winners) == 1
    assert winners[0]["id"] == "one"


def test_serp_snapshot_is_typed_region_bound_and_checksummed(tmp_path: Path) -> None:
    instance = ledger(tmp_path)
    query_id = instance.write_record(
        "query",
        {
            "phrase": "дома в натальной карте",
            "region_id": "225",
            "source": "wordstat",
            "observed_at": "2026-07-21T00:00:00.000Z",
        },
    )["id"]
    results = [
        {
            "position": 1,
            "url": "https://example.org/article",
            "title": "Дома натальной карты",
        }
    ]
    checksum = hashlib.sha256(canonical_json(results).encode("utf-8")).hexdigest()
    payload = {
        "query_id": query_id,
        "region_id": "225",
        "requested_at": "2026-07-21T00:05:00.000Z",
        "results": results,
        "checksum": checksum,
    }

    snapshot = instance.write_record("serp-snapshot", payload)
    assert instance.write_record("serp-snapshot", payload) == snapshot
    with pytest.raises(LedgerError, match="checksum"):
        instance.write_record("serp-snapshot", {**payload, "checksum": "0" * 64})
    with pytest.raises(LedgerError, match="region"):
        instance.write_record(
            "serp-snapshot",
            {**payload, "region_id": "213", "requested_at": "2026-07-21T00:06:00.000Z"},
        )


def test_expired_claim_is_reclaimed_and_old_owner_is_rejected(tmp_path: Path) -> None:
    instance = ledger(tmp_path)
    now = utc_now()
    with instance.transaction(immediate=True) as connection:
        connection.execute(
            "INSERT INTO keyword_clusters(id,slug,title,intent,status,priority_score,created_at,updated_at) VALUES ('one','lease-test','Lease test','informational','ready',10,?,?)",
            (now, now),
        )
    first = instance.claim("cluster")
    assert first is not None
    with instance.transaction(immediate=True) as connection:
        connection.execute(
            "UPDATE keyword_clusters SET claim_expires_at='2000-01-01T00:00:00.000Z' WHERE id='one'"
        )
    second = instance.claim("cluster")
    assert second is not None
    assert second["claim_token"] != first["claim_token"]
    payload = brief_payload("one", first["claim_token"])
    with pytest.raises(LedgerError, match="claim is stale"):
        instance.write_record("brief", payload)
    instance.write_record("brief", {**payload, "claim_token": second["claim_token"]})


def test_publication_status_cannot_regress(tmp_path: Path) -> None:
    instance = ledger(tmp_path)
    now = utc_now()
    with instance.transaction(immediate=True) as connection:
        connection.execute("INSERT INTO keyword_clusters(id,slug,title,intent,status,created_at,updated_at) VALUES ('c','topic','Topic','informational','briefed',?,?)", (now, now))
        connection.execute("INSERT INTO content_briefs(id,cluster_id,status,title,primary_query,audience_problem,search_intent,outline_json,evidence_json,internal_links_json,prohibited_claims_json,checksum,created_at) VALUES ('b','c','consumed','Topic','query','problem','informational','[]','[]','[]','[]','sum',?)", (now,))
        connection.execute("INSERT INTO article_drafts(id,brief_id,slug,status,title,excerpt,content_markdown,seo_title,meta_description,focus_keyphrase,category,author_name,content_hash,created_at,updated_at) VALUES ('d','b','topic','published','Topic','Excerpt','Content','SEO','Description','query','Guide','VedicWay','hash',?,?)", (now, now))
        connection.execute("INSERT INTO publications(id,draft_id,target,status,public_url,content_hash,request_hash,evidence_json,published_at) VALUES ('p','d','site','verified','https://vedicway.ru/guide/topic','hash','request-hash','{}',?)", (now,))
    with pytest.raises(sqlite3.IntegrityError, match="cannot regress"):
        with instance.transaction(immediate=True) as connection:
            connection.execute("UPDATE publications SET status='draft' WHERE id='p'")
    with pytest.raises(sqlite3.IntegrityError, match="cannot regress"):
        with instance.transaction(immediate=True) as connection:
            connection.execute("UPDATE publications SET status='published' WHERE id='p'")


def test_verified_article_optimization_requires_claim_hashes_and_public_evidence(tmp_path: Path) -> None:
    instance = ledger(tmp_path)
    now = utc_now()
    with instance.transaction(immediate=True) as connection:
        connection.execute(
            "INSERT INTO keyword_clusters(id,slug,title,intent,status,created_at,updated_at) VALUES ('c','topic','Topic','informational','ready',?,?)",
            (now, now),
        )
    cluster = instance.claim("cluster")
    assert cluster is not None
    brief_id = instance.write_record("brief", brief_payload("c", cluster["claim_token"]))["id"]
    content = "Первоначальный проверенный текст статьи."
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    draft_payload = {
        "brief_id": brief_id,
        "slug": "topic",
        "title": "Topic article",
        "excerpt": "Practical article excerpt",
        "content_markdown": content,
        "seo_title": "Topic SEO title",
        "meta_description": "Topic meta description",
        "focus_keyphrase": "topic",
        "category": "Guide",
        "content_hash": content_hash,
    }
    draft_id = instance.write_record("draft", draft_payload)["id"]
    with pytest.raises(LedgerError, match="not bound"):
        instance.write_record(
            "draft-quality",
            {"draft_id": draft_id, "passed": True, "report": passed_report("wrong")},
        )
    instance.write_record(
        "draft-quality",
        {"draft_id": draft_id, "passed": True, "report": passed_report(content_hash)},
    )
    draft_claim = instance.claim("draft")
    assert draft_claim is not None
    failed_attempt = instance.write_record(
        "publication-attempt",
        {
            "draft_id": draft_id,
            "target": "site",
            "claim_token": draft_claim["claim_token"],
            "idempotency_key": "site-topic-initial-0001",
            "attempt_token": "attempt-initial-failed",
            "status": "failed",
            "content_hash": content_hash,
            "request_hash": "request-initial",
        },
    )
    succeeded_attempt = instance.write_record(
        "publication-attempt",
        {
            "draft_id": draft_id,
            "target": "site",
            "claim_token": draft_claim["claim_token"],
            "idempotency_key": "site-topic-initial-0001",
            "attempt_token": "attempt-initial-success",
            "status": "succeeded",
            "content_hash": content_hash,
            "request_hash": "request-initial",
        },
    )
    assert failed_attempt["attempt_no"] == 1
    assert succeeded_attempt["attempt_no"] == 2
    checks = {
        "canonical": True,
        "article_schema": True,
        "title": True,
        "request_hash": True,
        "sitemap": True,
        "dzen_feed": True,
        "cover": True,
    }
    publication_id = instance.write_record(
        "publication",
        {
            "draft_id": draft_id,
            "target": "site",
            "claim_token": draft_claim["claim_token"],
            "attempt_token": "attempt-initial-success",
            "public_url": "https://vedicway.ru/guide/topic",
            "content_hash": content_hash,
            "request_hash": "request-initial",
            "evidence": {"checks": checks},
        },
    )["id"]
    action_id = instance.write_record(
        "action",
        {
            "publication_id": publication_id,
            "action_type": "title_test",
            "hypothesis": "A clearer title improves CTR",
            "success_metric": "CTR after 28 days",
            "evidence": {"baseline_ctr": 0.01},
        },
    )["id"]
    action = instance.claim("action")
    assert action is not None
    assert action["draft_id"] == draft_id
    revised = instance.write_record(
        "draft",
        {
            **draft_payload,
            "seo_title": "A clearer Topic SEO title",
            "action_id": action_id,
            "action_claim_token": action["claim_token"],
        },
    )
    assert revised["id"] == draft_id
    instance.write_record(
        "draft-quality",
        {"draft_id": draft_id, "passed": True, "report": passed_report(content_hash)},
    )
    revision_claim = instance.claim("draft")
    assert revision_claim is not None
    instance.write_record(
        "publication-attempt",
        {
            "draft_id": draft_id,
            "target": "site",
            "claim_token": revision_claim["claim_token"],
            "idempotency_key": "site-topic-revision-0001",
            "attempt_token": "attempt-revision-success",
            "status": "succeeded",
            "content_hash": content_hash,
            "request_hash": "request-revision",
        },
    )
    updated_publication_id = instance.write_record(
        "publication",
        {
            "draft_id": draft_id,
            "target": "site",
            "claim_token": revision_claim["claim_token"],
            "attempt_token": "attempt-revision-success",
            "public_url": "https://vedicway.ru/guide/topic",
            "content_hash": content_hash,
            "request_hash": "request-revision",
            "evidence": {"checks": checks},
        },
    )["id"]
    assert updated_publication_id == publication_id
    result = instance.write_record(
        "action-result",
        {
            "action_id": action_id,
            "claim_token": action["claim_token"],
            "status": "completed",
            "evidence": {"request_hash": "request-revision"},
        },
    )
    assert result["status"] == "completed"


def test_online_backup_is_consistent(tmp_path: Path) -> None:
    instance = ledger(tmp_path)
    target = tmp_path / "backups" / "seo.sqlite3"
    result = instance.backup(target)
    assert result["sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()
    with sqlite3.connect(target) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
