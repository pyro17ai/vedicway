-- One immutable UI preference snapshot per requested PDF render.
ALTER TABLE jobs ADD COLUMN payload jsonb;

CREATE TABLE pdf_render_requests (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  chart_id uuid NOT NULL REFERENCES charts(id),
  job_id uuid REFERENCES jobs(id),
  preferences jsonb NOT NULL,
  preferences_checksum text NOT NULL,
  status text NOT NULL CHECK (status IN ('queued', 'generating', 'ready', 'failed')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX pdf_render_requests_chart_idx ON pdf_render_requests(chart_id, created_at DESC);

ALTER TABLE reports ADD COLUMN render_request_id uuid REFERENCES pdf_render_requests(id);
ALTER TABLE reports ADD COLUMN preferences_checksum text;
