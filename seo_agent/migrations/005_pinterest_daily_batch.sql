DROP INDEX IF EXISTS one_distribution_media_role_per_draft;

CREATE INDEX pinterest_distribution_media_by_draft
ON article_media(draft_id, created_at)
WHERE distribution_role = 'pinterest';
