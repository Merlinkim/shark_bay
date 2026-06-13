from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.stats import annualized_sharpe


@dataclass(frozen=True)
class DateRange:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class DatasetSplit:
    train: DateRange
    validation: DateRange
    holdout: DateRange


@dataclass(frozen=True)
class WalkForwardWindow:
    train: DateRange
    validation: DateRange
    test: DateRange


def _validate_split_ratios(train_ratio: float, validation_ratio: float, holdout_ratio: float) -> None:
    total = train_ratio + validation_ratio + holdout_ratio
    if abs(total - 1.0) > 1e-9:
        raise ValueError("Split ratios must sum to 1.0")


def deterministic_date_split(
    dataset_start: datetime,
    dataset_end: datetime,
    *,
    train_ratio: float = 0.7,
    validation_ratio: float = 0.15,
    holdout_ratio: float = 0.15,
    train_end: datetime | None = None,
    validation_end: datetime | None = None,
) -> DatasetSplit:
    if dataset_end <= dataset_start:
        raise ValueError("dataset_end must be greater than dataset_start")

    if train_end is not None and validation_end is not None:
        if not (dataset_start < train_end < validation_end < dataset_end):
            raise ValueError("Explicit boundaries must satisfy start < train_end < validation_end < end")
        return DatasetSplit(
            train=DateRange(dataset_start, train_end),
            validation=DateRange(train_end, validation_end),
            holdout=DateRange(validation_end, dataset_end),
        )

    _validate_split_ratios(train_ratio, validation_ratio, holdout_ratio)
    span = dataset_end - dataset_start
    train_cut = dataset_start + timedelta(seconds=span.total_seconds() * train_ratio)
    validation_cut = train_cut + timedelta(seconds=span.total_seconds() * validation_ratio)

    return DatasetSplit(
        train=DateRange(dataset_start, train_cut),
        validation=DateRange(train_cut, validation_cut),
        holdout=DateRange(validation_cut, dataset_end),
    )


def generate_walk_forward_windows(
    dataset_start: datetime,
    dataset_end: datetime,
    *,
    train_days: int,
    validation_days: int,
    test_days: int,
    step_days: int | None = None,
) -> list[WalkForwardWindow]:
    if dataset_end <= dataset_start:
        raise ValueError("dataset_end must be greater than dataset_start")
    if min(train_days, validation_days, test_days) <= 0:
        raise ValueError("Window days must be positive")

    step = timedelta(days=step_days if step_days is not None else test_days)
    train_td = timedelta(days=train_days)
    valid_td = timedelta(days=validation_days)
    test_td = timedelta(days=test_days)

    windows: list[WalkForwardWindow] = []
    cursor = dataset_start
    while True:
        train_end = cursor + train_td
        validation_end = train_end + valid_td
        test_end = validation_end + test_td
        if test_end > dataset_end:
            break
        windows.append(
            WalkForwardWindow(
                train=DateRange(cursor, train_end),
                validation=DateRange(train_end, validation_end),
                test=DateRange(validation_end, test_end),
            )
        )
        cursor = cursor + step
    return windows


def _returns(candles: list[Any]) -> list[float]:
    closes = [float(c.close) for c in candles]
    return [(closes[i] / closes[i - 1]) - 1.0 for i in range(1, len(closes)) if closes[i - 1] != 0]


def _metrics(candles: list[Any]) -> dict[str, float]:
    rs = _returns(candles)
    if not candles or len(candles) < 2:
        return {"rows": float(len(candles)), "total_return_pct": 0.0, "sharpe": 0.0, "up_candle_pct": 0.0}
    closes = [float(c.close) for c in candles]
    total_return_pct = ((closes[-1] / closes[0]) - 1.0) * 100.0 if closes[0] else 0.0
    # Buy-and-hold Sharpe of the raw candle series (market property, not a strategy metric).
    sharpe = annualized_sharpe(rs, interval="1m")
    # Fraction of up candles. Not a trade win rate — renamed so it can never be confused with one.
    up_candle_pct = (sum(1 for r in rs if r > 0) / len(rs)) * 100.0 if rs else 0.0
    return {"rows": float(len(candles)), "total_return_pct": total_return_pct, "sharpe": sharpe, "up_candle_pct": up_candle_pct}


def build_split_payload(
    *,
    symbol: str,
    interval: str,
    candles: list[Any],
    split_mode: str = "ratio",
    include_holdout: bool = False,
    train_days: int = 180,
    validation_days: int = 30,
    test_days: int = 30,
    step_days: int | None = None,
) -> dict[str, Any]:
    if len(candles) < 2:
        raise ValueError("Need at least 2 candles")
    dataset_start = candles[0].open_time
    dataset_end = candles[-1].open_time

    if split_mode == "rolling":
        windows = generate_walk_forward_windows(
            dataset_start,
            dataset_end,
            train_days=train_days,
            validation_days=validation_days,
            test_days=test_days,
            step_days=step_days,
        )
        aggregate = {
            "walk_forward_count": len(windows),
            "avg_test_sharpe": sum(0.0 for _ in windows) / len(windows) if windows else 0.0,
        }
        return {
            "symbol": symbol,
            "interval": interval,
            "split_mode": split_mode,
            "dataset_start": dataset_start.isoformat(),
            "dataset_end": dataset_end.isoformat(),
            "selected_range_start": dataset_start.isoformat(),
            "selected_range_end": dataset_end.isoformat(),
            "windows": [
                {
                    "train": asdict(w.train),
                    "validation": asdict(w.validation),
                    "test": asdict(w.test),
                }
                for w in windows
            ],
            "walk_forward_aggregate_metrics": aggregate,
        }

    split = deterministic_date_split(dataset_start, dataset_end)
    train_c = [c for c in candles if split.train.start <= c.open_time < split.train.end]
    valid_c = [c for c in candles if split.validation.start <= c.open_time < split.validation.end]
    hold_c = [c for c in candles if split.holdout.start <= c.open_time <= split.holdout.end]

    payload: dict[str, Any] = {
        "symbol": symbol,
        "interval": interval,
        "split_mode": split_mode,
        "dataset_start": dataset_start.isoformat(),
        "dataset_end": dataset_end.isoformat(),
        "selected_range_start": dataset_start.isoformat(),
        "selected_range_end": dataset_end.isoformat(),
        "train_range": {"start": split.train.start.isoformat(), "end": split.train.end.isoformat()},
        "validation_range": {"start": split.validation.start.isoformat(), "end": split.validation.end.isoformat()},
        "train_metrics": _metrics(train_c),
        "validation_metrics": _metrics(valid_c),
        "analytics": {
            "train_vs_validation_drift": _metrics(valid_c)["total_return_pct"] - _metrics(train_c)["total_return_pct"],
            "regime_consistency": 1.0 if _metrics(train_c)["sharpe"] * _metrics(valid_c)["sharpe"] >= 0 else 0.0,
            "walk_forward_sharpe_stability": 0.0,
        },
    }
    if include_holdout:
        hold_metrics = _metrics(hold_c)
        payload["holdout_range"] = {"start": split.holdout.start.isoformat(), "end": split.holdout.end.isoformat()}
        payload["holdout_metrics"] = hold_metrics
        payload["analytics"]["holdout_degradation"] = hold_metrics["total_return_pct"] - payload["validation_metrics"]["total_return_pct"]
    return payload


def parse_iso8601_utc(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("Datetime must include timezone, e.g. 2024-04-01T00:00:00Z")
    return parsed.astimezone(timezone.utc)


def resolve_selected_range(
    candles: list[Any],
    start: datetime | None,
    end: datetime | None,
) -> tuple[datetime, datetime]:
    if len(candles) < 2:
        raise ValueError("Need at least 2 candles")
    full_start = candles[0].open_time
    full_end = candles[-1].open_time
    selected_start = start or full_start
    selected_end = end or full_end
    if selected_end <= selected_start:
        raise ValueError("Invalid range: end must be greater than start")
    return selected_start, selected_end


def main() -> None:
    parser = argparse.ArgumentParser(description="Deterministic dataset splitting and rolling walk-forward window generation")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--split-mode", choices=["ratio", "rolling"], default="ratio")
    parser.add_argument("--train-days", type=int, default=180)
    parser.add_argument("--validation-days", type=int, default=30)
    parser.add_argument("--test-days", type=int, default=30)
    parser.add_argument("--step-days", type=int, default=None)
    parser.add_argument("--start", type=str, default=None)
    parser.add_argument("--end", type=str, default=None)
    parser.add_argument("--include-holdout", action="store_true")
    args = parser.parse_args()

    import os
    from app.backtest import CandleRepository

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set")

    selected_start = parse_iso8601_utc(args.start) if args.start else None
    selected_end = parse_iso8601_utc(args.end) if args.end else None
    candles = CandleRepository(db_url).get_candles(symbol=args.symbol, interval=args.interval, start_time=selected_start, end_time=selected_end)
    if selected_start is None or selected_end is None:
        selected_start, selected_end = resolve_selected_range(candles, selected_start, selected_end)
    payload = build_split_payload(
        symbol=args.symbol,
        interval=args.interval,
        candles=candles,
        split_mode=args.split_mode,
        include_holdout=args.include_holdout,
        train_days=args.train_days,
        validation_days=args.validation_days,
        test_days=args.test_days,
        step_days=args.step_days,
    )
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
