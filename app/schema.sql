CREATE TABLE IF NOT EXISTS candles_1m (
  symbol TEXT NOT NULL,
  open_time TIMESTAMPTZ NOT NULL,
  close_time TIMESTAMPTZ NOT NULL,
  open NUMERIC(20,10) NOT NULL,
  high NUMERIC(20,10) NOT NULL,
  low NUMERIC(20,10) NOT NULL,
  close NUMERIC(20,10) NOT NULL,
  volume NUMERIC(30,10) NOT NULL,
  trades INTEGER NOT NULL,
  taker_buy_base NUMERIC(30,10) NOT NULL,
  taker_buy_quote NUMERIC(30,10) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (symbol, open_time)
);

CREATE INDEX IF NOT EXISTS idx_candles_1m_open_time ON candles_1m (open_time DESC);

CREATE TABLE IF NOT EXISTS collector_heartbeat (
  collector_name TEXT PRIMARY KEY,
  symbol TEXT NOT NULL,
  last_heartbeat_at TIMESTAMPTZ NOT NULL,
  poll_count BIGINT NOT NULL DEFAULT 0,
  success_count BIGINT NOT NULL DEFAULT 0,
  error_count BIGINT NOT NULL DEFAULT 0,
  retry_count BIGINT NOT NULL DEFAULT 0,
  reconnect_count BIGINT NOT NULL DEFAULT 0
);

ALTER TABLE collector_heartbeat
  ADD COLUMN IF NOT EXISTS last_backfill_status TEXT,
  ADD COLUMN IF NOT EXISTS last_backfill_candle_count INTEGER,
  ADD COLUMN IF NOT EXISTS last_backfill_time TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS missing_candle_events (
  id BIGSERIAL PRIMARY KEY,
  symbol TEXT NOT NULL,
  expected_open_time TIMESTAMPTZ NOT NULL,
  detected_at TIMESTAMPTZ NOT NULL,
  reason TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rest_backfill_events (
  id BIGSERIAL PRIMARY KEY,
  symbol TEXT NOT NULL,
  interval TEXT NOT NULL,
  missing_start_time TIMESTAMPTZ NOT NULL,
  missing_end_time TIMESTAMPTZ NOT NULL,
  recovered_count INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE TABLE IF NOT EXISTS backtest_runs (
  run_id UUID PRIMARY KEY,
  status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
  config_hash TEXT NOT NULL,
  dataset_fingerprint TEXT NOT NULL,
  symbol TEXT NOT NULL,
  interval TEXT NOT NULL,
  start_time TIMESTAMPTZ,
  end_time TIMESTAMPTZ,
  deterministic_summary_timestamp TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  failure_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_backtest_runs_symbol_interval_created_at ON backtest_runs (symbol, interval, created_at DESC);

CREATE TABLE IF NOT EXISTS backtest_metrics (
  run_id UUID PRIMARY KEY REFERENCES backtest_runs(run_id) ON DELETE CASCADE,
  total_return DOUBLE PRECISION NOT NULL,
  final_equity DOUBLE PRECISION NOT NULL,
  max_drawdown DOUBLE PRECISION NOT NULL,
  profit_factor DOUBLE PRECISION NOT NULL,
  average_trade_return DOUBLE PRECISION NOT NULL,
  trade_count INTEGER NOT NULL,
  win_rate DOUBLE PRECISION NOT NULL,
  total_fees DOUBLE PRECISION NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS backtest_equity_curve (
  run_id UUID NOT NULL REFERENCES backtest_runs(run_id) ON DELETE CASCADE,
  point_index INTEGER NOT NULL,
  open_time TIMESTAMPTZ NOT NULL,
  equity DOUBLE PRECISION NOT NULL,
  PRIMARY KEY (run_id, point_index)
);

CREATE INDEX IF NOT EXISTS idx_backtest_equity_curve_run_open_time ON backtest_equity_curve (run_id, open_time);

CREATE TABLE IF NOT EXISTS backtest_fills (
  run_id UUID NOT NULL REFERENCES backtest_runs(run_id) ON DELETE CASCADE,
  fill_index INTEGER NOT NULL,
  open_time TIMESTAMPTZ NOT NULL,
  prev_position INTEGER NOT NULL,
  new_position INTEGER NOT NULL,
  exec_price DOUBLE PRECISION NOT NULL,
  PRIMARY KEY (run_id, fill_index)
);

CREATE INDEX IF NOT EXISTS idx_backtest_fills_run_open_time ON backtest_fills (run_id, open_time);

CREATE TABLE IF NOT EXISTS research_experiments (
  experiment_id TEXT PRIMARY KEY,
  strategy_name TEXT NOT NULL,
  strategy_version TEXT NOT NULL,
  symbol TEXT NOT NULL,
  interval TEXT NOT NULL,
  dataset_start TIMESTAMPTZ,
  dataset_end TIMESTAMPTZ,
  dataset_row_count INTEGER NOT NULL,
  dataset_fingerprint TEXT NOT NULL,
  parameters JSONB NOT NULL,
  features_used JSONB NOT NULL,
  intended_regime TEXT NOT NULL,
  risk_profile TEXT NOT NULL,
  total_return_pct DOUBLE PRECISION NOT NULL,
  sharpe DOUBLE PRECISION NOT NULL,
  max_drawdown_pct DOUBLE PRECISION NOT NULL,
  win_rate_pct DOUBLE PRECISION NOT NULL,
  trade_count INTEGER NOT NULL,
  status TEXT NOT NULL,
  is_simulated BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_research_experiments_symbol_interval_created_at
  ON research_experiments (symbol, interval, created_at DESC);


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

CREATE TABLE IF NOT EXISTS experiments (
  id UUID PRIMARY KEY,
  strategy_id TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_experiments_strategy_created_at
  ON experiments (strategy_id, created_at DESC);

CREATE TABLE IF NOT EXISTS experiment_runs (
  id UUID PRIMARY KEY,
  experiment_id UUID NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
  run_id UUID NOT NULL,
  job_id UUID NOT NULL REFERENCES backtest_jobs(id) ON DELETE CASCADE,
  config_hash TEXT NOT NULL,
  dataset_fingerprint TEXT NOT NULL,
  risk_config_hash TEXT NOT NULL,
  execution_config_hash TEXT NOT NULL,
  git_commit_hash TEXT,
  summary_metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
  result_reference TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (run_id),
  UNIQUE (job_id)
);

CREATE INDEX IF NOT EXISTS idx_experiment_runs_experiment_created_at
  ON experiment_runs (experiment_id, created_at DESC);

CREATE TABLE IF NOT EXISTS experiment_metrics (
  id UUID PRIMARY KEY,
  experiment_id UUID NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
  run_id UUID NOT NULL,
  metric_name TEXT NOT NULL,
  metric_value DOUBLE PRECISION NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_experiment_metrics_experiment_run
  ON experiment_metrics (experiment_id, run_id);

CREATE TABLE IF NOT EXISTS experiment_artifacts (
  id UUID PRIMARY KEY,
  experiment_id UUID NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
  run_id UUID NOT NULL,
  artifact_type TEXT NOT NULL,
  artifact_reference TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_experiment_artifacts_experiment_run
  ON experiment_artifacts (experiment_id, run_id);
