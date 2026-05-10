from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

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
    created_at: str


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
        created_at=created_at,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic read-only research experiments")
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--lookback-hours", type=int, default=24)
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
    print(json.dumps(asdict(result), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
