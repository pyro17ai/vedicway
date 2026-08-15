CREATE TABLE schema_migrations (
    version text PRIMARY KEY,
    checksum text NOT NULL,
    applied_at text NOT NULL
);

CREATE TABLE settings (
    key text PRIMARY KEY,
    value_json text NOT NULL,
    updated_at text NOT NULL
);

CREATE TABLE source_documents (
    id text PRIMARY KEY,
    source_kind text NOT NULL CHECK (source_kind IN ('web', 'mcp', 'repository', 'editorial')),
    source_key text NOT NULL,
    url text,
    status text NOT NULL CHECK (status IN ('active', 'stale', 'rejected')),
    checksum text NOT NULL,
    retrieved_at text NOT NULL,
    payload_json text NOT NULL,
    UNIQUE (source_kind, source_key, checksum)
);

CREATE TABLE cron_runs (
    id text PRIMARY KEY,
    job_name text NOT NULL,
    schedule_token text NOT NULL,
    status text NOT NULL CHECK (status IN ('running', 'completed', 'failed', 'blocked', 'skipped')),
    owner_token text NOT NULL,
    started_at text NOT NULL,
    heartbeat_at text NOT NULL,
    finished_at text,
    outcome text,
    error_code text,
    error_detail text,
    UNIQUE (job_name, schedule_token)
);

CREATE UNIQUE INDEX one_running_cron_per_job
ON cron_runs(job_name) WHERE status = 'running';

CREATE TABLE skill_runs (
    id text PRIMARY KEY,
    cron_run_id text NOT NULL REFERENCES cron_runs(id) ON DELETE CASCADE,
    skill_name text NOT NULL,
    attempt_token text NOT NULL UNIQUE,
    status text NOT NULL CHECK (status IN ('running', 'completed', 'failed', 'blocked', 'skipped')),
    input_hash text NOT NULL,
    output_json text,
    started_at text NOT NULL,
    finished_at text
);

CREATE TABLE raw_tool_responses (
    id text PRIMARY KEY,
    cron_run_id text NOT NULL REFERENCES cron_runs(id) ON DELETE CASCADE,
    provider text NOT NULL CHECK (provider IN ('yandex-search', 'wordstat', 'webmaster', 'metrika', 'site', 'dzen')),
    tool_name text NOT NULL,
    request_hash text NOT NULL,
    response_json text NOT NULL,
    observed_at text NOT NULL,
    expires_at text,
    UNIQUE (provider, tool_name, request_hash, observed_at)
);

CREATE TABLE keyword_queries (
    id text PRIMARY KEY,
    phrase text NOT NULL,
    region_id text NOT NULL,
    source text NOT NULL CHECK (source IN ('wordstat', 'webmaster', 'metrika', 'seed')),
    intent text CHECK (intent IS NULL OR intent IN ('informational', 'commercial', 'navigational')),
    metrics_json text NOT NULL,
    observed_at text NOT NULL
);
CREATE UNIQUE INDEX keyword_queries_identity_idx
ON keyword_queries(lower(phrase), region_id, source, observed_at);

CREATE TABLE serp_snapshots (
    id text PRIMARY KEY,
    query_id text NOT NULL REFERENCES keyword_queries(id) ON DELETE CASCADE,
    region_id text NOT NULL,
    requested_at text NOT NULL,
    result_json text NOT NULL,
    checksum text NOT NULL,
    UNIQUE (query_id, requested_at)
);

CREATE TABLE keyword_clusters (
    id text PRIMARY KEY,
    slug text NOT NULL UNIQUE,
    title text NOT NULL,
    intent text NOT NULL CHECK (intent IN ('informational', 'commercial', 'navigational')),
    status text NOT NULL CHECK (status IN ('candidate', 'ready', 'claimed', 'briefed', 'rejected', 'published')),
    priority_score double precision NOT NULL DEFAULT 0,
    rationale text NOT NULL DEFAULT '',
    claim_token text UNIQUE,
    claim_expires_at text,
    created_at text NOT NULL,
    updated_at text NOT NULL
);

CREATE TABLE cluster_queries (
    cluster_id text NOT NULL REFERENCES keyword_clusters(id) ON DELETE CASCADE,
    query_id text NOT NULL REFERENCES keyword_queries(id) ON DELETE CASCADE,
    is_primary integer NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
    PRIMARY KEY (cluster_id, query_id)
);

CREATE UNIQUE INDEX one_primary_query_per_cluster
ON cluster_queries(cluster_id) WHERE is_primary = 1;

CREATE TABLE content_briefs (
    id text PRIMARY KEY,
    cluster_id text NOT NULL UNIQUE REFERENCES keyword_clusters(id) ON DELETE RESTRICT,
    status text NOT NULL CHECK (status IN ('draft', 'approved', 'rejected', 'consumed')),
    title text NOT NULL,
    primary_query text NOT NULL,
    audience_problem text NOT NULL,
    search_intent text NOT NULL,
    outline_json text NOT NULL,
    evidence_json text NOT NULL,
    internal_links_json text NOT NULL,
    prohibited_claims_json text NOT NULL,
    checksum text NOT NULL,
    created_at text NOT NULL,
    approved_at text
);

CREATE TABLE article_drafts (
    id text PRIMARY KEY,
    brief_id text NOT NULL REFERENCES content_briefs(id) ON DELETE RESTRICT,
    slug text NOT NULL UNIQUE,
    status text NOT NULL CHECK (status IN ('draft', 'editing', 'quality_failed', 'approved', 'publishing', 'published', 'rejected')),
    title text NOT NULL,
    excerpt text NOT NULL,
    content_markdown text NOT NULL,
    seo_title text NOT NULL,
    meta_description text NOT NULL,
    focus_keyphrase text NOT NULL,
    category text NOT NULL,
    author_name text NOT NULL,
    content_hash text NOT NULL,
    quality_report_json text,
    claim_token text UNIQUE,
    claim_expires_at text,
    created_at text NOT NULL,
    updated_at text NOT NULL,
    approved_at text
);

CREATE TABLE article_media (
    id text PRIMARY KEY,
    draft_id text NOT NULL REFERENCES article_drafts(id) ON DELETE CASCADE,
    purpose text NOT NULL CHECK (purpose IN ('cover', 'body')),
    local_path text NOT NULL,
    alt_text text NOT NULL,
    title text NOT NULL DEFAULT '',
    caption text NOT NULL DEFAULT '',
    source_kind text NOT NULL CHECK (source_kind IN ('generated', 'licensed', 'owned')),
    source_url text,
    license_note text NOT NULL,
    checksum text NOT NULL,
    backend_media_id text,
    public_url text,
    created_at text NOT NULL,
    UNIQUE (draft_id, checksum, purpose)
);

CREATE UNIQUE INDEX one_cover_per_draft
ON article_media(draft_id) WHERE purpose = 'cover';

CREATE TABLE publication_attempts (
    id text PRIMARY KEY,
    draft_id text NOT NULL REFERENCES article_drafts(id) ON DELETE RESTRICT,
    target text NOT NULL CHECK (target IN ('site', 'dzen')),
    attempt_no integer NOT NULL CHECK (attempt_no > 0),
    idempotency_key text NOT NULL,
    attempt_token text NOT NULL UNIQUE,
    status text NOT NULL CHECK (status IN ('succeeded', 'failed', 'blocked')),
    content_hash text NOT NULL,
    request_hash text NOT NULL,
    response_json text,
    started_at text NOT NULL,
    finished_at text,
    UNIQUE (draft_id, target, attempt_no)
);

CREATE TABLE publications (
    id text PRIMARY KEY,
    draft_id text NOT NULL REFERENCES article_drafts(id) ON DELETE RESTRICT,
    target text NOT NULL CHECK (target IN ('site', 'dzen')),
    status text NOT NULL CHECK (status IN ('published', 'verified', 'removed')),
    public_url text NOT NULL,
    external_id text,
    content_hash text NOT NULL,
    request_hash text NOT NULL,
    evidence_json text NOT NULL,
    published_at text NOT NULL,
    verified_at text,
    UNIQUE (draft_id, target)
);

CREATE FUNCTION publication_terminal_state_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF (OLD.status = 'published' AND NEW.status NOT IN ('published', 'verified', 'removed'))
       OR (OLD.status = 'verified' AND NEW.status NOT IN ('verified', 'removed')) THEN
        RAISE EXCEPTION 'publication status cannot regress' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER publication_terminal_state_guard
BEFORE UPDATE OF status ON publications
FOR EACH ROW EXECUTE FUNCTION publication_terminal_state_guard();

CREATE TABLE performance_snapshots (
    id text PRIMARY KEY,
    publication_id text NOT NULL REFERENCES publications(id) ON DELETE CASCADE,
    window_start text NOT NULL,
    window_end text NOT NULL,
    webmaster_json text NOT NULL,
    metrika_json text NOT NULL,
    captured_at text NOT NULL,
    UNIQUE (publication_id, window_start, window_end)
);

CREATE TABLE optimization_actions (
    id text PRIMARY KEY,
    publication_id text NOT NULL REFERENCES publications(id) ON DELETE CASCADE,
    action_type text NOT NULL CHECK (action_type IN ('rewrite', 'expand', 'internal_links', 'title_test', 'recrawl', 'hold')),
    status text NOT NULL CHECK (status IN ('open', 'claimed', 'completed', 'rejected')),
    priority_score double precision NOT NULL DEFAULT 0,
    hypothesis text NOT NULL,
    success_metric text NOT NULL,
    evidence_json text NOT NULL,
    baseline_request_hash text NOT NULL,
    result_evidence_json text,
    claim_token text UNIQUE,
    claim_expires_at text,
    created_at text NOT NULL,
    completed_at text
);

CREATE UNIQUE INDEX one_active_action_per_type
ON optimization_actions(publication_id, action_type)
WHERE status IN ('open', 'claimed');

CREATE TABLE job_results (
    id text PRIMARY KEY,
    cron_run_id text NOT NULL UNIQUE REFERENCES cron_runs(id) ON DELETE CASCADE,
    outcome text NOT NULL CHECK (outcome IN ('completed', 'blocked', 'skipped')),
    summary text NOT NULL,
    artifact_json text NOT NULL,
    created_at text NOT NULL
);

CREATE TABLE audit_events (
    id bigserial PRIMARY KEY,
    occurred_at text NOT NULL,
    actor text NOT NULL,
    action text NOT NULL,
    entity_type text NOT NULL,
    entity_id text,
    detail_json text NOT NULL
);

CREATE VIEW v_ready_clusters AS
SELECT * FROM keyword_clusters
WHERE status = 'ready'
  AND (claim_expires_at IS NULL OR claim_expires_at < to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'))
ORDER BY priority_score DESC, created_at ASC;

CREATE VIEW v_ready_drafts AS
SELECT d.*, m.id AS cover_id, m.local_path AS cover_path
FROM article_drafts d
JOIN article_media m ON m.draft_id = d.id AND m.purpose = 'cover'
WHERE d.status = 'approved'
  AND (d.claim_expires_at IS NULL OR d.claim_expires_at < to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'))
ORDER BY d.approved_at ASC;

CREATE VIEW v_due_lifecycle AS
SELECT p.*
FROM publications p
LEFT JOIN performance_snapshots s ON s.publication_id = p.id
WHERE p.target = 'site' AND p.status IN ('published', 'verified')
GROUP BY p.id
HAVING MAX(s.captured_at) IS NULL
    OR MAX(s.captured_at) < to_char(clock_timestamp() AT TIME ZONE 'UTC' - interval '7 days', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"');

CREATE VIEW v_open_actions AS
SELECT * FROM optimization_actions
WHERE status = 'open'
  AND (claim_expires_at IS NULL OR claim_expires_at < to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'))
ORDER BY priority_score DESC, created_at ASC;
