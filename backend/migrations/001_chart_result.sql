-- Production PostgreSQL schema. The local development BFF mirrors these resources in SQLite.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE anonymous_sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  token_hash text NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE birth_profiles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id uuid NOT NULL REFERENCES anonymous_sessions(id),
  encrypted_payload bytea NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE charts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id uuid NOT NULL REFERENCES anonymous_sessions(id),
  birth_profile_id uuid NOT NULL REFERENCES birth_profiles(id),
  idempotency_key text NOT NULL,
  status text NOT NULL,
  birth_public jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(session_id, idempotency_key)
);

CREATE TABLE chart_access (
  chart_id uuid NOT NULL REFERENCES charts(id),
  session_id uuid NOT NULL REFERENCES anonymous_sessions(id),
  granted_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(chart_id, session_id)
);

CREATE TABLE chart_snapshots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  chart_id uuid NOT NULL REFERENCES charts(id),
  revision integer NOT NULL,
  schema_version text NOT NULL,
  payload jsonb NOT NULL,
  checksum text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(chart_id, revision),
  UNIQUE(checksum)
);

CREATE TABLE calculation_sections (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  snapshot_id uuid NOT NULL REFERENCES chart_snapshots(id),
  section text NOT NULL,
  status text NOT NULL,
  payload jsonb,
  error_code text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(snapshot_id, section)
);

CREATE TABLE evidence_facts (
  id text PRIMARY KEY,
  snapshot_id uuid NOT NULL REFERENCES chart_snapshots(id),
  payload jsonb NOT NULL,
  checksum text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX evidence_facts_snapshot_idx ON evidence_facts(snapshot_id);

CREATE TABLE jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  chart_id uuid NOT NULL REFERENCES charts(id),
  job_type text NOT NULL,
  status text NOT NULL,
  priority smallint NOT NULL DEFAULT 10,
  attempts integer NOT NULL DEFAULT 0,
  input_checksum text,
  error jsonb,
  scheduled_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX jobs_claim_idx ON jobs(status, priority DESC, scheduled_at, created_at);

CREATE TABLE agent_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  chart_id uuid NOT NULL REFERENCES charts(id),
  job_id uuid NOT NULL REFERENCES jobs(id),
  provider text NOT NULL,
  prompt_version text NOT NULL,
  input_checksum text NOT NULL,
  output_checksum text,
  status text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz
);

CREATE TABLE interpretation_bundles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  snapshot_id uuid NOT NULL REFERENCES chart_snapshots(id),
  access_level text NOT NULL,
  schema_version text NOT NULL,
  payload jsonb NOT NULL,
  evidence_checksum text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(snapshot_id, access_level)
);

CREATE TABLE purchases (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  chart_id uuid NOT NULL REFERENCES charts(id),
  idempotency_key text NOT NULL,
  email_ciphertext bytea,
  provider text NOT NULL,
  provider_payment_id text,
  status text NOT NULL,
  amount_minor integer NOT NULL CHECK (amount_minor = 99000),
  currency char(3) NOT NULL CHECK (currency = 'RUB'),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(chart_id, idempotency_key)
);

CREATE TABLE payment_events (
  provider text NOT NULL,
  provider_event_id text NOT NULL,
  payload_checksum text NOT NULL,
  received_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(provider, provider_event_id)
);

CREATE TABLE entitlements (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  chart_id uuid NOT NULL REFERENCES charts(id),
  product_code text NOT NULL CHECK (product_code = 'report_full'),
  purchase_id uuid REFERENCES purchases(id),
  granted_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(chart_id, product_code)
);

CREATE TABLE reports (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  chart_id uuid NOT NULL REFERENCES charts(id),
  status text NOT NULL,
  object_key text,
  checksum text,
  size_bytes integer,
  pages integer,
  error_code text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(chart_id)
);

CREATE TABLE saved_questions (
  chart_id uuid NOT NULL REFERENCES charts(id),
  question_id text NOT NULL,
  saved boolean NOT NULL DEFAULT false,
  reflection_status text NOT NULL DEFAULT 'saved' CHECK (reflection_status IN ('saved', 'thinking', 'return_later')),
  note_ciphertext bytea,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(chart_id, question_id)
);

CREATE TABLE magic_links (
  token_hash text PRIMARY KEY,
  chart_id uuid NOT NULL REFERENCES charts(id),
  scope text NOT NULL CHECK (scope = 'read_chart'),
  expires_at timestamptz NOT NULL,
  used_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE outbox_events (
  id bigserial PRIMARY KEY,
  chart_id uuid NOT NULL REFERENCES charts(id),
  event text NOT NULL,
  payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  delivered_at timestamptz
);
CREATE INDEX outbox_chart_idx ON outbox_events(chart_id, id);
