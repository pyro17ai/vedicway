-- Durable YooKassa payment lifecycle. Apply after 001_chart_result.sql.

ALTER TABLE purchases ADD COLUMN IF NOT EXISTS product_code text NOT NULL DEFAULT 'full_report_v1';
ALTER TABLE purchases ADD COLUMN IF NOT EXISTS provider_idempotency_key text;
ALTER TABLE purchases ADD COLUMN IF NOT EXISTS checkout_url text;
ALTER TABLE purchases ADD COLUMN IF NOT EXISTS provider_status text;
ALTER TABLE purchases ADD COLUMN IF NOT EXISTS provider_payload jsonb;
ALTER TABLE purchases ADD COLUMN IF NOT EXISTS failure_code text;
ALTER TABLE purchases ADD COLUMN IF NOT EXISTS paid_amount_minor integer;
ALTER TABLE purchases ADD COLUMN IF NOT EXISTS refunded_amount_minor integer NOT NULL DEFAULT 0;
ALTER TABLE purchases ADD COLUMN IF NOT EXISTS offer_version text;
ALTER TABLE purchases ADD COLUMN IF NOT EXISTS last_reconciled_at timestamptz;
ALTER TABLE purchases ADD COLUMN IF NOT EXISTS paid_at timestamptz;
ALTER TABLE purchases ADD COLUMN IF NOT EXISTS canceled_at timestamptz;
ALTER TABLE purchases ADD COLUMN IF NOT EXISTS receipt_registration text;

CREATE UNIQUE INDEX IF NOT EXISTS purchases_provider_key_idx
  ON purchases(provider, provider_idempotency_key)
  WHERE provider_idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS purchases_active_idx
  ON purchases(chart_id, product_code, status, created_at DESC);

ALTER TABLE payment_events ADD COLUMN IF NOT EXISTS event_type text;
ALTER TABLE payment_events ADD COLUMN IF NOT EXISTS object_id text;

ALTER TABLE entitlements ADD COLUMN IF NOT EXISTS revoked_at timestamptz;
ALTER TABLE entitlements ADD COLUMN IF NOT EXISTS revocation_reason text;

CREATE TABLE IF NOT EXISTS refunds (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  purchase_id uuid NOT NULL REFERENCES purchases(id),
  idempotency_key text NOT NULL,
  provider_idempotency_key text NOT NULL UNIQUE,
  provider_refund_id text UNIQUE,
  status text NOT NULL,
  amount_minor integer NOT NULL CHECK (amount_minor >= 100),
  currency char(3) NOT NULL CHECK (currency = 'RUB'),
  reason_ciphertext bytea,
  actor_fingerprint text NOT NULL,
  failure_code text,
  receipt_registration text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(purchase_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS refunds_purchase_idx ON refunds(purchase_id, status, created_at DESC);
