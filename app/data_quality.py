from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import psycopg
from psycopg.rows import dict_row


@dataclass(frozen=True)
class CandleRow:
    open_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None


@dataclass(frozen=True)
class DataQualityReport:
    symbol: str
    interval: str
    lookback_hours: int
    total_rows_checked: int
    gap_count: int
    duplicate_count: int
    invalid_ohlc_count: int
    invalid_volume_count: int
    future_timestamp_count: int
    latest_candle_timestamp: datetime | None
    data_lag_seconds: int | None


def get_db_url() -> str:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set")
    return db_url


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def compute_quality_report(
    candles: list[CandleRow],
    *,
    symbol: str,
    interval: str,
    lookback_hours: int,
    now: datetime | None = None,
) -> DataQualityReport:
    if interval != "1m":
        raise ValueError("Only 1m interval is currently supported")

    now_utc = _ensure_utc(now or datetime.now(timezone.utc))

    total_rows_checked = len(candles)
    duplicate_count = 0
    invalid_ohlc_count = 0
    invalid_volume_count = 0
    future_timestamp_count = 0
    gap_count = 0
    latest_candle_timestamp: datetime | None = None

    seen: set[datetime] = set()
    prev_open_time: datetime | None = None

    for candle in candles:
        open_time = _ensure_utc(candle.open_time)

        if latest_candle_timestamp is None or open_time > latest_candle_timestamp:
            latest_candle_timestamp = open_time

        if open_time in seen:
            duplicate_count += 1
        seen.add(open_time)

        if candle.high < candle.open or candle.high < candle.close or candle.low > candle.open or candle.low > candle.close or candle.high < candle.low:
            invalid_ohlc_count += 1

        if candle.volume is None or candle.volume <= 0:
            invalid_volume_count += 1

        if open_time > now_utc:
            future_timestamp_count += 1

        if prev_open_time is not None:
            delta = open_time - prev_open_time
            if delta > timedelta(minutes=1):
                gap_count += int(delta.total_seconds() // 60) - 1
        prev_open_time = open_time

    data_lag_seconds: int | None = None
    if latest_candle_timestamp is not None:
        data_lag_seconds = int((now_utc - latest_candle_timestamp).total_seconds())

    return DataQualityReport(
        symbol=symbol,
        interval=interval,
        lookback_hours=lookback_hours,
        total_rows_checked=total_rows_checked,
        gap_count=gap_count,
        duplicate_count=duplicate_count,
        invalid_ohlc_count=invalid_ohlc_count,
        invalid_volume_count=invalid_volume_count,
        future_timestamp_count=future_timestamp_count,
        latest_candle_timestamp=latest_candle_timestamp,
        data_lag_seconds=data_lag_seconds,
    )


def load_candles(db_url: str, *, symbol: str, lookback_hours: int) -> list[CandleRow]:
    start_time = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT open_time, open, high, low, close, volume
                FROM candles_1m
                WHERE symbol = %s AND open_time >= %s
                ORDER BY open_time ASC
                """,
                (symbol, start_time),
            )
            rows = cur.fetchall()

    return [
        CandleRow(
            open_time=row["open_time"],
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=row["volume"],
        )
        for row in rows
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run read-only candle data quality checks.")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--lookback-hours", type=int, default=24)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    candles = load_candles(get_db_url(), symbol=args.symbol, lookback_hours=args.lookback_hours)
    report = compute_quality_report(
        candles,
        symbol=args.symbol,
        interval=args.interval,
        lookback_hours=args.lookback_hours,
    )

    payload = asdict(report)
    if report.latest_candle_timestamp is not None:
        payload["latest_candle_timestamp"] = report.latest_candle_timestamp.isoformat()
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
