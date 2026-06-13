#!/usr/bin/env python3
"""Read-only production data-integrity audit for SharkBay.

Audits the production Postgres (candles_1m, funding_rates) against ten integrity
checks and, optionally, against live Binance source data. STRICTLY READ-ONLY:
the DB session is forced to `default_transaction_read_only = on`, and only SELECT
statements are issued — the tool cannot mutate production data even on a bug.

Checks
  1  Missing candles            6  Funding-rate alignment
  2  Duplicate candles          7  Exchange-data fidelity vs Binance sample
  3  Timestamp continuity       8  Resampled timeframe correctness
  4  OHLC consistency           9  Symbol coverage
  5  Volume consistency        10  Production-vs-Binance mismatch summary

Outputs a JSON report and a Markdown report. Checks 7/8/10 require network access
to Binance; pass --no-network to run the DB-only checks (1–6, 9).

Run on the VPS / Mac Mini:
  DATABASE_URL=postgresql://... \
  python -m tools.audit_production_data \
    --symbols BTCUSDT,ETHUSDT --start 2021-01-01 --end 2026-06-01 \
    --sample-size 200 --resample-interval 8h \
    --out-json audit.json --out-md audit.md

  # all symbols, DB-only:
  DATABASE_URL=... python -m tools.audit_production_data --symbols all --no-network
"""
from __future__ import annotations

import argparse
import json
import os
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

# ----------------------------------------------------------------------------
# Pure logic (no DB, no network) — unit-testable.
# ----------------------------------------------------------------------------

SEVERITY_ORDER = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


def worst(*severities: str) -> str:
    return max(severities, key=lambda s: SEVERITY_ORDER[s]) if severities else "NONE"


def ohlc_invalid(o: float, h: float, l: float, c: float) -> bool:
    """True if the OHLC relationships are violated."""
    return h < o or h < c or l > o or l > c or h < l


def volume_inconsistent(volume: float | None, taker_buy_base: float | None) -> bool:
    """True if volume is missing/negative or taker-buy exceeds total volume."""
    if volume is None or volume < 0:
        return True
    if taker_buy_base is not None and taker_buy_base > volume + 1e-9:
        return True
    return False


def compute_missing_ranges(open_times: list[datetime], step_seconds: int = 60) -> list[dict]:
    """Given ascending open_times, return the gap ranges (missing interior slots)."""
    ranges: list[dict] = []
    for i in range(1, len(open_times)):
        delta = (open_times[i] - open_times[i - 1]).total_seconds()
        if delta > step_seconds:
            missing = int(delta // step_seconds) - 1
            if missing > 0:
                ranges.append({
                    "gap_start": open_times[i - 1].isoformat(),
                    "gap_end": open_times[i].isoformat(),
                    "missing_count": missing,
                })
    return ranges


def is_monotonic(open_times: list[datetime]) -> bool:
    return all(open_times[i] > open_times[i - 1] for i in range(1, len(open_times)))


def funding_alignment_issues(settlements: list[datetime], interval_hours: int = 8) -> dict:
    """Detect funding settlements off the 8h grid and gaps between settlements."""
    misaligned = []
    gaps = []
    for t in settlements:
        secs = t.hour * 3600 + t.minute * 60 + t.second
        if secs % (interval_hours * 3600) != 0:
            misaligned.append(t.isoformat())
    for i in range(1, len(settlements)):
        delta_h = (settlements[i] - settlements[i - 1]).total_seconds() / 3600.0
        if abs(delta_h - interval_hours) > 1e-6:
            gaps.append({
                "from": settlements[i - 1].isoformat(),
                "to": settlements[i].isoformat(),
                "hours": round(delta_h, 3),
            })
    return {"misaligned_count": len(misaligned), "misaligned": misaligned[:50],
            "gap_count": len(gaps), "gaps": gaps[:50]}


def candle_mismatch(db_row: dict, src_row: dict, rel_tol: float = 1e-4) -> list[str]:
    """Return the list of OHLCV fields that differ beyond rel_tol."""
    diffs = []
    for f in ("open", "high", "low", "close", "volume"):
        a = db_row.get(f)
        b = src_row.get(f)
        if a is None or b is None:
            if a != b:
                diffs.append(f)
            continue
        a, b = float(a), float(b)
        denom = max(abs(a), abs(b), 1e-9)
        if abs(a - b) / denom > rel_tol:
            diffs.append(f)
    return diffs


def severity_missing(missing: int, expected: int) -> str:
    if expected <= 0:
        return "NONE"
    r = missing / expected
    if r > 0.01:
        return "HIGH"
    if r > 0.001:
        return "MEDIUM"
    if missing > 0:
        return "LOW"
    return "NONE"


def severity_count(n: int, high_at: int = 1) -> str:
    return "HIGH" if n >= high_at else "NONE"


def severity_mismatch_rate(rate: float) -> str:
    if rate > 0.005:
        return "CRITICAL"
    if rate > 0.0:
        return "HIGH"
    return "NONE"


# ----------------------------------------------------------------------------
# DB + Binance access (only imported/used when actually auditing).
# ----------------------------------------------------------------------------

def _connect_read_only(db_url: str):
    import psycopg
    conn = psycopg.connect(db_url)
    # Hard read-only guard: any write will raise, even on a code bug.
    with conn.cursor() as cur:
        cur.execute("SET default_transaction_read_only = on")
    conn.commit()
    return conn


def _binance_klines(base: str, symbol: str, interval: str, start_ms: int, limit: int = 1) -> list:
    import urllib.request
    url = (f"{base}?symbol={symbol}&interval={interval}"
           f"&startTime={start_ms}&limit={limit}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (SharkBay audit)"})
    import json as _json
    with urllib.request.urlopen(req, timeout=30) as r:
        return _json.load(r)


@dataclass
class SymbolAudit:
    symbol: str
    row_count: int = 0
    first_open_time: str | None = None
    last_open_time: str | None = None
    expected_rows: int = 0
    missing_count: int = 0
    missing_ranges: list[dict] = field(default_factory=list)
    duplicate_count: int = 0
    monotonic: bool = True
    invalid_ohlc_count: int = 0
    invalid_volume_count: int = 0
    funding: dict = field(default_factory=dict)
    fidelity_samples: int = 0
    fidelity_mismatches: int = 0
    fidelity_mismatch_rate: float = 0.0
    resample_buckets: int = 0
    resample_mismatches: int = 0
    resample_mismatch_rate: float = 0.0
    severity: str = "NONE"


def audit_symbol(conn, symbol: str, start: datetime, end: datetime, *, args) -> SymbolAudit:
    sa = SymbolAudit(symbol=symbol)
    with conn.cursor() as cur:
        # 9. coverage
        cur.execute("SELECT count(*), min(open_time), max(open_time) FROM candles_1m "
                    "WHERE symbol=%s AND open_time>=%s AND open_time<%s", (symbol, start, end))
        cnt, lo, hi = cur.fetchone()
        sa.row_count = cnt or 0
        sa.first_open_time = lo.isoformat() if lo else None
        sa.last_open_time = hi.isoformat() if hi else None

        # 1+3. missing + continuity via gap boundaries (returns only gap rows)
        cur.execute(
            """
            SELECT open_time, next_ot FROM (
              SELECT open_time, LEAD(open_time) OVER (ORDER BY open_time) AS next_ot
              FROM candles_1m WHERE symbol=%s AND open_time>=%s AND open_time<%s
            ) t WHERE next_ot IS NOT NULL AND next_ot - open_time > interval '60 seconds'
            ORDER BY open_time
            """, (symbol, start, end))
        gap_rows = cur.fetchall()
        for ot, nxt in gap_rows:
            missing = int((nxt - ot).total_seconds() // 60) - 1
            sa.missing_count += missing
            if len(sa.missing_ranges) < 100:
                sa.missing_ranges.append({"gap_start": ot.isoformat(), "gap_end": nxt.isoformat(), "missing_count": missing})
        if lo and hi:
            sa.expected_rows = int((hi - lo).total_seconds() // 60) + 1

        # 2. duplicates (PK should prevent; verify anyway)
        cur.execute("SELECT count(*) FROM (SELECT open_time FROM candles_1m WHERE symbol=%s "
                    "AND open_time>=%s AND open_time<%s GROUP BY open_time HAVING count(*)>1) d",
                    (symbol, start, end))
        sa.duplicate_count = cur.fetchone()[0] or 0

        # 3. monotonic (a duplicate-free ascending PK index implies this; explicit check)
        cur.execute("SELECT count(*) FROM (SELECT open_time, LAG(open_time) OVER (ORDER BY open_time) lp "
                    "FROM candles_1m WHERE symbol=%s AND open_time>=%s AND open_time<%s) t "
                    "WHERE lp IS NOT NULL AND open_time <= lp", (symbol, start, end))
        sa.monotonic = (cur.fetchone()[0] or 0) == 0

        # 4. OHLC
        cur.execute("SELECT count(*) FROM candles_1m WHERE symbol=%s AND open_time>=%s AND open_time<%s "
                    "AND (high<open OR high<close OR low>open OR low>close OR high<low)", (symbol, start, end))
        sa.invalid_ohlc_count = cur.fetchone()[0] or 0

        # 5. volume / taker
        cur.execute("SELECT count(*) FROM candles_1m WHERE symbol=%s AND open_time>=%s AND open_time<%s "
                    "AND (volume IS NULL OR volume<0 OR taker_buy_base>volume)", (symbol, start, end))
        sa.invalid_volume_count = cur.fetchone()[0] or 0

        # 6. funding alignment
        if args.funding:
            cur.execute("SELECT settlement_time FROM funding_rates WHERE symbol=%s AND settlement_time>=%s "
                        "AND settlement_time<%s ORDER BY settlement_time", (symbol, start, end))
            settlements = [r[0].astimezone(timezone.utc) for r in cur.fetchall()]
            sa.funding = funding_alignment_issues(settlements) if settlements else {"misaligned_count": 0, "gap_count": 0, "note": "no funding rows"}

    # 7+10. exchange fidelity (sample N 1m bars, diff vs Binance)
    if not args.no_network and sa.row_count > 0 and lo and hi:
        rng = random.Random(args.seed)
        with conn.cursor() as cur:
            cur.execute("SELECT open_time, open, high, low, close, volume FROM candles_1m "
                        "WHERE symbol=%s AND open_time>=%s AND open_time<%s", (symbol, start, end))
            allrows = cur.fetchall()
        sample = rng.sample(allrows, min(args.sample_size, len(allrows)))
        for ot, o, h, l, c, v in sample:
            try:
                k = _binance_klines(args.binance_klines, symbol, "1m", int(ot.timestamp() * 1000), 1)
            except Exception:
                continue
            if not k:
                continue
            src = {"open": k[0][1], "high": k[0][2], "low": k[0][3], "close": k[0][4], "volume": k[0][5]}
            db = {"open": o, "high": h, "low": l, "close": c, "volume": v}
            sa.fidelity_samples += 1
            if candle_mismatch(db, src, rel_tol=args.tol):
                sa.fidelity_mismatches += 1
        sa.fidelity_mismatch_rate = (sa.fidelity_mismatches / sa.fidelity_samples) if sa.fidelity_samples else 0.0

    # 8. resample correctness (one aligned window vs Binance native)
    if not args.no_network and sa.row_count > 0 and lo and hi:
        from app.backtest import Candle, resample_candles
        from decimal import Decimal
        # take the most recent fully-covered resample bucket in range
        with conn.cursor() as cur:
            cur.execute("SELECT open_time, open, high, low, close, volume FROM candles_1m "
                        "WHERE symbol=%s AND open_time>=%s AND open_time<%s ORDER BY open_time DESC LIMIT %s",
                        (symbol, start, end, args.resample_window_minutes))
            rows = list(reversed(cur.fetchall()))
        if rows:
            candles = [Candle(symbol=symbol, open_time=r[0].astimezone(timezone.utc), close=Decimal(str(r[4])),
                              open=Decimal(str(r[1])), high=Decimal(str(r[2])), low=Decimal(str(r[3])),
                              volume=Decimal(str(r[5])) if r[5] is not None else Decimal(0)) for r in rows]
            db_bars = resample_candles(candles, args.resample_interval)
            for bar in db_bars:
                try:
                    k = _binance_klines(args.binance_klines, symbol, args.resample_interval,
                                        int(bar.open_time.timestamp() * 1000), 1)
                except Exception:
                    continue
                if not k:
                    continue
                src = {"open": k[0][1], "high": k[0][2], "low": k[0][3], "close": k[0][4], "volume": k[0][5]}
                db = {"open": float(bar.open_), "high": float(bar.high_), "low": float(bar.low_),
                      "close": float(bar.close), "volume": float(bar.volume or 0)}
                sa.resample_buckets += 1
                if candle_mismatch(db, src, rel_tol=args.tol):
                    sa.resample_mismatches += 1
            sa.resample_mismatch_rate = (sa.resample_mismatches / sa.resample_buckets) if sa.resample_buckets else 0.0

    # severity rollup
    sev = [
        severity_missing(sa.missing_count, sa.expected_rows),
        severity_count(sa.duplicate_count),
        "NONE" if sa.monotonic else "HIGH",
        severity_count(sa.invalid_ohlc_count),
        "MEDIUM" if sa.invalid_volume_count else "NONE",
        severity_count(sa.funding.get("misaligned_count", 0)) if sa.funding else "NONE",
        severity_count(sa.funding.get("gap_count", 0)) if sa.funding else "NONE",
        severity_mismatch_rate(sa.fidelity_mismatch_rate),
        severity_mismatch_rate(sa.resample_mismatch_rate),
    ]
    sa.severity = worst(*sev)
    return sa


def render_markdown(report: dict) -> str:
    lines = [f"# SharkBay Production Data Audit", "",
             f"- Generated: {report['generated_at']}",
             f"- Range: {report['start']} → {report['end']}",
             f"- Symbols: {len(report['symbols'])}",
             f"- Network checks (7/8/10): {'disabled' if report['no_network'] else 'enabled'}",
             f"- **Overall severity: {report['overall_severity']}**", "",
             "## Per-symbol summary", "",
             "| symbol | rows | missing | dup | mono | bad OHLC | bad vol | funding gaps | fidelity mismatch | resample mismatch | severity |",
             "|--------|------|---------|-----|------|----------|---------|--------------|-------------------|-------------------|----------|"]
    for s in report["symbols"]:
        lines.append(
            f"| {s['symbol']} | {s['row_count']} | {s['missing_count']} | {s['duplicate_count']} | "
            f"{'ok' if s['monotonic'] else 'BAD'} | {s['invalid_ohlc_count']} | {s['invalid_volume_count']} | "
            f"{s.get('funding', {}).get('gap_count', '-')} | "
            f"{s['fidelity_mismatches']}/{s['fidelity_samples']} ({s['fidelity_mismatch_rate']:.2%}) | "
            f"{s['resample_mismatches']}/{s['resample_buckets']} ({s['resample_mismatch_rate']:.2%}) | "
            f"{s['severity']} |")
    return "\n".join(lines) + "\n"


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Read-only production data integrity audit")
    p.add_argument("--symbols", required=True, help="comma list or 'all'")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--interval", default="1m")
    p.add_argument("--sample-size", type=int, default=200, help="fidelity samples per symbol")
    p.add_argument("--resample-interval", default="8h")
    p.add_argument("--resample-window-minutes", type=int, default=2880, help="recent 1m rows to resample-check")
    p.add_argument("--tol", type=float, default=1e-4, help="relative tolerance for value diffs")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--funding", action="store_true", help="include funding alignment (check 6)")
    p.add_argument("--no-network", action="store_true", help="skip Binance checks (7/8/10)")
    p.add_argument("--binance-klines", default="https://api.binance.com/api/v3/klines",
                   help="spot=api.binance.com/api/v3/klines, futures=fapi.binance.com/fapi/v1/klines")
    p.add_argument("--out-json", default=None)
    p.add_argument("--out-md", default=None)
    return p.parse_args(argv)


def _parse_dt(s: str) -> datetime:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def main(argv=None) -> int:
    args = parse_args(argv)
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL is not set")
    start, end = _parse_dt(args.start), _parse_dt(args.end)

    conn = _connect_read_only(db_url)
    try:
        if args.symbols.strip().lower() == "all":
            with conn.cursor() as cur:
                cur.execute("SELECT DISTINCT symbol FROM candles_1m ORDER BY symbol")
                symbols = [r[0] for r in cur.fetchall()]
        else:
            symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]

        audits = [audit_symbol(conn, sym, start, end, args=args) for sym in symbols]
    finally:
        conn.close()

    overall = worst(*[a.severity for a in audits]) if audits else "NONE"
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "start": start.isoformat(), "end": end.isoformat(),
        "no_network": args.no_network,
        "overall_severity": overall,
        "symbols": [asdict(a) for a in audits],
    }
    out = json.dumps(report, indent=2, default=str)
    if args.out_json:
        with open(args.out_json, "w", encoding="utf-8") as f:
            f.write(out)
    if args.out_md:
        with open(args.out_md, "w", encoding="utf-8") as f:
            f.write(render_markdown(report))
    print(out)
    print(f"\nOVERALL SEVERITY: {overall}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
