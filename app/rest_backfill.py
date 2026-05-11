from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import requests

from app.import_binance_klines import _validate_candle

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
_INTERVAL_MS = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "8h": 28_800_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
}


@dataclass
class BackfillSummary:
    symbol: str
    interval: str
    start: str
    end: str
    requested_range: int
    api_requests: int = 0
    fetched_rows: int = 0
    upserted_rows: int = 0
    min_open_time: datetime | None = None
    max_open_time: datetime | None = None
    dry_run: bool = False
    errors: list[str] = field(default_factory=list)


def parse_utc_to_ms(value: str) -> int:
    normalized = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def ms_to_utc(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def normalize_rest_kline_row(raw: list[Any]) -> dict[str, Any]:
    try:
        return {
            "open_time": ms_to_utc(int(raw[0])),
            "open": Decimal(str(raw[1])),
            "high": Decimal(str(raw[2])),
            "low": Decimal(str(raw[3])),
            "close": Decimal(str(raw[4])),
            "volume": Decimal(str(raw[5])),
            "close_time": ms_to_utc(int(raw[6])),
            "trades": int(raw[8]) if len(raw) > 8 else 0,
            "taker_buy_base": Decimal(str(raw[9])) if len(raw) > 9 else Decimal("0"),
            "taker_buy_quote": Decimal(str(raw[10])) if len(raw) > 10 else Decimal("0"),
        }
    except (IndexError, ValueError, InvalidOperation) as exc:
        raise ValueError(f"row parsing failed: {exc}") from exc


def fetch_klines_page(symbol: str, interval: str, start_time_ms: int, end_time_ms: int, limit: int, timeout: int = 30) -> list[list[Any]]:
    resp = requests.get(
        BINANCE_KLINES_URL,
        params={
            "symbol": symbol,
            "interval": interval,
            "startTime": start_time_ms,
            "endTime": end_time_ms,
            "limit": min(max(limit, 1), 1000),
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise ValueError("unexpected response payload")
    return data


def run_rest_backfill(symbol: str, interval: str, start: str, end: str, dry_run: bool = False, sleep_seconds: float = 0.2, limit: int = 1000, skip_existing: bool = False) -> BackfillSummary:
    if interval not in _INTERVAL_MS:
        raise ValueError(f"unsupported interval: {interval}")

    start_ms = parse_utc_to_ms(start)
    end_ms = parse_utc_to_ms(end)
    if start_ms >= end_ms:
        raise ValueError("start must be before end")

    summary = BackfillSummary(symbol=symbol, interval=interval, start=start, end=end, requested_range=end_ms - start_ms, dry_run=dry_run)

    conn = None
    if not dry_run:
        import psycopg2

        db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/market_data")
        conn = psycopg2.connect(db_url)

    step = _INTERVAL_MS[interval]
    next_start = start_ms
    try:
        while next_start < end_ms:
            attempts = 0
            page: list[list[Any]] = []
            while attempts < 3:
                try:
                    summary.api_requests += 1
                    page = fetch_klines_page(symbol=symbol, interval=interval, start_time_ms=next_start, end_time_ms=end_ms, limit=limit)
                    break
                except requests.HTTPError as exc:
                    status = exc.response.status_code if exc.response is not None else None
                    if status in {418, 429}:
                        attempts += 1
                        time.sleep(max(0.5, sleep_seconds))
                        continue
                    raise
            if not page:
                break

            summary.fetched_rows += len(page)
            last_open_ms = None
            for raw in page:
                candle = normalize_rest_kline_row(raw)
                open_ms = int(raw[0])
                if open_ms >= end_ms:
                    continue
                candle["symbol"] = symbol
                if not _validate_candle(candle):
                    continue

                summary.min_open_time = candle["open_time"] if summary.min_open_time is None else min(summary.min_open_time, candle["open_time"])
                summary.max_open_time = candle["open_time"] if summary.max_open_time is None else max(summary.max_open_time, candle["open_time"])

                if not dry_run:
                    if skip_existing:
                        with conn.cursor() as cur:
                            cur.execute("SELECT 1 FROM candles_1m WHERE symbol = %s AND open_time = %s", (symbol, candle["open_time"]))
                            if cur.fetchone() is not None:
                                last_open_ms = open_ms
                                continue
                    from app.main import upsert_candle

                    if upsert_candle(conn, candle):
                        summary.upserted_rows += 1
                last_open_ms = open_ms

            if last_open_ms is None:
                break
            next_start = last_open_ms + step
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

        if conn is not None:
            conn.commit()
    except Exception as exc:
        summary.errors.append(str(exc))
        raise
    finally:
        if conn is not None:
            conn.close()

    print(
        json.dumps(
            {
                "symbol": summary.symbol,
                "interval": summary.interval,
                "start": summary.start,
                "end": summary.end,
                "requested_range": summary.requested_range,
                "api_requests": summary.api_requests,
                "fetched_rows": summary.fetched_rows,
                "upserted_rows": summary.upserted_rows,
                "min_open_time": summary.min_open_time.isoformat() if summary.min_open_time else None,
                "max_open_time": summary.max_open_time.isoformat() if summary.max_open_time else None,
                "dry_run": summary.dry_run,
                "errors": summary.errors,
            },
            indent=2,
        )
    )
    return summary


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backfill Binance REST klines into candles_1m")
    p.add_argument("--symbol", required=True)
    p.add_argument("--interval", default="1m")
    p.add_argument("--start", required=True, help="ISO8601 UTC start e.g. 2026-05-01T00:00:00Z")
    p.add_argument("--end", required=True, help="ISO8601 UTC end e.g. 2026-05-11T00:00:00Z")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--sleep-seconds", type=float, default=0.2)
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--skip-existing", action="store_true")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_rest_backfill(
        symbol=args.symbol,
        interval=args.interval,
        start=args.start,
        end=args.end,
        dry_run=args.dry_run,
        sleep_seconds=args.sleep_seconds,
        limit=args.limit,
        skip_existing=args.skip_existing,
    )
