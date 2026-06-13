"""Backfill Binance USDⓈ-M futures funding rates and open interest.

Mirrors app/rest_backfill.py: paginated public REST pulls, idempotent upserts,
a JSON summary, and a --dry-run mode. No authentication required.

Endpoints:
  funding rate   GET https://fapi.binance.com/fapi/v1/fundingRate
                 (paginated by startTime/endTime, max 1000 rows/page, 8h cadence)
  open interest  GET https://fapi.binance.com/futures/data/openInterestHist
                 (period=5m/15m/1h/..., max 500 rows, only ~30 days of history)

Usage:
  python -m app.funding_backfill --symbol BTCUSDT \
      --start 2024-01-01T00:00:00Z --end 2024-06-01T00:00:00Z [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import requests

FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"
OPEN_INTEREST_URL = "https://fapi.binance.com/futures/data/openInterestHist"
_HEADERS = {"User-Agent": "Mozilla/5.0 (SharkBay research backfill)"}
_PAGE_LIMIT = 1000


def parse_utc_to_ms(value: str) -> int:
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def ms_to_utc(ms: int) -> datetime:
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)


@dataclass
class FundingBackfillSummary:
    symbol: str
    start: str
    end: str
    api_requests: int = 0
    funding_rows: int = 0
    funding_upserted: int = 0
    oi_rows: int = 0
    oi_upserted: int = 0
    dry_run: bool = False
    errors: list[str] = field(default_factory=list)


def fetch_funding_rates(symbol: str, start_ms: int, end_ms: int, sleep_seconds: float = 0.25) -> list[dict]:
    """Page through the funding-rate history for [start_ms, end_ms)."""
    out: list[dict] = []
    cursor = start_ms
    while cursor < end_ms:
        params = {"symbol": symbol, "startTime": cursor, "endTime": end_ms, "limit": _PAGE_LIMIT}
        resp = requests.get(FUNDING_URL, params=params, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
        page = resp.json()
        if not page:
            break
        out.extend(page)
        last = int(page[-1]["fundingTime"])
        if len(page) < _PAGE_LIMIT:
            break
        cursor = last + 1
        if sleep_seconds:
            time.sleep(sleep_seconds)
    # De-dup on fundingTime (page boundaries can overlap).
    seen: dict[int, dict] = {}
    for item in out:
        seen[int(item["fundingTime"])] = item
    return [seen[k] for k in sorted(seen)]


def fetch_open_interest(symbol: str, period: str = "1h", limit: int = 500) -> list[dict]:
    """Open-interest history. Binance only retains ~30 days; best-effort."""
    params = {"symbol": symbol, "period": period, "limit": limit}
    resp = requests.get(OPEN_INTEREST_URL, params=params, headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _get_db_url(db_url: str | None) -> str:
    resolved = db_url or os.getenv("DATABASE_URL")
    if not resolved:
        raise RuntimeError("DATABASE_URL is not set")
    return resolved


def backfill(symbol: str, start: str, end: str, *, db_url: str | None = None, dry_run: bool = False) -> FundingBackfillSummary:
    summary = FundingBackfillSummary(symbol=symbol, start=start, end=end, dry_run=dry_run)
    start_ms, end_ms = parse_utc_to_ms(start), parse_utc_to_ms(end)

    funding = fetch_funding_rates(symbol, start_ms, end_ms)
    summary.api_requests += 1
    summary.funding_rows = len(funding)
    oi = fetch_open_interest(symbol)
    summary.api_requests += 1
    summary.oi_rows = len(oi)

    if not dry_run:
        import psycopg

        with psycopg.connect(_get_db_url(db_url)) as conn:
            with conn.cursor() as cur:
                for item in funding:
                    cur.execute(
                        """
                        INSERT INTO funding_rates (symbol, settlement_time, funding_rate, mark_price)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (symbol, settlement_time) DO NOTHING
                        """,
                        (symbol, ms_to_utc(item["fundingTime"]), item["fundingRate"], item.get("markPrice")),
                    )
                    summary.funding_upserted += cur.rowcount
                for item in oi:
                    cur.execute(
                        """
                        INSERT INTO open_interest (symbol, ts, open_interest, open_interest_value)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (symbol, ts) DO NOTHING
                        """,
                        (symbol, ms_to_utc(item["timestamp"]), item["sumOpenInterest"], item.get("sumOpenInterestValue")),
                    )
                    summary.oi_upserted += cur.rowcount
            conn.commit()

    print(json.dumps(summary.__dict__, indent=2, default=str))
    return summary


def main() -> int:
    p = argparse.ArgumentParser(description="Backfill Binance funding rates and open interest")
    p.add_argument("--symbol", required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    backfill(args.symbol, args.start, args.end, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
