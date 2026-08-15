-- PostgreSQL runtime schema used by vedicway_backend.store.
-- The earlier public tables were deployment scaffolding and remain untouched for safe upgrades.

CREATE SCHEMA IF NOT EXISTS runtime;

CREATE TABLE IF NOT EXISTS runtime.anonymous_sessions (
  id text PRIMARY KEY,
  token_hash text NOT NULL UNIQUE,
  created_at text NOT NULL,
  last_seen_at text NOT NULL
);

CREATE TABLE IF NOT EXISTS runtime.birth_profiles (
  id text PRIMARY KEY,
  session_id text NOT NULL REFERENCES runtime.anonymous_sessions(id),
  encrypted_payload bytea NOT NULL,
  created_at text NOT NULL,
  deleted_at text
);

CREATE TABLE IF NOT EXISTS runtime.charts (
  id text PRIMARY KEY,
  session_id text NOT NULL REFERENCES runtime.anonymous_sessions(id),
  birth_profile_id text NOT NULL REFERENCES runtime.birth_profiles(id),
  idempotency_key text NOT NULL,
  status text NOT NULL,
  birth_public_json text NOT NULL,
  snapshot_json text,
  evidence_json text,
  free_bundle_json text,
  paid_bundle_json text,
  created_at text NOT NULL,
  updated_at text NOT NULL,
  soft_deleted_at text,
  UNIQUE (session_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS runtime.chart_access (
  chart_id text NOT NULL REFERENCES runtime.charts(id),
  session_id text NOT NULL REFERENCES runtime.anonymous_sessions(id),
  granted_at text NOT NULL,
  PRIMARY KEY (chart_id, session_id)
);

CREATE TABLE IF NOT EXISTS runtime.jobs (
  id text PRIMARY KEY,
  chart_id text NOT NULL REFERENCES runtime.charts(id),
  job_type text NOT NULL,
  status text NOT NULL,
  priority integer NOT NULL,
  attempts integer NOT NULL DEFAULT 0,
  input_checksum text,
  payload_json text,
  error_json text,
  scheduled_at text NOT NULL,
  started_at text,
  finished_at text,
  created_at text NOT NULL,
  updated_at text NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_queue_idx
  ON runtime.jobs(status, priority DESC, scheduled_at, created_at);

CREATE TABLE IF NOT EXISTS runtime.outbox_events (
  id bigserial PRIMARY KEY,
  chart_id text NOT NULL REFERENCES runtime.charts(id),
  event text NOT NULL,
  payload_json text NOT NULL,
  created_at text NOT NULL
);
CREATE INDEX IF NOT EXISTS outbox_chart_idx ON runtime.outbox_events(chart_id, id);

CREATE TABLE IF NOT EXISTS runtime.agent_runs (
  id text PRIMARY KEY,
  chart_id text NOT NULL REFERENCES runtime.charts(id),
  job_id text NOT NULL REFERENCES runtime.jobs(id),
  provider text NOT NULL,
  prompt_version text NOT NULL,
  input_checksum text NOT NULL,
  output_checksum text,
  status text NOT NULL,
  created_at text NOT NULL,
  finished_at text
);

CREATE TABLE IF NOT EXISTS runtime.purchases (
  id text PRIMARY KEY,
  chart_id text NOT NULL REFERENCES runtime.charts(id),
  idempotency_key text NOT NULL,
  email_ciphertext bytea,
  email_lookup_hmac text,
  product_code text NOT NULL DEFAULT 'full_report_v1',
  provider text NOT NULL,
  provider_idempotency_key text,
  provider_payment_id text,
  checkout_url text,
  status text NOT NULL,
  provider_status text,
  provider_payload_json text,
  failure_code text,
  amount_minor integer NOT NULL,
  paid_amount_minor integer,
  refunded_amount_minor integer NOT NULL DEFAULT 0,
  currency text NOT NULL,
  offer_version text,
  last_reconciled_at text,
  paid_at text,
  canceled_at text,
  receipt_registration text,
  created_at text NOT NULL,
  updated_at text NOT NULL,
  UNIQUE (chart_id, idempotency_key)
);
CREATE UNIQUE INDEX IF NOT EXISTS purchases_provider_key_idx
  ON runtime.purchases(provider, provider_idempotency_key);
CREATE INDEX IF NOT EXISTS purchases_active_idx
  ON runtime.purchases(chart_id, product_code, status, created_at);
CREATE INDEX IF NOT EXISTS purchases_email_lookup_idx
  ON runtime.purchases(email_lookup_hmac);

CREATE TABLE IF NOT EXISTS runtime.payment_events (
  provider text NOT NULL,
  provider_event_id text NOT NULL,
  event_type text,
  object_id text,
  payload_checksum text NOT NULL,
  received_at text NOT NULL,
  PRIMARY KEY (provider, provider_event_id)
);

CREATE TABLE IF NOT EXISTS runtime.payment_incidents (
  id text PRIMARY KEY,
  purchase_id text REFERENCES runtime.purchases(id),
  category text NOT NULL,
  detail_json text NOT NULL,
  trace_id text,
  created_at text NOT NULL
);
CREATE INDEX IF NOT EXISTS payment_incidents_purchase_idx
  ON runtime.payment_incidents(purchase_id, created_at);

CREATE TABLE IF NOT EXISTS runtime.entitlements (
  id text PRIMARY KEY,
  chart_id text NOT NULL REFERENCES runtime.charts(id),
  product_code text NOT NULL,
  purchase_id text REFERENCES runtime.purchases(id),
  granted_at text NOT NULL,
  revoked_at text,
  revocation_reason text,
  UNIQUE (chart_id, product_code)
);

CREATE TABLE IF NOT EXISTS runtime.rectifications (
  chart_id text PRIMARY KEY REFERENCES runtime.charts(id),
  status text NOT NULL,
  answers_ciphertext bytea,
  result_ciphertext bytea,
  error_code text,
  created_at text NOT NULL,
  updated_at text NOT NULL
);
CREATE INDEX IF NOT EXISTS rectifications_status_idx
  ON runtime.rectifications(status, updated_at);

CREATE TABLE IF NOT EXISTS runtime.refunds (
  id text PRIMARY KEY,
  purchase_id text NOT NULL REFERENCES runtime.purchases(id),
  idempotency_key text NOT NULL,
  provider_idempotency_key text NOT NULL UNIQUE,
  provider_refund_id text UNIQUE,
  status text NOT NULL,
  amount_minor integer NOT NULL,
  currency text NOT NULL,
  reason_ciphertext bytea,
  actor_fingerprint text NOT NULL,
  failure_code text,
  receipt_registration text,
  created_at text NOT NULL,
  updated_at text NOT NULL,
  UNIQUE (purchase_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS refunds_purchase_idx
  ON runtime.refunds(purchase_id, status, created_at);

CREATE TABLE IF NOT EXISTS runtime.payment_operations (
  id text PRIMARY KEY,
  action text NOT NULL,
  purchase_id text REFERENCES runtime.purchases(id),
  refund_id text REFERENCES runtime.refunds(id),
  actor_fingerprint text NOT NULL,
  source_ip text NOT NULL,
  trace_id text NOT NULL,
  reason_ciphertext bytea,
  amount_minor integer,
  result text NOT NULL,
  detail_json text NOT NULL,
  created_at text NOT NULL
);
CREATE INDEX IF NOT EXISTS payment_operations_purchase_idx
  ON runtime.payment_operations(purchase_id, created_at);

CREATE TABLE IF NOT EXISTS runtime.reports (
  id text PRIMARY KEY,
  chart_id text NOT NULL REFERENCES runtime.charts(id),
  status text NOT NULL,
  path text,
  checksum text,
  size_bytes bigint,
  pages integer,
  error_code text,
  render_request_id text,
  preferences_checksum text,
  created_at text NOT NULL,
  updated_at text NOT NULL,
  UNIQUE (chart_id)
);

CREATE TABLE IF NOT EXISTS runtime.pdf_render_requests (
  id text PRIMARY KEY,
  chart_id text NOT NULL REFERENCES runtime.charts(id),
  job_id text,
  preferences_json text NOT NULL,
  preferences_checksum text NOT NULL,
  status text NOT NULL,
  path text,
  checksum text,
  size_bytes bigint,
  pages integer,
  error_code text,
  created_at text NOT NULL,
  updated_at text NOT NULL
);
CREATE INDEX IF NOT EXISTS pdf_render_requests_chart_idx
  ON runtime.pdf_render_requests(chart_id, created_at DESC);

CREATE TABLE IF NOT EXISTS runtime.rate_limit_events (
  bucket_key text NOT NULL,
  occurred_at double precision NOT NULL
);
CREATE INDEX IF NOT EXISTS rate_limit_events_bucket_idx
  ON runtime.rate_limit_events(bucket_key, occurred_at);

CREATE TABLE IF NOT EXISTS runtime.saved_questions (
  chart_id text NOT NULL REFERENCES runtime.charts(id),
  question_id text NOT NULL,
  saved integer NOT NULL DEFAULT 0,
  reflection_status text NOT NULL DEFAULT 'saved',
  note_ciphertext bytea,
  updated_at text NOT NULL,
  PRIMARY KEY (chart_id, question_id)
);

CREATE TABLE IF NOT EXISTS runtime.magic_links (
  token_hash text PRIMARY KEY,
  chart_id text NOT NULL REFERENCES runtime.charts(id),
  scope text NOT NULL,
  render_request_id text,
  expires_at text NOT NULL,
  used_at text,
  created_at text NOT NULL
);

CREATE TABLE IF NOT EXISTS runtime.magic_link_confirmations (
  nonce_hash text PRIMARY KEY,
  magic_token_hash text NOT NULL
    REFERENCES runtime.magic_links(token_hash) ON DELETE CASCADE,
  csrf_token_hash text NOT NULL,
  expires_at text NOT NULL,
  used_at text,
  created_at text NOT NULL
);
CREATE INDEX IF NOT EXISTS magic_link_confirmations_token_idx
  ON runtime.magic_link_confirmations(magic_token_hash, created_at DESC);

CREATE TABLE IF NOT EXISTS runtime.privacy_requests (
  id text PRIMARY KEY,
  request_type text NOT NULL,
  email_lookup_hmac text NOT NULL,
  email_ciphertext bytea NOT NULL,
  status text NOT NULL,
  created_at text NOT NULL,
  updated_at text NOT NULL
);
CREATE INDEX IF NOT EXISTS privacy_requests_lookup_idx
  ON runtime.privacy_requests(email_lookup_hmac, created_at DESC);

CREATE TABLE IF NOT EXISTS runtime.erasure_tombstones (
  chart_id text PRIMARY KEY,
  reason text NOT NULL,
  financial_records_retained integer NOT NULL,
  report_paths_json text NOT NULL,
  status text NOT NULL,
  created_at text NOT NULL,
  files_deleted_at text,
  last_error_code text
);

CREATE TABLE IF NOT EXISTS runtime.retention_runs (
  id text PRIMARY KEY,
  mode text NOT NULL,
  cutoff_at text NOT NULL,
  candidates integer NOT NULL,
  erased integer NOT NULL,
  failed integer NOT NULL,
  detail_json text NOT NULL,
  created_at text NOT NULL,
  finished_at text
);

CREATE TABLE IF NOT EXISTS runtime.email_deliveries (
  id text PRIMARY KEY,
  purpose text NOT NULL,
  request_key text NOT NULL UNIQUE,
  email_lookup_hmac text,
  purchase_id text REFERENCES runtime.purchases(id),
  chart_id text REFERENCES runtime.charts(id),
  render_request_id text,
  status text NOT NULL,
  attempts integer NOT NULL DEFAULT 0,
  scheduled_at text NOT NULL,
  provider_message_id text,
  error_code text,
  created_at text NOT NULL,
  updated_at text NOT NULL
);
CREATE INDEX IF NOT EXISTS email_deliveries_queue_idx
  ON runtime.email_deliveries(status, scheduled_at, created_at);
