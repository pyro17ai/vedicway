-- One immutable UI preference snapshot and one exact result per requested PDF render.
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS payload jsonb;

CREATE TABLE IF NOT EXISTS pdf_render_requests (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  chart_id uuid NOT NULL REFERENCES charts(id),
  job_id uuid REFERENCES jobs(id),
  preferences jsonb NOT NULL,
  preferences_checksum text NOT NULL,
  status text NOT NULL CHECK (status IN ('queued', 'generating', 'ready', 'failed')),
  path text,
  checksum text,
  size_bytes bigint,
  pages integer,
  error_code text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS pdf_render_requests_chart_idx
  ON pdf_render_requests(chart_id, created_at DESC);

ALTER TABLE reports ADD COLUMN IF NOT EXISTS render_request_id uuid REFERENCES pdf_render_requests(id);
ALTER TABLE reports ADD COLUMN IF NOT EXISTS preferences_checksum text;

