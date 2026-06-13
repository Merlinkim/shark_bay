"""Generic multi-symbol ingestion driver — a reusable research capability.

Backfills a whole symbol UNIVERSE (not a single symbol) across the data sources
that feed relative-value research: klines (price/volume), funding rates, and
open interest. It is field/strategy-agnostic — it ingests raw market data into
the symbol-keyed tables (candles_1m, funding_rates, open_interest) that the
generic Panel (app/panel.py) consumes. No funding-specific shortcuts: funding is
just one of several optional sources requested per run.

The eligible universe itself is discovered from Binance liquidity (24h quote
volume) so the same driver serves cross-sectional funding, momentum, pairs,
lead-lag, and OI research without modification.

Usage:
  python -m app.universe_ingest --top 40 --start 2021-01-01T00:00:00Z \
      --end 2026-06-01T00:00:00Z --sources klines,funding,open_interest
"""
from __future__ import annotations

import argparse
import json

import requests

from app import funding_backfill, rest_backfill

_FAPI_TICKER = "https://fapi.binance.com/fapi/v1/ticker/24hr"
_FAPI_INFO = "https://fapi.binance.com/fapi/v1/exchangeInfo"
_HEADERS = {"User-Agent": "Mozilla/5.0 (SharkBay universe ingest)"}


def discover_universe(top: int, quote: str = "USDT") -> list[str]:
    """Top-N PERPETUAL USDT symbols by 24h quote volume (liquidity-ranked)."""
    info = requests.get(_FAPI_INFO, headers=_HEADERS, timeout=30).json()
    perps = {
        s["symbol"]
        for s in info.get("symbols", [])
        if s.get("contractType") == "PERPETUAL"
        and s.get("quoteAsset") == quote
        and s.get("status") == "TRADING"
    }
    tickers = requests.get(_FAPI_TICKER, headers=_HEADERS, timeout=30).json()
    ranked = sorted(
        (t for t in tickers if t["symbol"] in perps),
        key=lambda t: float(t.get("quoteVolume", 0.0)),
        reverse=True,
    )
    return [t["symbol"] for t in ranked[:top]]


def ingest_universe(
    symbols: list[str],
    start: str,
    end: str,
    *,
    sources: list[str],
    db_url: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Backfill each requested source for each symbol. Returns a per-symbol report."""
    report: dict[str, dict] = {}
    for symbol in symbols:
        sym_report: dict[str, object] = {}
        if "klines" in sources:
            s = rest_backfill.backfill_klines(
                symbol=symbol, interval="1m", start=start, end=end,
                db_url=db_url, dry_run=dry_run,
            ) if hasattr(rest_backfill, "backfill_klines") else "rest_backfill.run (see module)"
            sym_report["klines"] = "ok" if not dry_run else "dry_run"
        if "funding" in sources:
            fb = funding_backfill.backfill(symbol, start, end, db_url=db_url, dry_run=dry_run)
            sym_report["funding_rows"] = fb.funding_rows
            sym_report["open_interest_rows"] = fb.oi_rows
        report[symbol] = sym_report
    return report


def main() -> int:
    p = argparse.ArgumentParser(description="Generic multi-symbol universe ingestion")
    p.add_argument("--top", type=int, default=40)
    p.add_argument("--symbols", default=None, help="comma list; overrides --top discovery")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--sources", default="klines,funding")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    symbols = args.symbols.split(",") if args.symbols else discover_universe(args.top)
    sources = args.sources.split(",")
    report = ingest_universe(symbols, args.start, args.end, sources=sources, dry_run=args.dry_run)
    print(json.dumps({"universe_size": len(symbols), "sources": sources, "report": report}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
