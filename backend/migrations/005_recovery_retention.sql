-- Recovery email, DSAR intake and single-node lifecycle audit.
-- Apply after 004_runtime_rate_limits.sql.

ALTER TABLE birth_profiles ADD COLUMN IF NOT EXISTS deleted_at timestamptz;
ALTER TABLE charts ADD COLUMN IF NOT EXISTS soft_deleted_at timestamptz;
ALTER TABLE purchases ADD COLUMN IF NOT EXISTS email_lookup_hmac text;
CREATE INDEX IF NOT EXISTS purchases_email_lookup_idx
  ON purchases(email_lookup_hmac) WHERE email_lookup_hmac IS NOT NULL;
ALTER TABLE magic_links DROP CONSTRAINT IF EXISTS magic_links_scope_check;
ALTER TABLE magic_links ADD CONSTRAINT magic_links_scope_check
  CHECK (scope IN ('read_chart', 'download_pdf'));
ALTER TABLE magic_links ADD COLUMN IF NOT EXISTS render_request_id uuid REFERENCES pdf_render_requests(id);

CREATE TABLE IF NOT EXISTS privacy_requests (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  request_type text NOT NULL CHECK (request_type IN ('access', 'erase', 'withdraw')),
  email_lookup_hmac text NOT NULL,
  email_ciphertext bytea NOT NULL,
  status text NOT NULL DEFAULT 'received',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS privacy_requests_lookup_idx
  ON privacy_requests(email_lookup_hmac, created_at DESC);

CREATE TABLE IF NOT EXISTS erasure_tombstones (
  chart_id uuid PRIMARY KEY,
  reason text NOT NULL,
  financial_records_retained boolean NOT NULL,
  report_paths jsonb NOT NULL DEFAULT '[]'::jsonb,
  status text NOT NULL CHECK (status IN ('pending_files', 'complete')),
  created_at timestamptz NOT NULL DEFAULT now(),
  files_deleted_at timestamptz,
  last_error_code text
);

CREATE TABLE IF NOT EXISTS retention_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  mode text NOT NULL CHECK (mode IN ('dry-run', 'apply')),
  cutoff_at timestamptz NOT NULL,
  candidates integer NOT NULL DEFAULT 0,
  erased integer NOT NULL DEFAULT 0,
  failed integer NOT NULL DEFAULT 0,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz
);

CREATE TABLE IF NOT EXISTS email_deliveries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  purpose text NOT NULL CHECK (purpose IN ('access_recovery', 'purchase_ready')),
  request_key text NOT NULL UNIQUE,
  email_lookup_hmac text,
  purchase_id uuid REFERENCES purchases(id),
  chart_id uuid REFERENCES charts(id),
  render_request_id uuid REFERENCES pdf_render_requests(id),
  status text NOT NULL,
  attempts integer NOT NULL DEFAULT 0,
  scheduled_at timestamptz NOT NULL DEFAULT now(),
  provider_message_id text,
  error_code text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS email_deliveries_queue_idx
  ON email_deliveries(status, scheduled_at, created_at);
