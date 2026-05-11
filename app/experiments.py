from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from math import sqrt
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
    parameter_hash: str
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
    equity_curve: list[dict[str, Any]]
    fills: list[dict[str, Any]]


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
  parameter_hash TEXT NOT NULL DEFAULT '',
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
  is_simulated BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL,
  equity_curve JSONB NOT NULL DEFAULT '[]'::jsonb,
  fills JSONB NOT NULL DEFAULT '[]'::jsonb
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
                      parameter_hash, parameters, features_used, intended_regime, risk_profile,
                      total_return_pct, sharpe, max_drawdown_pct, win_rate_pct, trade_count,
                      status, is_simulated, created_at, equity_curve, fills
                    ) VALUES (
                      %(experiment_id)s, %(strategy_name)s, %(strategy_version)s, %(symbol)s, %(interval)s,
                      %(dataset_start)s, %(dataset_end)s, %(dataset_row_count)s, %(dataset_fingerprint)s,
                      %(parameter_hash)s, %(parameters)s::jsonb, %(features_used)s::jsonb, %(intended_regime)s, %(risk_profile)s,
                      %(total_return_pct)s, %(sharpe)s, %(max_drawdown_pct)s, %(win_rate_pct)s, %(trade_count)s,
                      %(status)s, %(is_simulated)s, %(created_at)s, %(equity_curve)s::jsonb, %(fills)s::jsonb
                    )
                    ON CONFLICT (experiment_id) DO UPDATE SET
                      total_return_pct = EXCLUDED.total_return_pct,
                      sharpe = EXCLUDED.sharpe,
                      max_drawdown_pct = EXCLUDED.max_drawdown_pct,
                      win_rate_pct = EXCLUDED.win_rate_pct,
                      trade_count = EXCLUDED.trade_count,
                      status = EXCLUDED.status,
                      is_simulated = EXCLUDED.is_simulated,
                      created_at = EXCLUDED.created_at,
                      equity_curve = EXCLUDED.equity_curve,
                      fills = EXCLUDED.fills
                    """,
                    {
                        **asdict(result),
                        "parameters": json.dumps(result.parameters),
                        "features_used": json.dumps(result.features_used),
                        "equity_curve": json.dumps(result.equity_curve),
                        "fills": json.dumps(result.fills),
                    },
                )

    def list_latest(self, symbol: str, interval: str, limit: int) -> list[dict[str, Any]]:
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM research_experiments WHERE symbol=%s AND interval=%s ORDER BY created_at DESC LIMIT %s", (symbol, interval, limit))
                return cur.fetchall()

    def get(self, experiment_id: str) -> dict[str, Any] | None:
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM research_experiments WHERE experiment_id=%s", (experiment_id,))
                return cur.fetchone()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _strategy_lookup(strategy_name: str) -> dict[str, Any]:
    for spec in list_strategy_specs():
        if spec["strategy_name"] == strategy_name:
            return spec
    raise ValueError(f"Unknown strategy_name: {strategy_name}")


def dataset_fingerprint(candles: list[Candle], symbol: str, interval: str) -> str:
    payload = f"{symbol}|{interval}|{len(candles)}|"
    if candles:
        payload += f"{candles[0].open_time.isoformat()}|{candles[-1].open_time.isoformat()}"
    else:
        payload += "empty"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _param_hash(params: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16]


def _signal(strategy_name: str, params: dict[str, Any], i: int, closes: list[float], position: int, entry_idx: int | None) -> int:
    if strategy_name == "ema_cross_v1":
        fast = int(params["fast_window"]); slow = int(params["slow_window"])
        if i + 1 < slow:
            return 0
        f = sum(closes[i-fast+1:i+1]) / fast
        s = sum(closes[i-slow+1:i+1]) / slow
        return 1 if f > s else 0
    if strategy_name == "rsi_mean_reversion_v1":
        win = 14
        if i < win:
            return 0
        deltas = [closes[j] - closes[j-1] for j in range(i-win+1, i+1)]
        gains = sum(d for d in deltas if d > 0) / win
        losses = abs(sum(d for d in deltas if d < 0) / win)
        rsi = 100.0 if losses == 0 else 100.0 - (100.0 / (1 + (gains / losses)))
        if position == 0 and rsi <= float(params["rsi_buy_threshold"]):
            return 1
        if position == 1 and (rsi >= float(params["rsi_sell_threshold"]) or (entry_idx is not None and i - entry_idx >= int(params["max_holding_bars"]))):
            return 0
        return position
    if strategy_name == "volatility_breakout_v1":
        look = 20
        if i < look:
            return 0
        ret = [(closes[j] / closes[j-1]) - 1 for j in range(i-look+1, i+1)]
        vol = (sum(r*r for r in ret) / len(ret)) ** 0.5
        th = float(params["volatility_threshold"])
        if position == 0 and vol >= th and closes[i] > max(closes[i-5:i]):
            return 1
        if position == 1 and closes[i] < min(closes[i-5:i]):
            return 0
        return position
    raise ValueError("unsupported strategy")


def run_real_backtest_experiment(strategy_name: str, symbol: str, interval: str, db_url: str, lookback_hours: int | None = None, start: datetime | None = None, end: datetime | None = None) -> ExperimentResult:
    spec = _strategy_lookup(strategy_name)
    if interval != spec["interval"]:
        raise ValueError(f"Strategy {strategy_name} supports interval={spec['interval']}")
    if symbol not in spec["symbols"]:
        raise ValueError(f"Strategy {strategy_name} does not support symbol={symbol}")
    if start is None or end is None:
        end = datetime.now(timezone.utc).replace(second=0, microsecond=0) if end is None else end
        start = end - timedelta(hours=lookback_hours or 24) if start is None else start

    candles = CandleRepository(db_url).get_candles(symbol=symbol, interval=interval, start_time=start, end_time=end)
    fp = dataset_fingerprint(candles, symbol, interval)
    created_at = _now_iso()
    p_hash = _param_hash(spec["parameters"])
    exp_key = json.dumps({"strategy": strategy_name, "symbol": symbol, "interval": interval, "fp": fp, "params": spec["parameters"]}, sort_keys=True)

    if len(candles) < 30:
        return ExperimentResult(str(uuid.uuid5(uuid.NAMESPACE_DNS, exp_key)), strategy_name, spec["version"], symbol, interval, candles[0].open_time.isoformat() if candles else None, candles[-1].open_time.isoformat() if candles else None, len(candles), fp, p_hash, spec["parameters"], spec["features_used"], spec["intended_regime"], spec["risk_profile"], 0.0, 0.0, 0.0, 0.0, 0, "insufficient_data", False, created_at, [], [])

    fee = 0.0004; slippage = 0.0002
    closes = [float(c.close) for c in candles]
    equity = 1.0; peak = 1.0; position = 0; entry = None
    rets=[]; fills=[]; curve=[]; wins=0; trades=0
    for i, candle in enumerate(candles):
        target = _signal(strategy_name, spec["parameters"], i, closes, position, entry)
        if i > 0 and position == 1:
            r = (closes[i] / closes[i-1]) - 1.0
            equity *= (1 + r)
            rets.append(r)
        if target != position:
            px = closes[i] * (1 + slippage if target > position else 1 - slippage)
            equity *= (1 - fee)
            fills.append({"open_time": candle.open_time.isoformat(), "prev_position": position, "new_position": target, "exec_price": round(px, 8)})
            if position == 0 and target == 1:
                entry = i
            if position == 1 and target == 0 and entry is not None:
                tr = (closes[i] / closes[entry]) - 1.0 - (2 * fee + 2 * slippage)
                trades += 1
                if tr > 0:
                    wins += 1
                entry = None
            position = target
        peak = max(peak, equity)
        curve.append({"open_time": candle.open_time.isoformat(), "equity": round(equity, 8)})

    dd = min((((p["equity"] / max(x["equity"] for x in curve[:idx+1])) - 1.0) * 100.0) for idx, p in enumerate(curve))
    avg = sum(rets)/len(rets) if rets else 0.0
    sd = sqrt(sum((r-avg)**2 for r in rets)/len(rets)) if rets else 0.0
    sharpe = (avg/sd)*sqrt(60.0) if sd > 0 else 0.0
    return ExperimentResult(
        experiment_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, exp_key)), strategy_name=strategy_name, strategy_version=spec["version"], symbol=symbol, interval=interval,
        dataset_start=candles[0].open_time.isoformat(), dataset_end=candles[-1].open_time.isoformat(), dataset_row_count=len(candles),
        dataset_fingerprint=fp, parameter_hash=p_hash, parameters=spec["parameters"], features_used=spec["features_used"], intended_regime=spec["intended_regime"], risk_profile=spec["risk_profile"],
        total_return_pct=round((equity-1.0)*100.0, 6), sharpe=round(sharpe, 6), max_drawdown_pct=round(dd, 6), win_rate_pct=round((wins/trades)*100.0, 6) if trades else 0.0, trade_count=trades,
        status="real_backtest", is_simulated=False, created_at=created_at, equity_curve=curve, fills=fills,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--lookback-hours", type=int, default=24)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args()
    db_url = __import__("os").getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set")
    start = datetime.fromisoformat(args.start.replace("Z", "+00:00")) if args.start else None
    end = datetime.fromisoformat(args.end.replace("Z", "+00:00")) if args.end else None
    result = run_real_backtest_experiment(args.strategy, args.symbol, args.interval, db_url, args.lookback_hours, start, end)
    if args.persist:
        repo = ResearchExperimentRepository(db_url)
        repo.ensure_schema()
        repo.upsert(result)
    print(json.dumps(asdict(result), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
