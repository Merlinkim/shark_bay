from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime
from math import sqrt
from statistics import mean
from typing import Any

from app.backtest import Candle, CandleRepository
from app.dataset_splits import generate_walk_forward_windows, parse_iso8601_utc
from app.experiments import _signal, _strategy_lookup


def _avg(values: list[float]) -> float:
    return mean(values) if values else 0.0


def _degradation(train_metrics: dict[str, Any], validation_metrics: dict[str, Any], test_metrics: dict[str, Any]) -> dict[str, float]:
    return {
        "train_to_validation_sharpe_drop": train_metrics["sharpe"] - validation_metrics["sharpe"],
        "validation_to_test_sharpe_drop": validation_metrics["sharpe"] - test_metrics["sharpe"],
        "train_to_test_return_drop_pct": train_metrics["total_return_pct"] - test_metrics["total_return_pct"],
    }


def _slice_bounds(candles: list[Candle], start: datetime, end: datetime) -> tuple[int, int]:
    lo = 0
    hi = len(candles)
    while lo < hi:
        mid = (lo + hi) // 2
        if candles[mid].open_time < start:
            lo = mid + 1
        else:
            hi = mid
    left = lo

    lo = left
    hi = len(candles)
    while lo < hi:
        mid = (lo + hi) // 2
        if candles[mid].open_time <= end:
            lo = mid + 1
        else:
            hi = mid
    right = lo
    return left, right


def _segment_metrics(strategy_name: str, params: dict[str, Any], candles: list[Candle], left: int, right: int) -> dict[str, Any]:
    segment = candles[left:right]
    if len(segment) < 30:
        return {
            "status": "insufficient_data",
            "total_return_pct": 0.0,
            "sharpe": 0.0,
            "max_drawdown_pct": 0.0,
            "win_rate_pct": 0.0,
            "trade_count": 0,
            "dataset_row_count": len(segment),
        }

    fee = 0.0004
    slippage = 0.0002
    closes = [float(c.close) for c in segment]
    equity = 1.0
    position = 0
    entry = None
    rets: list[float] = []
    curve: list[float] = []
    wins = 0
    trades = 0

    for i, _ in enumerate(segment):
        target = _signal(strategy_name, params, i, closes, position, entry)
        if i > 0 and position == 1:
            r = (closes[i] / closes[i - 1]) - 1.0
            equity *= 1 + r
            rets.append(r)
        if target != position:
            equity *= 1 - fee
            if position == 0 and target == 1:
                entry = i
            if position == 1 and target == 0 and entry is not None:
                tr = (closes[i] / closes[entry]) - 1.0 - (2 * fee + 2 * slippage)
                trades += 1
                if tr > 0:
                    wins += 1
                entry = None
            position = target
        curve.append(equity)

    peak = 0.0
    worst_dd = 0.0
    for point in curve:
        peak = max(peak, point)
        if peak > 0:
            worst_dd = min(worst_dd, ((point / peak) - 1.0) * 100.0)

    avg = sum(rets) / len(rets) if rets else 0.0
    sd = sqrt(sum((r - avg) ** 2 for r in rets) / len(rets)) if rets else 0.0
    sharpe = (avg / sd) * sqrt(60.0) if sd > 0 else 0.0

    return {
        "status": "real_backtest",
        "total_return_pct": (equity - 1.0) * 100.0,
        "sharpe": sharpe,
        "max_drawdown_pct": worst_dd,
        "win_rate_pct": (wins / trades) * 100.0 if trades else 0.0,
        "trade_count": trades,
        "dataset_row_count": len(segment),
    }


def run_walk_forward_backtest(
    *,
    strategy: str,
    symbol: str,
    interval: str,
    start: datetime,
    end: datetime,
    train_days: int,
    validation_days: int,
    test_days: int,
    step_days: int | None = None,
    include_holdout: bool = False,
    persist: bool = False,
    db_url: str | None = None,
) -> dict[str, Any]:
    del include_holdout, persist
    t0 = time.perf_counter()
    resolved_db_url = db_url or os.getenv("DATABASE_URL")
    if not resolved_db_url:
        raise RuntimeError("DATABASE_URL is not set")

    spec = _strategy_lookup(strategy)
    if interval != spec["interval"]:
        raise ValueError(f"Strategy {strategy} supports interval={spec['interval']}")
    if symbol not in spec["symbols"]:
        raise ValueError(f"Strategy {strategy} does not support symbol={symbol}")

    t_load_start = time.perf_counter()
    candles = CandleRepository(resolved_db_url).get_candles(symbol=symbol, interval=interval, start_time=start, end_time=end)
    load_candles_ms = round((time.perf_counter() - t_load_start) * 1000, 2)

    windows = generate_walk_forward_windows(
        start,
        end,
        train_days=train_days,
        validation_days=validation_days,
        test_days=test_days,
        step_days=step_days,
    )

    t_bt_start = time.perf_counter()
    payload_windows: list[dict[str, Any]] = []
    for idx, window in enumerate(windows):
        tr_l, tr_r = _slice_bounds(candles, window.train.start, window.train.end)
        va_l, va_r = _slice_bounds(candles, window.validation.start, window.validation.end)
        te_l, te_r = _slice_bounds(candles, window.test.start, window.test.end)

        train_metrics = _segment_metrics(strategy, spec["parameters"], candles, tr_l, tr_r)
        validation_metrics = _segment_metrics(strategy, spec["parameters"], candles, va_l, va_r)
        test_metrics = _segment_metrics(strategy, spec["parameters"], candles, te_l, te_r)

        payload_windows.append(
            {
                "window_index": idx,
                "train_range": {"start": window.train.start.isoformat(), "end": window.train.end.isoformat()},
                "validation_range": {"start": window.validation.start.isoformat(), "end": window.validation.end.isoformat()},
                "test_range": {"start": window.test.start.isoformat(), "end": window.test.end.isoformat()},
                "train_metrics": train_metrics,
                "validation_metrics": validation_metrics,
                "test_metrics": test_metrics,
                "degradation_metrics": _degradation(train_metrics, validation_metrics, test_metrics),
            }
        )
    backtest_total_ms = round((time.perf_counter() - t_bt_start) * 1000, 2)

    train_sharpes = [w["train_metrics"]["sharpe"] for w in payload_windows]
    validation_sharpes = [w["validation_metrics"]["sharpe"] for w in payload_windows]
    test_sharpes = [w["test_metrics"]["sharpe"] for w in payload_windows]
    test_returns = [w["test_metrics"]["total_return_pct"] for w in payload_windows]
    test_drawdowns = [w["test_metrics"]["max_drawdown_pct"] for w in payload_windows]
    test_win_rates = [w["test_metrics"]["win_rate_pct"] for w in payload_windows]
    degradation_values = [w["degradation_metrics"]["validation_to_test_sharpe_drop"] for w in payload_windows]

    avg_test_return = _avg(test_returns)
    avg_test_sharpe = _avg(test_sharpes)
    total_runtime_ms = round((time.perf_counter() - t0) * 1000, 2)

    return {
        "strategy_name": strategy,
        "symbol": symbol,
        "interval": interval,
        "selected_range_start": start.isoformat(),
        "selected_range_end": end.isoformat(),
        "load_candles_ms": load_candles_ms,
        "window_count": len(payload_windows),
        "backtest_total_ms": backtest_total_ms,
        "total_runtime_ms": total_runtime_ms,
        "windows": payload_windows,
        "aggregate": {
            "avg_train_sharpe": _avg(train_sharpes),
            "avg_validation_sharpe": _avg(validation_sharpes),
            "avg_test_sharpe": avg_test_sharpe,
            "avg_test_return_pct": avg_test_return,
            "worst_test_drawdown_pct": min(test_drawdowns) if test_drawdowns else 0.0,
            "test_win_rate_avg": _avg(test_win_rates),
            "stability_score": max(0.0, 1.0 - (abs(avg_test_return) / 100.0) * 0.1) if payload_windows else 0.0,
            "degradation_score": _avg(degradation_values),
            "pass_fail_status": "pass" if payload_windows and avg_test_sharpe >= 0 and _avg(degradation_values) <= 0.5 else "fail",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run walk-forward real backtest over rolling windows")
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--train-days", type=int, required=True)
    parser.add_argument("--validation-days", type=int, required=True)
    parser.add_argument("--test-days", type=int, required=True)
    parser.add_argument("--step-days", type=int, default=None)
    parser.add_argument("--include-holdout", action="store_true")
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args()

    payload = run_walk_forward_backtest(
        strategy=args.strategy,
        symbol=args.symbol,
        interval=args.interval,
        start=parse_iso8601_utc(args.start),
        end=parse_iso8601_utc(args.end),
        train_days=args.train_days,
        validation_days=args.validation_days,
        test_days=args.test_days,
        step_days=args.step_days,
        include_holdout=args.include_holdout,
        persist=args.persist,
    )
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
