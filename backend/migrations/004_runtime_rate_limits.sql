-- Shared rate-limit ledger. Store only HMAC/SHA-256 bucket keys, never raw client IPs.
CREATE TABLE IF NOT EXISTS rate_limit_events (
  bucket_key text NOT NULL,
  occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS rate_limit_events_bucket_idx
  ON rate_limit_events(bucket_key, occurred_at);
