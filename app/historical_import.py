from __future__ import annotations

import argparse
import csv
import io
import json
import os
import time
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable

import requests

from app.import_binance_klines import _normalize_kline_row, _validate_candle

VISION_URL_PATTERN = "https://data.binance.vision/data/spot/monthly/klines/{symbol}/{interval}/{symbol}-{interval}-{month}.zip"


@dataclass
class ImportSummary:
    symbol: str
    interval: str
    requested_months: int
    downloaded_months: int = 0
    missing_months: list[str] = field(default_factory=list)
    imported_rows: int = 0
    upserted_rows: int = 0
    min_open_time: datetime | None = None
    max_open_time: datetime | None = None
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CandleRow:
    open_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None


def month_iter(start_month: str, end_month: str) -> list[str]:
    start = datetime.strptime(start_month, "%Y-%m")
    end = datetime.strptime(end_month, "%Y-%m")
    months: list[str] = []
    cur = start
    while cur <= end:
        months.append(cur.strftime("%Y-%m"))
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)
    return months


def build_url(symbol: str, interval: str, month: str) -> str:
    return VISION_URL_PATTERN.format(symbol=symbol, interval=interval, month=month)


def parse_zip_rows(content: bytes) -> Iterable[list[str]]:
    with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not names:
            raise ValueError("zip does not contain csv")
        with zf.open(names[0], "r") as f:
            text = io.TextIOWrapper(f, encoding="utf-8")
            yield from csv.reader(text)


def _parse_binance_timestamp(raw_ts: str) -> datetime:
    ts = int(raw_ts)
    # Binance Vision is expected to be milliseconds, but defensively support seconds.
    if ts > 10_000_000_000:  # > year 2286 in seconds, likely milliseconds
        return datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _normalize_historical_kline_row(raw: list[str]) -> dict:
    candle = _normalize_kline_row(raw)
    # Defensive override: accept both ms and seconds timestamp units.
    candle["open_time"] = _parse_binance_timestamp(raw[0])
    if len(raw) > 6 and raw[6]:
        candle["close_time"] = _parse_binance_timestamp(raw[6])
    return candle


def _compute_months(args: argparse.Namespace) -> list[str]:
    now = datetime.now(timezone.utc)
    if args.end_month:
        end_month = args.end_month
    else:
        end_month = now.strftime("%Y-%m")
    if args.start_month:
        start_month = args.start_month
        months = month_iter(start_month, end_month)
    else:
        months = []
        end = datetime.strptime(end_month, "%Y-%m")
        for i in range(args.months):
            y = end.year
            m = end.month - i
            while m <= 0:
                y -= 1
                m += 12
            months.append(f"{y:04d}-{m:02d}")
        months.reverse()
    if args.max_months:
        months = months[-args.max_months :]
    return months


def run_import(args: argparse.Namespace) -> ImportSummary:
    months = _compute_months(args)
    summary = ImportSummary(symbol=args.symbol, interval=args.interval, requested_months=len(months))
    conn = None
    if not args.dry_run:
        import psycopg2
        db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/market_data")
        conn = psycopg2.connect(db_url)

    imported_candles: list[CandleRow] = []
    try:
        for month in months:
            url = build_url(args.symbol, args.interval, month)
            try:
                if args.skip_existing and conn is not None:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            SELECT 1
                            FROM candles_1m
                            WHERE symbol = %s
                              AND open_time >= %s::date
                              AND open_time < (%s::date + interval '1 month')
                            LIMIT 1
                            """,
                            (args.symbol, f"{month}-01", f"{month}-01"),
                        )
                        if cur.fetchone():
                            print(json.dumps({"status": "skipped_existing", "month": month}))
                            continue
                resp = requests.get(url, timeout=30)
                if resp.status_code == 404:
                    summary.missing_months.append(month)
                    print(json.dumps({"status": "missing", "month": month, "url": url}))
                    continue
                resp.raise_for_status()
                rows = list(parse_zip_rows(resp.content))
                summary.downloaded_months += 1
                for raw in rows:
                    candle = _normalize_historical_kline_row(raw)
                    candle["symbol"] = args.symbol
                    if not _validate_candle(candle):
                        continue
                    summary.imported_rows += 1
                    summary.min_open_time = candle["open_time"] if summary.min_open_time is None else min(summary.min_open_time, candle["open_time"])
                    summary.max_open_time = candle["open_time"] if summary.max_open_time is None else max(summary.max_open_time, candle["open_time"])
                    if args.dry_run:
                        imported_candles.append(CandleRow(open_time=candle["open_time"], open=candle["open"], high=candle["high"], low=candle["low"], close=candle["close"], volume=candle["volume"]))
                        continue
                    from app.main import upsert_candle
                    inserted = upsert_candle(conn, candle)
                    summary.upserted_rows += 1 if inserted else 0
            except Exception as exc:
                summary.errors.append(f"{month}: {exc}")
                print(json.dumps({"status": "error", "month": month, "error": str(exc)}))
            if args.sleep_seconds:
                time.sleep(args.sleep_seconds)
        if conn is not None:
            conn.commit()
    finally:
        if conn is not None:
            conn.close()

    print(json.dumps({
        "symbol": summary.symbol,
        "interval": summary.interval,
        "requested_months": summary.requested_months,
        "downloaded_months": summary.downloaded_months,
        "missing_months": summary.missing_months,
        "imported_rows": summary.imported_rows,
        "upserted_rows": summary.upserted_rows,
        "min_open_time": summary.min_open_time.isoformat() if summary.min_open_time else None,
        "max_open_time": summary.max_open_time.isoformat() if summary.max_open_time else None,
        "errors": summary.errors,
    }, indent=2))

    if args.run_quality_check and summary.min_open_time and summary.max_open_time:
        from app.data_quality import compute_quality_report
        report = compute_quality_report(
            imported_candles,
            symbol=args.symbol,
            interval=args.interval,
            lookback_hours=24,
        )
        print(json.dumps({"quality_report": asdict(report)}, default=str, indent=2))

    return summary


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Import Binance Vision monthly historical klines")
    p.add_argument("--symbol", required=True)
    p.add_argument("--interval", default="1m")
    p.add_argument("--months", type=int, default=80)
    p.add_argument("--start-month")
    p.add_argument("--end-month")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--max-months", type=int)
    p.add_argument("--sleep-seconds", type=float, default=0.0)
    p.add_argument("--skip-existing", action="store_true")
    p.add_argument("--run-quality-check", action="store_true")
    return p.parse_args()


if __name__ == "__main__":
    run_import(parse_args())
