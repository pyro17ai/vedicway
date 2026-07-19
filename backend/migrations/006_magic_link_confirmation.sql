-- Two-step confirmation for emailed chart and PDF access links.
-- Apply after 005_recovery_retention.sql.

CREATE TABLE IF NOT EXISTS magic_link_confirmations (
  nonce_hash text PRIMARY KEY,
  magic_token_hash text NOT NULL REFERENCES magic_links(token_hash) ON DELETE CASCADE,
  csrf_token_hash text NOT NULL,
  expires_at timestamptz NOT NULL,
  used_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS magic_link_confirmations_token_idx
  ON magic_link_confirmations(magic_token_hash, created_at DESC);
