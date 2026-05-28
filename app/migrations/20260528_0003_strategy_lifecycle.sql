CREATE TABLE IF NOT EXISTS research_strategy_proposals (
  strategy_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  current_status TEXT NOT NULL,
  created_by_agent TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_research_strategy_proposals_status
  ON research_strategy_proposals (current_status, updated_at DESC);

CREATE TABLE IF NOT EXISTS research_strategy_status_history (
  id BIGSERIAL PRIMARY KEY,
  strategy_id TEXT NOT NULL REFERENCES research_strategy_proposals(strategy_id) ON DELETE CASCADE,
  from_status TEXT,
  to_status TEXT NOT NULL,
  reason TEXT NOT NULL,
  changed_by_agent TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_research_strategy_status_history_strategy_created
  ON research_strategy_status_history (strategy_id, created_at ASC);
