PRAGMA foreign_keys = ON;

CREATE TABLE schema_migrations (
    version TEXT PRIMARY KEY,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL
) STRICT;

CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL CHECK (json_valid(value_json)),
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE source_documents (
    id TEXT PRIMARY KEY,
    source_kind TEXT NOT NULL CHECK (source_kind IN ('web', 'mcp', 'repository', 'editorial')),
    source_key TEXT NOT NULL,
    url TEXT,
    status TEXT NOT NULL CHECK (status IN ('active', 'stale', 'rejected')),
    checksum TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    UNIQUE (source_kind, source_key, checksum)
) STRICT;

CREATE TABLE cron_runs (
    id TEXT PRIMARY KEY,
    job_name TEXT NOT NULL,
    schedule_token TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed', 'blocked', 'skipped')),
    owner_token TEXT NOT NULL,
    started_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    finished_at TEXT,
    outcome TEXT,
    error_code TEXT,
    error_detail TEXT,
    UNIQUE (job_name, schedule_token)
) STRICT;

CREATE UNIQUE INDEX one_running_cron_per_job
ON cron_runs(job_name) WHERE status = 'running';

CREATE TABLE skill_runs (
    id TEXT PRIMARY KEY,
    cron_run_id TEXT NOT NULL REFERENCES cron_runs(id) ON DELETE CASCADE,
    skill_name TEXT NOT NULL,
    attempt_token TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed', 'blocked', 'skipped')),
    input_hash TEXT NOT NULL,
    output_json TEXT CHECK (output_json IS NULL OR json_valid(output_json)),
    started_at TEXT NOT NULL,
    finished_at TEXT
) STRICT;

CREATE TABLE raw_tool_responses (
    id TEXT PRIMARY KEY,
    cron_run_id TEXT NOT NULL REFERENCES cron_runs(id) ON DELETE CASCADE,
    provider TEXT NOT NULL CHECK (provider IN ('yandex-search', 'wordstat', 'webmaster', 'metrika', 'site', 'dzen')),
    tool_name TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    response_json TEXT NOT NULL CHECK (json_valid(response_json)),
    observed_at TEXT NOT NULL,
    expires_at TEXT,
    UNIQUE (provider, tool_name, request_hash, observed_at)
) STRICT;

CREATE TABLE keyword_queries (
    id TEXT PRIMARY KEY,
    phrase TEXT NOT NULL COLLATE NOCASE,
    region_id TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('wordstat', 'webmaster', 'metrika', 'seed')),
    intent TEXT CHECK (intent IS NULL OR intent IN ('informational', 'commercial', 'navigational')),
    metrics_json TEXT NOT NULL CHECK (json_valid(metrics_json)),
    observed_at TEXT NOT NULL,
    UNIQUE (phrase, region_id, source, observed_at)
) STRICT;

CREATE TABLE serp_snapshots (
    id TEXT PRIMARY KEY,
    query_id TEXT NOT NULL REFERENCES keyword_queries(id) ON DELETE CASCADE,
    region_id TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    result_json TEXT NOT NULL CHECK (json_valid(result_json)),
    checksum TEXT NOT NULL,
    UNIQUE (query_id, requested_at)
) STRICT;

CREATE TABLE keyword_clusters (
    id TEXT PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    intent TEXT NOT NULL CHECK (intent IN ('informational', 'commercial', 'navigational')),
    status TEXT NOT NULL CHECK (status IN ('candidate', 'ready', 'claimed', 'briefed', 'rejected', 'published')),
    priority_score REAL NOT NULL DEFAULT 0,
    rationale TEXT NOT NULL DEFAULT '',
    claim_token TEXT UNIQUE,
    claim_expires_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE cluster_queries (
    cluster_id TEXT NOT NULL REFERENCES keyword_clusters(id) ON DELETE CASCADE,
    query_id TEXT NOT NULL REFERENCES keyword_queries(id) ON DELETE CASCADE,
    is_primary INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
    PRIMARY KEY (cluster_id, query_id)
) WITHOUT ROWID, STRICT;

CREATE UNIQUE INDEX one_primary_query_per_cluster
ON cluster_queries(cluster_id) WHERE is_primary = 1;

CREATE TABLE content_briefs (
    id TEXT PRIMARY KEY,
    cluster_id TEXT NOT NULL UNIQUE REFERENCES keyword_clusters(id) ON DELETE RESTRICT,
    status TEXT NOT NULL CHECK (status IN ('draft', 'approved', 'rejected', 'consumed')),
    title TEXT NOT NULL,
    primary_query TEXT NOT NULL,
    audience_problem TEXT NOT NULL,
    search_intent TEXT NOT NULL,
    outline_json TEXT NOT NULL CHECK (json_valid(outline_json)),
    evidence_json TEXT NOT NULL CHECK (json_valid(evidence_json)),
    internal_links_json TEXT NOT NULL CHECK (json_valid(internal_links_json)),
    prohibited_claims_json TEXT NOT NULL CHECK (json_valid(prohibited_claims_json)),
    checksum TEXT NOT NULL,
    created_at TEXT NOT NULL,
    approved_at TEXT
) STRICT;

CREATE TABLE article_drafts (
    id TEXT PRIMARY KEY,
    brief_id TEXT NOT NULL REFERENCES content_briefs(id) ON DELETE RESTRICT,
    slug TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('draft', 'editing', 'quality_failed', 'approved', 'publishing', 'published', 'rejected')),
    title TEXT NOT NULL,
    excerpt TEXT NOT NULL,
    content_markdown TEXT NOT NULL,
    seo_title TEXT NOT NULL,
    meta_description TEXT NOT NULL,
    focus_keyphrase TEXT NOT NULL,
    category TEXT NOT NULL,
    author_name TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    quality_report_json TEXT CHECK (quality_report_json IS NULL OR json_valid(quality_report_json)),
    claim_token TEXT UNIQUE,
    claim_expires_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    approved_at TEXT
) STRICT;

CREATE TABLE article_media (
    id TEXT PRIMARY KEY,
    draft_id TEXT NOT NULL REFERENCES article_drafts(id) ON DELETE CASCADE,
    purpose TEXT NOT NULL CHECK (purpose IN ('cover', 'body')),
    local_path TEXT NOT NULL,
    alt_text TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    caption TEXT NOT NULL DEFAULT '',
    source_kind TEXT NOT NULL CHECK (source_kind IN ('generated', 'licensed', 'owned')),
    source_url TEXT,
    license_note TEXT NOT NULL,
    checksum TEXT NOT NULL,
    backend_media_id TEXT,
    public_url TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (draft_id, checksum, purpose)
) STRICT;

CREATE UNIQUE INDEX one_cover_per_draft
ON article_media(draft_id) WHERE purpose = 'cover';

CREATE TABLE publication_attempts (
    id TEXT PRIMARY KEY,
    draft_id TEXT NOT NULL REFERENCES article_drafts(id) ON DELETE RESTRICT,
    target TEXT NOT NULL CHECK (target IN ('site', 'dzen')),
    attempt_no INTEGER NOT NULL CHECK (attempt_no > 0),
    idempotency_key TEXT NOT NULL,
    attempt_token TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('succeeded', 'failed', 'blocked')),
    content_hash TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    response_json TEXT CHECK (response_json IS NULL OR json_valid(response_json)),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    UNIQUE (draft_id, target, attempt_no)
) STRICT;

CREATE TABLE publications (
    id TEXT PRIMARY KEY,
    draft_id TEXT NOT NULL REFERENCES article_drafts(id) ON DELETE RESTRICT,
    target TEXT NOT NULL CHECK (target IN ('site', 'dzen')),
    status TEXT NOT NULL CHECK (status IN ('published', 'verified', 'removed')),
    public_url TEXT NOT NULL,
    external_id TEXT,
    content_hash TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    evidence_json TEXT NOT NULL CHECK (json_valid(evidence_json)),
    published_at TEXT NOT NULL,
    verified_at TEXT,
    UNIQUE (draft_id, target)
) STRICT;

CREATE TRIGGER publication_terminal_state_guard
BEFORE UPDATE OF status ON publications
WHEN (OLD.status = 'published' AND NEW.status NOT IN ('published', 'verified', 'removed'))
  OR (OLD.status = 'verified' AND NEW.status NOT IN ('verified', 'removed'))
BEGIN
    SELECT RAISE(ABORT, 'publication status cannot regress');
END;

CREATE TABLE performance_snapshots (
    id TEXT PRIMARY KEY,
    publication_id TEXT NOT NULL REFERENCES publications(id) ON DELETE CASCADE,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    webmaster_json TEXT NOT NULL CHECK (json_valid(webmaster_json)),
    metrika_json TEXT NOT NULL CHECK (json_valid(metrika_json)),
    captured_at TEXT NOT NULL,
    UNIQUE (publication_id, window_start, window_end)
) STRICT;

CREATE TABLE optimization_actions (
    id TEXT PRIMARY KEY,
    publication_id TEXT NOT NULL REFERENCES publications(id) ON DELETE CASCADE,
    action_type TEXT NOT NULL CHECK (action_type IN ('rewrite', 'expand', 'internal_links', 'title_test', 'recrawl', 'hold')),
    status TEXT NOT NULL CHECK (status IN ('open', 'claimed', 'completed', 'rejected')),
    priority_score REAL NOT NULL DEFAULT 0,
    hypothesis TEXT NOT NULL,
    success_metric TEXT NOT NULL,
    evidence_json TEXT NOT NULL CHECK (json_valid(evidence_json)),
    baseline_request_hash TEXT NOT NULL,
    result_evidence_json TEXT CHECK (result_evidence_json IS NULL OR json_valid(result_evidence_json)),
    claim_token TEXT UNIQUE,
    claim_expires_at TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
) STRICT;

CREATE UNIQUE INDEX one_active_action_per_type
ON optimization_actions(publication_id, action_type)
WHERE status IN ('open', 'claimed');

CREATE TABLE job_results (
    id TEXT PRIMARY KEY,
    cron_run_id TEXT NOT NULL UNIQUE REFERENCES cron_runs(id) ON DELETE CASCADE,
    outcome TEXT NOT NULL CHECK (outcome IN ('completed', 'blocked', 'skipped')),
    summary TEXT NOT NULL,
    artifact_json TEXT NOT NULL CHECK (json_valid(artifact_json)),
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    detail_json TEXT NOT NULL CHECK (json_valid(detail_json))
) STRICT;

CREATE VIEW v_ready_clusters AS
SELECT * FROM keyword_clusters
WHERE status = 'ready' AND (claim_expires_at IS NULL OR claim_expires_at < strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
ORDER BY priority_score DESC, created_at ASC;

CREATE VIEW v_ready_drafts AS
SELECT d.*, m.id AS cover_id, m.local_path AS cover_path
FROM article_drafts d
JOIN article_media m ON m.draft_id = d.id AND m.purpose = 'cover'
WHERE d.status = 'approved'
  AND (d.claim_expires_at IS NULL OR d.claim_expires_at < strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
ORDER BY d.approved_at ASC;

CREATE VIEW v_due_lifecycle AS
SELECT p.* FROM publications p
LEFT JOIN performance_snapshots s ON s.publication_id = p.id
WHERE p.target = 'site' AND p.status IN ('published', 'verified')
GROUP BY p.id
HAVING MAX(s.captured_at) IS NULL OR MAX(s.captured_at) < datetime('now', '-7 days');

CREATE VIEW v_open_actions AS
SELECT * FROM optimization_actions
WHERE status = 'open' AND (claim_expires_at IS NULL OR claim_expires_at < strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
ORDER BY priority_score DESC, created_at ASC;
