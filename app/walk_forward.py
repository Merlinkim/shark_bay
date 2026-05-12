from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from statistics import mean
from typing import Any

from app.dataset_splits import generate_walk_forward_windows, parse_iso8601_utc
from app.experiments import run_real_backtest_experiment


def _segment_metrics(strategy: str, symbol: str, interval: str, db_url: str, start: datetime, end: datetime) -> dict[str, Any]:
    result = run_real_backtest_experiment(strategy, symbol, interval, db_url=db_url, start=start, end=end)
    return {
        "status": result.status,
        "total_return_pct": result.total_return_pct,
        "sharpe": result.sharpe,
        "max_drawdown_pct": result.max_drawdown_pct,
        "win_rate_pct": result.win_rate_pct,
        "trade_count": result.trade_count,
        "dataset_row_count": result.dataset_row_count,
    }


def _degradation(train_metrics: dict[str, Any], validation_metrics: dict[str, Any], test_metrics: dict[str, Any]) -> dict[str, float]:
    return {
        "train_to_validation_sharpe_drop": train_metrics["sharpe"] - validation_metrics["sharpe"],
        "validation_to_test_sharpe_drop": validation_metrics["sharpe"] - test_metrics["sharpe"],
        "train_to_test_return_drop_pct": train_metrics["total_return_pct"] - test_metrics["total_return_pct"],
    }


def _avg(values: list[float]) -> float:
    return mean(values) if values else 0.0


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
    del include_holdout, persist  # v0: holdout intentionally excluded; persistence off by default.
    resolved_db_url = db_url or os.getenv("DATABASE_URL")
    if not resolved_db_url:
        raise RuntimeError("DATABASE_URL is not set")

    windows = generate_walk_forward_windows(
        start,
        end,
        train_days=train_days,
        validation_days=validation_days,
        test_days=test_days,
        step_days=step_days,
    )

    payload_windows: list[dict[str, Any]] = []
    for idx, window in enumerate(windows):
        train_metrics = _segment_metrics(strategy, symbol, interval, resolved_db_url, window.train.start, window.train.end)
        validation_metrics = _segment_metrics(strategy, symbol, interval, resolved_db_url, window.validation.start, window.validation.end)
        test_metrics = _segment_metrics(strategy, symbol, interval, resolved_db_url, window.test.start, window.test.end)
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

    train_sharpes = [w["train_metrics"]["sharpe"] for w in payload_windows]
    validation_sharpes = [w["validation_metrics"]["sharpe"] for w in payload_windows]
    test_sharpes = [w["test_metrics"]["sharpe"] for w in payload_windows]
    test_returns = [w["test_metrics"]["total_return_pct"] for w in payload_windows]
    test_drawdowns = [w["test_metrics"]["max_drawdown_pct"] for w in payload_windows]
    test_win_rates = [w["test_metrics"]["win_rate_pct"] for w in payload_windows]
    degradation_values = [w["degradation_metrics"]["validation_to_test_sharpe_drop"] for w in payload_windows]

    avg_test_return = _avg(test_returns)
    avg_test_sharpe = _avg(test_sharpes)
    stability_score = max(0.0, 1.0 - (abs(avg_test_return) / 100.0) * 0.1) if payload_windows else 0.0
    degradation_score = _avg(degradation_values)

    return {
        "strategy_name": strategy,
        "symbol": symbol,
        "interval": interval,
        "selected_range_start": start.isoformat(),
        "selected_range_end": end.isoformat(),
        "window_count": len(payload_windows),
        "windows": payload_windows,
        "aggregate": {
            "avg_train_sharpe": _avg(train_sharpes),
            "avg_validation_sharpe": _avg(validation_sharpes),
            "avg_test_sharpe": avg_test_sharpe,
            "avg_test_return_pct": avg_test_return,
            "worst_test_drawdown_pct": min(test_drawdowns) if test_drawdowns else 0.0,
            "test_win_rate_avg": _avg(test_win_rates),
            "stability_score": stability_score,
            "degradation_score": degradation_score,
            "pass_fail_status": "pass" if payload_windows and avg_test_sharpe >= 0 and degradation_score <= 0.5 else "fail",
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
