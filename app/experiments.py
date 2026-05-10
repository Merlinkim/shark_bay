from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
import psycopg
from psycopg.rows import dict_row

from app.backtest import Candle, CandleRepository
from app.strategy_registry import list_strategy_specs


@dataclass(frozen=True)
class ExperimentResult:
    experiment_id: str
    strategy_name: str
    strategy_version: str
    symbol: str
    interval: str
    dataset_start: str | None
    dataset_end: str | None
    dataset_row_count: int
    dataset_fingerprint: str
    parameters: dict[str, Any]
    features_used: list[str]
    intended_regime: str
    risk_profile: str
    total_return_pct: float
    sharpe: float
    max_drawdown_pct: float
    win_rate_pct: float
    trade_count: int
    status: str
    is_simulated: bool
    created_at: str


SCHEMA_SQL = """
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
"""


class ResearchExperimentRepository:
    def __init__(self, db_url: str):
        self.db_url = db_url

    def ensure_schema(self) -> None:
        with psycopg.connect(self.db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(SCHEMA_SQL)

    def upsert(self, result: ExperimentResult) -> None:
        with psycopg.connect(self.db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO research_experiments (
                      experiment_id, strategy_name, strategy_version, symbol, interval,
                      dataset_start, dataset_end, dataset_row_count, dataset_fingerprint,
                      parameters, features_used, intended_regime, risk_profile,
                      total_return_pct, sharpe, max_drawdown_pct, win_rate_pct, trade_count,
                      status, is_simulated, created_at
                    ) VALUES (
                      %(experiment_id)s, %(strategy_name)s, %(strategy_version)s, %(symbol)s, %(interval)s,
                      %(dataset_start)s, %(dataset_end)s, %(dataset_row_count)s, %(dataset_fingerprint)s,
                      %(parameters)s::jsonb, %(features_used)s::jsonb, %(intended_regime)s, %(risk_profile)s,
                      %(total_return_pct)s, %(sharpe)s, %(max_drawdown_pct)s, %(win_rate_pct)s, %(trade_count)s,
                      %(status)s, %(is_simulated)s, %(created_at)s
                    )
                    ON CONFLICT (experiment_id) DO UPDATE SET
                      strategy_name = EXCLUDED.strategy_name,
                      strategy_version = EXCLUDED.strategy_version,
                      symbol = EXCLUDED.symbol,
                      interval = EXCLUDED.interval,
                      dataset_start = EXCLUDED.dataset_start,
                      dataset_end = EXCLUDED.dataset_end,
                      dataset_row_count = EXCLUDED.dataset_row_count,
                      dataset_fingerprint = EXCLUDED.dataset_fingerprint,
                      parameters = EXCLUDED.parameters,
                      features_used = EXCLUDED.features_used,
                      intended_regime = EXCLUDED.intended_regime,
                      risk_profile = EXCLUDED.risk_profile,
                      total_return_pct = EXCLUDED.total_return_pct,
                      sharpe = EXCLUDED.sharpe,
                      max_drawdown_pct = EXCLUDED.max_drawdown_pct,
                      win_rate_pct = EXCLUDED.win_rate_pct,
                      trade_count = EXCLUDED.trade_count,
                      status = EXCLUDED.status,
                      is_simulated = EXCLUDED.is_simulated,
                      created_at = EXCLUDED.created_at
                    """,
                    {
                        **asdict(result),
                        "parameters": json.dumps(result.parameters),
                        "features_used": json.dumps(result.features_used),
                    },
                )

    def list_latest(self, symbol: str, interval: str, limit: int) -> list[dict[str, Any]]:
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM research_experiments
                    WHERE symbol = %s AND interval = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (symbol, interval, limit),
                )
                return cur.fetchall()

    def get(self, experiment_id: str) -> dict[str, Any] | None:
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM research_experiments WHERE experiment_id = %s", (experiment_id,))
                return cur.fetchone()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _strategy_lookup(strategy_name: str) -> dict[str, Any]:
    specs = list_strategy_specs()
    for spec in specs:
        if spec["strategy_name"] == strategy_name:
            return spec
    raise ValueError(f"Unknown strategy_name: {strategy_name}")


def dataset_fingerprint(candles: list[Candle], symbol: str, interval: str) -> str:
    if not candles:
        payload = f"{symbol}|{interval}|0|empty"
    else:
        payload = "|".join([
            symbol,
            interval,
            str(len(candles)),
            candles[0].open_time.isoformat(),
            candles[-1].open_time.isoformat(),
            str(candles[0].close),
            str(candles[-1].close),
        ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def run_deterministic_placeholder_experiment(strategy_name: str, symbol: str, interval: str, lookback_hours: int, db_url: str) -> ExperimentResult:
    spec = _strategy_lookup(strategy_name)
    if interval != spec["interval"]:
        raise ValueError(f"Strategy {strategy_name} supports interval={spec['interval']}")
    if symbol not in spec["symbols"]:
        raise ValueError(f"Strategy {strategy_name} does not support symbol={symbol}")

    end_time = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start_time = end_time - timedelta(hours=lookback_hours)
    candles = CandleRepository(db_url).get_candles(symbol=symbol, interval=interval, start_time=start_time, end_time=end_time)

    fp = dataset_fingerprint(candles, symbol, interval)
    row_count = len(candles)
    created_at = _now_iso()

    if row_count < 2:
        return ExperimentResult(
            experiment_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"placeholder:{strategy_name}:{symbol}:{interval}:{fp}")),
            strategy_name=strategy_name,
            strategy_version=spec["version"],
            symbol=symbol,
            interval=interval,
            dataset_start=candles[0].open_time.isoformat() if candles else None,
            dataset_end=candles[-1].open_time.isoformat() if candles else None,
            dataset_row_count=row_count,
            dataset_fingerprint=fp,
            parameters=spec["parameters"],
            features_used=spec["features_used"],
            intended_regime=spec["intended_regime"],
            risk_profile=spec["risk_profile"],
            total_return_pct=0.0,
            sharpe=0.0,
            max_drawdown_pct=0.0,
            win_rate_pct=0.0,
            trade_count=0,
            status="simulated_placeholder_insufficient_data",
            is_simulated=True,
            created_at=created_at,
        )

    closes = [float(c.close) for c in candles]
    returns = [(closes[i] / closes[i - 1]) - 1.0 for i in range(1, len(closes)) if closes[i - 1] != 0]
    total_return_pct = ((closes[-1] / closes[0]) - 1.0) * 100.0 if closes[0] != 0 else 0.0
    avg_r = sum(returns) / len(returns) if returns else 0.0
    var_r = sum((r - avg_r) ** 2 for r in returns) / len(returns) if returns else 0.0
    std_r = var_r ** 0.5
    sharpe = (avg_r / std_r) * (60.0 ** 0.5) if std_r > 0 else 0.0

    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    wins = 0
    for r in returns:
        equity *= (1 + r)
        peak = max(peak, equity)
        dd = ((equity / peak) - 1.0) * 100.0
        max_dd = min(max_dd, dd)
        if r > 0:
            wins += 1

    trade_count = max(1, len(returns) // 8)
    win_rate = (wins / len(returns)) * 100.0 if returns else 0.0

    experiment_key = json.dumps(
        {
            "strategy": strategy_name,
            "symbol": symbol,
            "interval": interval,
            "fp": fp,
            "params": spec["parameters"],
        },
        sort_keys=True,
    )

    return ExperimentResult(
        experiment_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, experiment_key)),
        strategy_name=strategy_name,
        strategy_version=spec["version"],
        symbol=symbol,
        interval=interval,
        dataset_start=candles[0].open_time.isoformat(),
        dataset_end=candles[-1].open_time.isoformat(),
        dataset_row_count=row_count,
        dataset_fingerprint=fp,
        parameters=spec["parameters"],
        features_used=spec["features_used"],
        intended_regime=spec["intended_regime"],
        risk_profile=spec["risk_profile"],
        total_return_pct=round(total_return_pct, 6),
        sharpe=round(sharpe, 6),
        max_drawdown_pct=round(max_dd, 6),
        win_rate_pct=round(win_rate, 6),
        trade_count=trade_count,
        status="simulated_placeholder",
        is_simulated=True,
        created_at=created_at,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic read-only research experiments")
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--lookback-hours", type=int, default=24)
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args()

    import os

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set")

    result = run_deterministic_placeholder_experiment(
        strategy_name=args.strategy,
        symbol=args.symbol,
        interval=args.interval,
        lookback_hours=args.lookback_hours,
        db_url=db_url,
    )
    if args.persist:
        repo = ResearchExperimentRepository(db_url)
        repo.ensure_schema()
        repo.upsert(result)
    print(json.dumps(asdict(result), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
