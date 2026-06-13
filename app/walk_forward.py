from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime
from statistics import mean
from typing import Any

from app.backtest import (
    Candle,
    CandleRepository,
    ENGINE_VERSION,
    SimulatedExecutionModel,
    build_dataset_fingerprint,
    build_execution_config,
    build_risk_config,
    build_strategy,
)
from app.dataset_splits import generate_walk_forward_windows, parse_iso8601_utc
from app.holdout import holdout_unlocked, log_holdout_access

# Research-neutral defaults: full notional sizing and effectively-disabled risk
# overlays, so walk-forward measures the strategy signal itself. Campaigns can
# override with explicit risk_config / execution_config.
RESEARCH_RISK_DEFAULTS: dict[str, Any] = {
    "position_size_mode": "notional_fraction",
    "risk_per_trade": 1.0,
    "max_position_size": 1.0,
    "stop_loss_pct": 1.0,
    "take_profit_pct": 1000.0,
    "max_holding_minutes": 10 ** 9,
    "max_daily_loss_pct": 100.0,
    "max_drawdown_pct": 100.0,
}


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


def _segment_metrics(
    strategy_name: str,
    params: dict[str, Any],
    candles: list[Candle],
    left: int,
    right: int,
    *,
    interval: str = "1m",
    risk_config: dict[str, Any] | None = None,
    execution_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the unified backtest engine on one walk-forward segment.

    Uses the exact same SimulatedExecutionModel as campaign backtests, so a
    walk-forward verdict and a single-window verdict can never disagree about
    engine semantics.
    """
    segment = candles[left:right]
    if len(segment) < 30:
        return {
            "status": "insufficient_data",
            "total_return_pct": 0.0,
            "sharpe": 0.0,
            "max_drawdown_pct": 0.0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "trade_count": 0,
            "dataset_row_count": len(segment),
        }

    strategy = build_strategy(strategy_name, dict(params))
    engine = SimulatedExecutionModel(
        execution_config=build_execution_config(execution_config),
        risk_config=build_risk_config({**RESEARCH_RISK_DEFAULTS, **(risk_config or {})}),
        interval=interval,
    )
    result = engine.run(
        segment,
        strategy,
        config_hash="walk_forward_segment",
        dataset_fingerprint=build_dataset_fingerprint(segment),
    )
    profit_factor = result.profit_factor
    if profit_factor == float("inf"):
        profit_factor = 999.0

    return {
        "status": "real_backtest",
        "total_return_pct": result.total_return_pct,
        "sharpe": result.sharpe,
        # Engine convention: positive percentage = drawdown magnitude.
        "max_drawdown_pct": result.max_drawdown_pct,
        "win_rate_pct": result.win_rate_pct,
        "profit_factor": profit_factor,
        "trade_count": result.trades,
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
    params: dict[str, Any] | None = None,
    risk_config: dict[str, Any] | None = None,
    execution_config: dict[str, Any] | None = None,
    include_holdout: bool = False,
    persist: bool = False,
    db_url: str | None = None,
    candles: list[Candle] | None = None,
) -> dict[str, Any]:
    del persist
    t0 = time.perf_counter()
    from app.backtest import INTERVAL_MINUTES
    if interval not in INTERVAL_MINUTES:
        raise ValueError(f"Unsupported interval: {interval}")
    # candles may be supplied pre-loaded (e.g. fetched from an exchange REST API
    # for an offline/in-memory verdict). In that case no database is required.
    preloaded = candles is not None
    resolved_db_url = db_url or os.getenv("DATABASE_URL")
    if not preloaded and not resolved_db_url:
        raise RuntimeError("DATABASE_URL is not set")

    allow_holdout = False
    if include_holdout:
        if not holdout_unlocked():
            raise PermissionError(
                "Holdout access requires RESEARCH_HOLDOUT_UNLOCK=1. "
                "Holdout data is opened once per strategy at final validation only."
            )
        log_holdout_access(
            resolved_db_url,
            accessor="walk_forward",
            purpose=f"strategy={strategy} symbol={symbol}",
            range_start=start,
            range_end=end,
        )
        allow_holdout = True

    t_load_start = time.perf_counter()
    if preloaded:
        candles = [c for c in candles if start <= c.open_time <= end]
    else:
        candles = CandleRepository(resolved_db_url).get_candles(
            symbol=symbol, interval=interval, start_time=start, end_time=end, allow_holdout=allow_holdout
        )
    load_candles_ms = round((time.perf_counter() - t_load_start) * 1000, 2)

    windows = generate_walk_forward_windows(
        start,
        end,
        train_days=train_days,
        validation_days=validation_days,
        test_days=test_days,
        step_days=step_days,
    )

    resolved_params = dict(params or {})

    t_bt_start = time.perf_counter()
    payload_windows: list[dict[str, Any]] = []
    for idx, window in enumerate(windows):
        tr_l, tr_r = _slice_bounds(candles, window.train.start, window.train.end)
        va_l, va_r = _slice_bounds(candles, window.validation.start, window.validation.end)
        te_l, te_r = _slice_bounds(candles, window.test.start, window.test.end)

        train_metrics = _segment_metrics(strategy, resolved_params, candles, tr_l, tr_r, interval=interval, risk_config=risk_config, execution_config=execution_config)
        validation_metrics = _segment_metrics(strategy, resolved_params, candles, va_l, va_r, interval=interval, risk_config=risk_config, execution_config=execution_config)
        test_metrics = _segment_metrics(strategy, resolved_params, candles, te_l, te_r, interval=interval, risk_config=risk_config, execution_config=execution_config)

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

    evaluable = [w for w in payload_windows if w["test_metrics"]["status"] == "real_backtest"]
    train_sharpes = [w["train_metrics"]["sharpe"] for w in payload_windows]
    validation_sharpes = [w["validation_metrics"]["sharpe"] for w in payload_windows]
    test_sharpes = [w["test_metrics"]["sharpe"] for w in evaluable]
    test_returns = [w["test_metrics"]["total_return_pct"] for w in evaluable]
    test_drawdowns = [w["test_metrics"]["max_drawdown_pct"] for w in evaluable]
    test_win_rates = [w["test_metrics"]["win_rate_pct"] for w in evaluable]
    test_profit_factors = [w["test_metrics"]["profit_factor"] for w in evaluable]
    test_trade_counts = [w["test_metrics"]["trade_count"] for w in evaluable]
    degradation_values = [w["degradation_metrics"]["validation_to_test_sharpe_drop"] for w in payload_windows]

    avg_test_return = _avg(test_returns)
    avg_test_sharpe = _avg(test_sharpes)
    avg_degradation = _avg(degradation_values)
    positive_fraction = (
        sum(1 for s in test_sharpes if s > 0) / len(test_sharpes) if test_sharpes else 0.0
    )

    # Pass requires: at least one evaluable window, positive average test Sharpe,
    # bounded validation->test degradation, and the majority of test windows positive.
    passed = (
        bool(evaluable)
        and avg_test_sharpe > 0.0
        and avg_degradation <= 0.5
        and positive_fraction >= 0.6
    )

    total_runtime_ms = round((time.perf_counter() - t0) * 1000, 2)

    return {
        "strategy_name": strategy,
        "symbol": symbol,
        "interval": interval,
        "engine_version": ENGINE_VERSION,
        "params": resolved_params,
        "selected_range_start": start.isoformat(),
        "selected_range_end": end.isoformat(),
        "load_candles_ms": load_candles_ms,
        "window_count": len(payload_windows),
        "evaluable_window_count": len(evaluable),
        "backtest_total_ms": backtest_total_ms,
        "total_runtime_ms": total_runtime_ms,
        "windows": payload_windows,
        "aggregate": {
            "avg_train_sharpe": _avg(train_sharpes),
            "avg_validation_sharpe": _avg(validation_sharpes),
            "avg_test_sharpe": avg_test_sharpe,
            "avg_test_return_pct": avg_test_return,
            "avg_test_profit_factor": _avg(test_profit_factors),
            "total_test_trade_count": sum(test_trade_counts),
            # Positive percentage = worst drawdown magnitude across test windows.
            "worst_test_drawdown_pct": max(test_drawdowns) if test_drawdowns else 0.0,
            "test_win_rate_avg": _avg(test_win_rates),
            "positive_test_window_fraction": positive_fraction,
            "degradation_score": avg_degradation,
            "pass_fail_status": "pass" if passed else "fail",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run walk-forward backtest over rolling windows (unified engine)")
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--train-days", type=int, required=True)
    parser.add_argument("--validation-days", type=int, required=True)
    parser.add_argument("--test-days", type=int, required=True)
    parser.add_argument("--step-days", type=int, default=None)
    parser.add_argument("--params", default=None, help="Strategy parameters as a JSON object")
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
        params=json.loads(args.params) if args.params else None,
        include_holdout=args.include_holdout,
        persist=args.persist,
    )
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
