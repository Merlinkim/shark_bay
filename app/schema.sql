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

CREATE TABLE IF NOT EXISTS missing_candle_events (
  id BIGSERIAL PRIMARY KEY,
  symbol TEXT NOT NULL,
  expected_open_time TIMESTAMPTZ NOT NULL,
  detected_at TIMESTAMPTZ NOT NULL,
  reason TEXT NOT NULL
);
