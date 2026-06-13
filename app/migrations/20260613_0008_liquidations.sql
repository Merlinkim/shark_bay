-- Forward-collection infrastructure: liquidation (force-order) events.
--
-- Binance does NOT serve usable multi-year liquidation history over REST, so the
-- only way to obtain a trustworthy backtestable record is to FORWARD-COLLECT it
-- from the public futures WebSocket stream (!forceOrder@arr) going forward. This
-- table is the durable sink. It must NOT be used for backtest verdicts until it
-- has accumulated sufficient history (tracked via collector_heartbeat).

CREATE TABLE IF NOT EXISTS liquidations (
  symbol TEXT NOT NULL,
  event_time TIMESTAMPTZ NOT NULL,   -- exchange event timestamp
  side TEXT NOT NULL,                -- BUY = short liquidated, SELL = long liquidated
  price NUMERIC(20,10) NOT NULL,
  quantity NUMERIC(30,10) NOT NULL,
  avg_price NUMERIC(20,10),
  order_status TEXT,
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (symbol, event_time, side, price, quantity)
);

CREATE INDEX IF NOT EXISTS idx_liquidations_symbol_time
  ON liquidations (symbol, event_time DESC);

-- Open interest is already defined (migration 0007). Forward collection appends
-- point-in-time snapshots from GET /fapi/v1/openInterest into the same table, at
-- a finer cadence than the ~30-day openInterestHist REST allows.
