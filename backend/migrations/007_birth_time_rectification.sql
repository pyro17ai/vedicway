-- Paid deterministic birth-time rectification. Apply after 006_magic_link_confirmation.sql.

CREATE TABLE IF NOT EXISTS rectifications (
  chart_id uuid PRIMARY KEY REFERENCES charts(id) ON DELETE CASCADE,
  status text NOT NULL CHECK (
    status IN ('awaiting_answers', 'queued', 'running', 'ready', 'failed')
  ),
  answers_ciphertext bytea,
  result_ciphertext bytea,
  error_code text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS rectifications_status_idx
  ON rectifications(status, updated_at);
