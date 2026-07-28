ALTER TABLE keyword_clusters
ADD COLUMN claim_run_id TEXT REFERENCES cron_runs(id) ON DELETE SET NULL;

ALTER TABLE article_drafts
ADD COLUMN claim_run_id TEXT REFERENCES cron_runs(id) ON DELETE SET NULL;

ALTER TABLE optimization_actions
ADD COLUMN claim_run_id TEXT REFERENCES cron_runs(id) ON DELETE SET NULL;

CREATE INDEX keyword_clusters_claim_run_idx ON keyword_clusters(claim_run_id);
CREATE INDEX article_drafts_claim_run_idx ON article_drafts(claim_run_id);
CREATE INDEX optimization_actions_claim_run_idx ON optimization_actions(claim_run_id);
