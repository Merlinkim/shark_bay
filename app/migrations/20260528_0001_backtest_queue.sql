CREATE TABLE IF NOT EXISTS backtest_jobs (
  id UUID PRIMARY KEY,
  strategy_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'success', 'failed', 'cancelled')),
  payload_json JSONB NOT NULL,
  reproducibility_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  result_json JSONB,
  result_reference TEXT,
  error_message TEXT,
  retry_count INTEGER NOT NULL DEFAULT 0,
  cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_backtest_jobs_status_created_at ON backtest_jobs (status, created_at ASC);

CREATE TABLE IF NOT EXISTS job_events (
  id BIGSERIAL PRIMARY KEY,
  job_id UUID NOT NULL REFERENCES backtest_jobs(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  event_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
