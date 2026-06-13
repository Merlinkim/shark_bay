-- Engine v2: version stamping and holdout access audit.
ALTER TABLE backtest_runs ADD COLUMN IF NOT EXISTS engine_version TEXT NOT NULL DEFAULT 'v0';

-- All rows existing before this migration were produced by the v0 engine
-- (close-fill look-ahead, per-candle win rate). Stamp them explicitly.
UPDATE backtest_runs SET engine_version = 'v0' WHERE engine_version = 'v0';

CREATE TABLE IF NOT EXISTS holdout_access_log (
  id BIGSERIAL PRIMARY KEY,
  accessor TEXT NOT NULL,
  purpose TEXT NOT NULL,
  range_start TIMESTAMPTZ,
  range_end TIMESTAMPTZ,
  accessed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Tombstone: research_experiments.sharpe values written before Engine v2 used
-- a sqrt(60) annualization factor and are not comparable to v2 values.
ALTER TABLE research_experiments ADD COLUMN IF NOT EXISTS engine_version TEXT NOT NULL DEFAULT 'v0';
