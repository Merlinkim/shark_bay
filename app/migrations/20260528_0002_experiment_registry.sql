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
