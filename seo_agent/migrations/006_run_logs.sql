CREATE TABLE run_logs (
    cron_run_id text PRIMARY KEY REFERENCES cron_runs(id) ON DELETE CASCADE,
    log_text text NOT NULL CHECK (
        char_length(btrim(log_text)) BETWEEN 1 AND 4000
    )
);
