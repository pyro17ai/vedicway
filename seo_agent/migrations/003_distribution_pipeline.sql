ALTER TABLE article_media
ADD COLUMN distribution_role text
CHECK (distribution_role IS NULL OR distribution_role IN ('vk', 'pinterest'));

CREATE UNIQUE INDEX one_distribution_media_role_per_draft
ON article_media(draft_id, distribution_role)
WHERE distribution_role IS NOT NULL;

CREATE TABLE distribution_items (
    id text PRIMARY KEY,
    source_publication_id text NOT NULL REFERENCES publications(id) ON DELETE RESTRICT,
    platform text NOT NULL CHECK (platform IN ('vk', 'pinterest')),
    kind text NOT NULL CHECK (kind IN ('article_digest', 'astrology_card')),
    title text NOT NULL,
    body text NOT NULL,
    target_url text NOT NULL,
    media_id text NOT NULL REFERENCES article_media(id) ON DELETE RESTRICT,
    media_public_url text NOT NULL,
    media_width integer NOT NULL CHECK (media_width > 0),
    media_height integer NOT NULL CHECK (media_height > 0),
    alt_text text NOT NULL,
    metadata_json text NOT NULL,
    content_hash text NOT NULL,
    status text NOT NULL CHECK (status IN ('approved', 'publishing', 'published', 'blocked', 'failed')),
    claim_token text UNIQUE,
    claim_expires_at text,
    claim_run_id text REFERENCES cron_runs(id) ON DELETE SET NULL,
    created_at text NOT NULL,
    updated_at text NOT NULL,
    published_at text,
    UNIQUE (platform, content_hash)
);

CREATE INDEX distribution_ready_queue
ON distribution_items(platform, status, created_at);

CREATE TABLE distribution_attempts (
    id text PRIMARY KEY,
    item_id text NOT NULL REFERENCES distribution_items(id) ON DELETE CASCADE,
    platform text NOT NULL CHECK (platform IN ('vk', 'pinterest')),
    attempt_no integer NOT NULL CHECK (attempt_no > 0),
    attempt_token text NOT NULL UNIQUE,
    idempotency_key text NOT NULL,
    status text NOT NULL CHECK (status IN ('succeeded', 'failed', 'blocked')),
    request_hash text NOT NULL,
    response_json text NOT NULL,
    external_id text,
    external_url text,
    created_at text NOT NULL,
    UNIQUE (item_id, attempt_no)
);

CREATE TABLE distribution_publications (
    id text PRIMARY KEY,
    item_id text NOT NULL UNIQUE REFERENCES distribution_items(id) ON DELETE RESTRICT,
    platform text NOT NULL CHECK (platform IN ('vk', 'pinterest')),
    status text NOT NULL CHECK (status IN ('published', 'verified')),
    external_id text NOT NULL,
    external_url text NOT NULL,
    content_hash text NOT NULL,
    request_hash text NOT NULL,
    evidence_json text NOT NULL,
    published_at text NOT NULL
);

CREATE VIEW v_ready_distribution AS
SELECT * FROM distribution_items
WHERE status = 'approved'
  AND (claim_expires_at IS NULL OR claim_expires_at < to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'))
ORDER BY created_at ASC;

CREATE FUNCTION prevent_distribution_publication_regression() RETURNS trigger AS $$
BEGIN
    IF OLD.status = 'verified' AND (
        NEW.status <> 'verified'
        OR NEW.external_id <> OLD.external_id
        OR NEW.external_url <> OLD.external_url
        OR NEW.content_hash <> OLD.content_hash
        OR NEW.request_hash <> OLD.request_hash
        OR NEW.evidence_json <> OLD.evidence_json
    ) THEN
        RAISE EXCEPTION 'verified distribution publication cannot regress';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER distribution_publication_terminal_update
BEFORE UPDATE ON distribution_publications
FOR EACH ROW EXECUTE FUNCTION prevent_distribution_publication_regression();

CREATE FUNCTION prevent_distribution_publication_delete() RETURNS trigger AS $$
BEGIN
    IF OLD.status = 'verified' THEN
        RAISE EXCEPTION 'verified distribution publication cannot be deleted';
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER distribution_publication_terminal_delete
BEFORE DELETE ON distribution_publications
FOR EACH ROW EXECUTE FUNCTION prevent_distribution_publication_delete();
