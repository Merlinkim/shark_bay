-- Funding Carry milestone, Phase 1: funding rate + open interest history.
--
-- Both are stored at their native observation cadence (funding settles every 8h;
-- open interest is sampled, typically every 5m on Binance). Research code joins
-- these onto a candle timeline with a STRICT as-of rule (app/funding.py), so the
-- value seen by a bar is only ever what was knowable at that bar's open_time.

CREATE TABLE IF NOT EXISTS funding_rates (
  symbol TEXT NOT NULL,
  settlement_time TIMESTAMPTZ NOT NULL,  -- instant the funding rate was applied
  funding_rate NUMERIC(20,10) NOT NULL,  -- fraction per 8h (e.g. 0.0001 = 1 bp)
  mark_price NUMERIC(20,10),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (symbol, settlement_time)
);

CREATE INDEX IF NOT EXISTS idx_funding_rates_settlement_time
  ON funding_rates (symbol, settlement_time DESC);

CREATE TABLE IF NOT EXISTS open_interest (
  symbol TEXT NOT NULL,
  ts TIMESTAMPTZ NOT NULL,                 -- observation timestamp
  open_interest NUMERIC(30,10) NOT NULL,   -- sum open interest (base units)
  open_interest_value NUMERIC(30,10),      -- notional (quote units), if available
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (symbol, ts)
);

CREATE INDEX IF NOT EXISTS idx_open_interest_ts
  ON open_interest (symbol, ts DESC);
