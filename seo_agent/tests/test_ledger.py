from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg
import pytest
from PIL import Image

from seo_agent.control import dispatch
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


def insert_published_draft(
    instance: AgentLedger,
    *,
    draft_id: str,
    pinterest_media_count: int = 0,
    dzen_evidence: dict[str, object] | None = None,
) -> dict[str, str]:
    now = utc_now()
    slug = draft_id
    content_hash = hashlib.sha256(f"content:{draft_id}".encode()).hexdigest()
    cover = instance.data_dir / "media" / f"{draft_id}-cover.webp"
    cover.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1200, 630), "navy").save(cover, "WEBP")
    with instance.transaction(immediate=True) as connection:
        connection.execute(
            "INSERT INTO keyword_clusters(id,slug,title,intent,status,created_at,updated_at) VALUES (%s,%s,%s,'informational','published',%s,%s)",
            (f"cluster-{draft_id}", f"cluster-{slug}", "Topic", now, now),
        )
        connection.execute(
            """INSERT INTO content_briefs(
            id,cluster_id,status,title,primary_query,audience_problem,search_intent,
            outline_json,evidence_json,internal_links_json,prohibited_claims_json,
            checksum,created_at
            ) VALUES (%s,%s,'consumed','Topic','query','problem','informational',
            '[]','[]','[]','[]','brief-hash',%s)""",
            (f"brief-{draft_id}", f"cluster-{draft_id}", now),
        )
        connection.execute(
            """INSERT INTO article_drafts(
            id,brief_id,slug,status,title,excerpt,content_markdown,seo_title,
            meta_description,focus_keyphrase,category,author_name,content_hash,
            created_at,updated_at,approved_at
            ) VALUES (%s,%s,%s,'published','Topic','Excerpt','Content','SEO title',
            'Description','topic','Guide','Редакция VedicWay',%s,%s,%s,%s)""",
            (
                draft_id,
                f"brief-{draft_id}",
                slug,
                content_hash,
                now,
                now,
                now,
            ),
        )
        connection.execute(
            """INSERT INTO article_media(
            id,draft_id,purpose,local_path,alt_text,title,caption,source_kind,
            license_note,checksum,backend_media_id,public_url,distribution_role,
            width,height,created_at
            ) VALUES (%s,%s,'cover',%s,'Обложка','','','generated','Owned',%s,
            %s,%s,NULL,1200,630,%s)""",
            (
                f"cover-{draft_id}",
                draft_id,
                cover.relative_to(instance.data_dir).as_posix(),
                hashlib.sha256(cover.read_bytes()).hexdigest(),
                f"backend-cover-{draft_id}",
                f"https://vedicway.ru/media/articles/backend-cover-{draft_id}/1200.webp",
                now,
            ),
        )
        for index in range(1, pinterest_media_count + 1):
            card = instance.data_dir / "media" / f"{draft_id}-pin-{index}.webp"
            Image.new(
                "RGB", (1000, 1500), (index * 20, index * 10, 40)
            ).save(card, "WEBP")
            connection.execute(
                """INSERT INTO article_media(
                id,draft_id,purpose,local_path,alt_text,title,caption,source_kind,
                license_note,checksum,backend_media_id,public_url,distribution_role,
                width,height,created_at
                ) VALUES (%s,%s,'body',%s,%s,'','','generated','Owned',%s,%s,%s,
                'pinterest',1000,1500,%s)""",
                (
                    f"pin-{draft_id}-{index}",
                    draft_id,
                    card.relative_to(instance.data_dir).as_posix(),
                    f"Карточка {index}",
                    hashlib.sha256(card.read_bytes()).hexdigest(),
                    f"backend-pin-{draft_id}-{index}",
                    f"https://vedicway.ru/media/articles/backend-pin-{draft_id}-{index}/1000.webp",
                    now,
                ),
            )
        connection.execute(
            """INSERT INTO publications(
            id,draft_id,target,status,public_url,content_hash,request_hash,
            evidence_json,published_at,verified_at
            ) VALUES (%s,%s,'site','verified',%s,%s,'site-request',%s,%s,%s)""",
            (
                f"site-{draft_id}",
                draft_id,
                f"https://vedicway.ru/blog/{slug}",
                content_hash,
                canonical_json({"checks": {"canonical": True}}),
                now,
                now,
            ),
        )
        if dzen_evidence is not None:
            connection.execute(
                """INSERT INTO publications(
                id,draft_id,target,status,public_url,external_id,content_hash,
                request_hash,evidence_json,published_at,verified_at
                ) VALUES (%s,%s,'dzen','verified',%s,%s,%s,'dzen-request',%s,%s,%s)""",
                (
                    f"dzen-{draft_id}",
                    draft_id,
                    f"https://dzen.ru/a/{draft_id}",
                    f"external-{draft_id}",
                    content_hash,
                    canonical_json(dzen_evidence),
                    now,
                    now,
                ),
            )
    return {
        "draft_id": draft_id,
        "content_hash": content_hash,
        "cover_path": str(cover),
        "site_publication_id": f"site-{draft_id}",
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


def test_database_url_must_use_postgresql(tmp_path: Path) -> None:
    with pytest.raises(LedgerError, match="must use PostgreSQL"):
        AgentLedger("unsupported-database-url", data_dir=tmp_path)


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
            "INSERT INTO keyword_clusters(id,slug,title,intent,status,created_at,updated_at) VALUES ('owned','owned-topic','Owned topic','informational','ready',%s,%s)",
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
            "SELECT error_code FROM cron_runs WHERE id=%s", (run["run_id"],)
        ).fetchone()
    assert cluster == {"status": "ready", "claim_token": None, "claim_run_id": None}
    assert finished["error_code"] == "CLAIM_UNFINISHED"


def test_atomic_cluster_claim_has_one_winner(tmp_path: Path) -> None:
    instance = ledger(tmp_path)
    now = utc_now()
    with instance.transaction(immediate=True) as connection:
        connection.execute(
            "INSERT INTO keyword_clusters(id,slug,title,intent,status,priority_score,created_at,updated_at) VALUES ('one','first-house','First house','informational','ready',10,%s,%s)",
            (now, now),
        )
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: instance.claim("cluster"), range(8)))
    winners = [result for result in results if result]
    assert len(winners) == 1
    assert winners[0]["id"] == "one"


def test_site_claim_recovers_a_published_draft_with_missing_distribution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = ledger(tmp_path)
    created = insert_published_draft(
        instance,
        draft_id="published-without-distribution",
        pinterest_media_count=10,
    )
    run = instance.start_run("article_site_publish", "recovery-site-run")
    monkeypatch.setenv("VEDICWAY_SEO_RUN_ID", run["run_id"])

    claimed = instance.claim("draft")

    assert claimed is not None
    assert claimed["id"] == created["draft_id"]
    assert claimed["recovery_mode"] == "missing_distribution"
    assert claimed["site_publication_id"] == created["site_publication_id"]
    assert claimed["distribution_counts"] == {"vk": 0, "pinterest": 0}
    instance.record_result(run["run_id"], "skipped", "release recovery claim", {})
    assert instance.finish_run(run["run_id"], run["owner_token"]) == "skipped"
    with instance.connect() as connection:
        released = connection.execute(
            "SELECT status,claim_token,claim_run_id FROM article_drafts WHERE id=%s",
            (created["draft_id"],),
        ).fetchone()
    assert released == {
        "status": "published",
        "claim_token": None,
        "claim_run_id": None,
    }


def test_dzen_claim_recovers_missing_cover_and_excludes_distribution_media(
    tmp_path: Path,
) -> None:
    instance = ledger(tmp_path)
    created = insert_published_draft(
        instance,
        draft_id="dzen-cover-recovery",
        pinterest_media_count=1,
        dzen_evidence={
            "checks": {
                "editor_persisted": True,
                "public_url_verified": True,
                "playwright_ui": True,
            }
        },
    )

    claimed = instance.claim("dzen-article")

    assert claimed is not None
    assert claimed["id"] == created["draft_id"]
    assert claimed["recovery_mode"] == "missing_cover"
    assert claimed["existing_dzen_public_url"] == (
        "https://dzen.ru/a/dzen-cover-recovery"
    )
    assert [item["purpose"] for item in claimed["media"]] == ["cover"]


def test_dzen_publication_requires_verified_cover_evidence(tmp_path: Path) -> None:
    instance = ledger(tmp_path)
    created = insert_published_draft(instance, draft_id="dzen-evidence")
    instance.write_record(
        "publication-attempt",
        {
            "draft_id": created["draft_id"],
            "target": "dzen",
            "idempotency_key": "dzen-evidence-attempt-0001",
            "attempt_token": "dzen-evidence-attempt-token",
            "status": "succeeded",
            "content_hash": created["content_hash"],
            "request_hash": "dzen-evidence-request",
        },
    )
    incomplete = {
        "checks": {
            "editor_persisted": True,
            "public_url_verified": True,
            "playwright_ui": True,
        }
    }

    with pytest.raises(LedgerError, match="cover"):
        instance.write_record(
            "publication",
            {
                "draft_id": created["draft_id"],
                "target": "dzen",
                "public_url": "https://dzen.ru/a/dzen-evidence",
                "external_id": "dzen-evidence",
                "content_hash": created["content_hash"],
                "request_hash": "dzen-evidence-request",
                "attempt_token": "dzen-evidence-attempt-token",
                "evidence": incomplete,
            },
        )

    publication = instance.write_record(
        "publication",
        {
            "draft_id": created["draft_id"],
            "target": "dzen",
            "public_url": "https://dzen.ru/a/dzen-evidence",
            "external_id": "dzen-evidence",
            "content_hash": created["content_hash"],
            "request_hash": "dzen-evidence-request",
            "attempt_token": "dzen-evidence-attempt-token",
            "evidence": {
                "checks": {**incomplete["checks"], "cover_present": True}
            },
        },
    )
    assert publication["id"]


def test_control_stages_the_claimed_dzen_cover_in_browser_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VEDICWAY_SEO_DATA_DIR", str(tmp_path))
    instance = ledger(tmp_path)
    created = insert_published_draft(instance, draft_id="dzen-stage")
    run = instance.start_run("dzen_daily_publish", "dzen-stage-run")
    monkeypatch.setenv("VEDICWAY_SEO_RUN_ID", run["run_id"])
    claimed = instance.claim("dzen-article")
    assert claimed is not None

    staged = dispatch("stage-dzen-media", {})

    target = tmp_path / "browser-input" / "dzen" / staged["filename"]
    assert staged["media_id"] == f"cover-{created['draft_id']}"
    assert staged["sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()
    assert target.read_bytes() == Path(created["cover_path"]).read_bytes()


def test_serp_snapshot_is_typed_region_bound_and_checksummed(tmp_path: Path) -> None:
    instance = ledger(tmp_path)
    run = instance.start_run("article_intelligence_refresh", "2026-07-21")
    raw_response_id = instance.write_record(
        "tool-response",
        {
            "cron_run_id": run["run_id"],
            "provider": "yandex-search",
            "tool_name": "search",
            "request_hash": "search-request-hash",
            "response": {"results": ["example"]},
        },
    )["id"]
    query_id = instance.write_record(
        "query",
        {
            "phrase": "дома в натальной карте",
            "region_id": "225",
            "source": "seed",
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
        "raw_response_id": raw_response_id,
    }

    snapshot = instance.write_record("serp-snapshot", payload)
    assert snapshot["checksum"] == checksum
    assert instance.write_record("serp-snapshot", payload) == snapshot
    assert instance.write_record(
        "serp-snapshot", {**payload, "checksum": "0" * 64}
    ) == snapshot
    with pytest.raises(LedgerError, match="region"):
        instance.write_record(
            "serp-snapshot",
            {**payload, "region_id": "213", "requested_at": "2026-07-21T00:06:00.000Z"},
        )


def test_ready_cluster_requires_wordstat_and_serp_provenance(tmp_path: Path) -> None:
    instance = ledger(tmp_path)
    run = instance.start_run("article_intelligence_refresh", "2026-07-22")
    wordstat_raw = instance.write_record(
        "tool-response",
        {
            "cron_run_id": run["run_id"],
            "provider": "wordstat",
            "tool_name": "top_requests",
            "request_hash": "wordstat-request-hash",
            "response": {"items": [{"phrase": "дома в натальной карте"}]},
        },
    )["id"]
    search_raw = instance.write_record(
        "tool-response",
        {
            "cron_run_id": run["run_id"],
            "provider": "yandex-search",
            "tool_name": "search",
            "request_hash": "serp-request-hash",
            "response": {"results": [{"url": "https://example.org"}]},
        },
    )["id"]
    query_id = instance.write_record(
        "query",
        {
            "phrase": "дома в натальной карте",
            "region_id": "225",
            "source": "wordstat",
            "raw_response_id": wordstat_raw,
        },
    )["id"]
    payload = {
        "slug": "doma-v-natalnoy-karte",
        "title": "Дома в натальной карте",
        "intent": "informational",
        "status": "ready",
        "query_ids": [query_id],
        "primary_query_id": query_id,
    }
    with pytest.raises(LedgerError, match="SERP"):
        instance.write_record("cluster", payload)
    results = [{"position": 1, "url": "https://example.org"}]
    instance.write_record(
        "serp-snapshot",
        {
            "query_id": query_id,
            "region_id": "225",
            "results": results,
            "checksum": hashlib.sha256(canonical_json(results).encode()).hexdigest(),
            "raw_response_id": search_raw,
        },
    )
    assert instance.write_record("cluster", payload)["id"]


def test_cluster_claim_returns_persisted_wordstat_and_serp_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = ledger(tmp_path)
    research_run = instance.start_run(
        "article_intelligence_refresh", "2026-08-23T13:48"
    )
    wordstat_raw = instance.write_record(
        "tool-response",
        {
            "cron_run_id": research_run["run_id"],
            "provider": "wordstat",
            "tool_name": "top_requests",
            "request_hash": "wordstat-evidence-hash",
            "response": {"items": [{"phrase": "дома в натальной карте"}]},
        },
    )["id"]
    search_raw = instance.write_record(
        "tool-response",
        {
            "cron_run_id": research_run["run_id"],
            "provider": "yandex-search",
            "tool_name": "search",
            "request_hash": "search-evidence-hash",
            "response": {"results": [{"url": "https://example.org/houses"}]},
        },
    )["id"]
    query_id = instance.write_record(
        "query",
        {
            "phrase": "дома в натальной карте",
            "region_id": "225",
            "source": "wordstat",
            "intent": "informational",
            "metrics": {"shows": 1234},
            "observed_at": "2026-08-23T10:50:00.000Z",
            "raw_response_id": wordstat_raw,
        },
    )["id"]
    results = [
        {
            "position": 1,
            "url": "https://example.org/houses",
            "title": "Дома натальной карты",
        }
    ]
    snapshot_id = instance.write_record(
        "serp-snapshot",
        {
            "query_id": query_id,
            "region_id": "225",
            "requested_at": "2026-08-23T10:51:00.000Z",
            "results": results,
            "checksum": hashlib.sha256(
                canonical_json(results).encode("utf-8")
            ).hexdigest(),
            "raw_response_id": search_raw,
        },
    )["id"]
    cluster_id = instance.write_record(
        "cluster",
        {
            "slug": "doma-v-natalnoy-karte",
            "title": "Дома в натальной карте",
            "intent": "informational",
            "status": "ready",
            "priority_score": 10,
            "rationale": "Подтвержденный спрос и информационный SERP",
            "query_ids": [query_id],
            "primary_query_id": query_id,
        },
    )["id"]
    content_run = instance.start_run(
        "article_content_production", "2026-08-23T13:54"
    )
    monkeypatch.setenv("VEDICWAY_SEO_RUN_ID", content_run["run_id"])

    claimed = instance.claim("cluster")

    assert claimed is not None
    assert claimed["id"] == cluster_id
    assert claimed["primary_query"]["id"] == query_id
    assert claimed["primary_query"]["phrase"] == "дома в натальной карте"
    assert claimed["queries"][0]["metrics"] == {"shows": 1234}
    assert claimed["queries"][0]["is_primary"] is True
    assert claimed["queries"][0]["serp_snapshots"] == [
        {
            "id": snapshot_id,
            "region_id": "225",
            "requested_at": "2026-08-23T10:51:00.000Z",
            "results": results,
            "checksum": hashlib.sha256(
                canonical_json(results).encode("utf-8")
            ).hexdigest(),
            "raw_response_id": search_raw,
        }
    ]


def test_active_run_accepts_one_short_text_log(tmp_path: Path) -> None:
    instance = ledger(tmp_path)
    run = instance.start_run("article_content_production", "2026-08-23T14:00")

    recorded = instance.record_run_log(
        run["run_id"],
        "Забрал кластер и подготовил материал. Ошибок не возникло.",
    )

    assert recorded == {"cron_run_id": run["run_id"]}
    with instance.connect() as connection:
        stored = connection.execute(
            "SELECT log_text FROM run_logs WHERE cron_run_id=%s", (run["run_id"],)
        ).fetchone()
    assert stored == {
        "log_text": "Забрал кластер и подготовил материал. Ошибок не возникло."
    }
    with pytest.raises(LedgerError, match="already has a log"):
        instance.record_run_log(run["run_id"], "Повторная запись")


def test_scheduler_backfills_run_log_when_codex_omits_it(tmp_path: Path) -> None:
    instance = ledger(tmp_path)
    run = instance.start_run("article_site_publish", "2026-08-23T14:01")
    instance.record_result(
        run["run_id"], "skipped", "Одобренных черновиков нет", {}
    )

    assert instance.finish_run(run["run_id"], run["owner_token"]) == "skipped"

    with instance.connect() as connection:
        stored = connection.execute(
            "SELECT log_text FROM run_logs WHERE cron_run_id=%s", (run["run_id"],)
        ).fetchone()
    assert stored is not None
    assert "Codex exec не записал отдельный лог" in stored["log_text"]
    assert "Одобренных черновиков нет" in stored["log_text"]


def test_expired_claim_is_reclaimed_and_old_owner_is_rejected(tmp_path: Path) -> None:
    instance = ledger(tmp_path)
    now = utc_now()
    with instance.transaction(immediate=True) as connection:
        connection.execute(
            "INSERT INTO keyword_clusters(id,slug,title,intent,status,priority_score,created_at,updated_at) VALUES ('one','lease-test','Lease test','informational','ready',10,%s,%s)",
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
        connection.execute("INSERT INTO keyword_clusters(id,slug,title,intent,status,created_at,updated_at) VALUES ('c','topic','Topic','informational','briefed',%s,%s)", (now, now))
        connection.execute("INSERT INTO content_briefs(id,cluster_id,status,title,primary_query,audience_problem,search_intent,outline_json,evidence_json,internal_links_json,prohibited_claims_json,checksum,created_at) VALUES ('b','c','consumed','Topic','query','problem','informational','[]','[]','[]','[]','sum',%s)", (now,))
        connection.execute("INSERT INTO article_drafts(id,brief_id,slug,status,title,excerpt,content_markdown,seo_title,meta_description,focus_keyphrase,category,author_name,content_hash,created_at,updated_at) VALUES ('d','b','topic','published','Topic','Excerpt','Content','SEO','Description','query','Guide','VedicWay','hash',%s,%s)", (now, now))
        connection.execute("INSERT INTO publications(id,draft_id,target,status,public_url,content_hash,request_hash,evidence_json,published_at) VALUES ('p','d','site','verified','https://vedicway.ru/guide/topic','hash','request-hash','{}',%s)", (now,))
    with pytest.raises(psycopg.IntegrityError, match="cannot regress"):
        with instance.transaction(immediate=True) as connection:
            connection.execute("UPDATE publications SET status='draft' WHERE id='p'")
    with pytest.raises(psycopg.IntegrityError, match="cannot regress"):
        with instance.transaction(immediate=True) as connection:
            connection.execute("UPDATE publications SET status='published' WHERE id='p'")


def test_verified_article_optimization_requires_claim_hashes_and_public_evidence(tmp_path: Path) -> None:
    instance = ledger(tmp_path)
    now = utc_now()
    with instance.transaction(immediate=True) as connection:
        connection.execute(
            "INSERT INTO keyword_clusters(id,slug,title,intent,status,created_at,updated_at) VALUES ('c','topic','Topic','informational','ready',%s,%s)",
            (now, now),
        )
    cluster = instance.claim("cluster")
    assert cluster is not None
    brief_contract = brief_payload("c", cluster["claim_token"])
    brief_contract.pop("checksum")
    brief = instance.write_record("brief", brief_contract)
    brief_id = brief["id"]
    assert len(brief["checksum"]) == 64
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
    }
    draft = instance.write_record("draft", draft_payload)
    draft_id = draft["id"]
    assert draft["content_hash"] == content_hash
    with pytest.raises(LedgerError, match="not bound"):
        instance.write_record(
            "draft-quality",
            {"draft_id": draft_id, "passed": True, "report": passed_report("wrong")},
        )
    instance.write_record(
        "draft-quality",
        {"draft_id": draft_id, "passed": True, "report": passed_report(content_hash)},
    )
    cover_path = instance.data_dir / "media" / "topic-cover.webp"
    cover_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1200, 630), "navy").save(cover_path, "WEBP")
    cover_id = instance.write_record(
        "media",
        {
            "draft_id": draft_id,
            "purpose": "cover",
            "local_path": str(cover_path),
            "alt_text": "Натальная карта",
            "source_kind": "generated",
            "license_note": "Generated for VedicWay with Codex Image Gen",
            "checksum": hashlib.sha256(cover_path.read_bytes()).hexdigest(),
        },
    )["id"]
    draft_claim = instance.claim("draft")
    assert draft_claim is not None
    assert draft_claim["media"] == [
        {
            "id": cover_id,
            "purpose": "cover",
            "local_path": "media/topic-cover.webp",
            "alt_text": "Натальная карта",
            "title": "",
            "caption": "",
            "source_kind": "generated",
            "source_url": None,
            "license_note": "Generated for VedicWay with Codex Image Gen",
            "checksum": hashlib.sha256(cover_path.read_bytes()).hexdigest(),
            "public_url": None,
            "distribution_role": None,
            "width": 1200,
            "height": 630,
        }
    ]
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
        "cover": True,
    }
    with pytest.raises(LedgerError, match="incomplete"):
        instance.write_record(
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
        )
    checks["all_media_public"] = True
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
