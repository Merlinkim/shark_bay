"""Durable forward-collection for open interest and liquidations.

These build the multi-year history that Binance does NOT serve over REST:
  * Open interest — GET /fapi/v1/openInterest is a point-in-time SNAPSHOT;
    polling it on a schedule accumulates a real series (the openInterestHist
    REST endpoint only retains ~30 days).
  * Liquidations — there is no usable historical REST feed; the public futures
    WebSocket stream `!forceOrder@arr` is the source. A long-running consumer
    appends events to the `liquidations` table.

Design principles (durable infrastructure, not a one-off):
  * Idempotent upserts (ON CONFLICT DO NOTHING) so restarts never duplicate.
  * Heartbeats in `collector_heartbeat` so freshness/coverage is observable and
    the "enough history yet?" gate can be checked before any backtest uses it.
  * Pure single-cycle functions (poll_open_interest_once, handle_liquidation_msg)
    that are unit-testable; the loops are thin wrappers.

GUARDRAIL: forward-collected data MUST NOT feed a backtest verdict until
sufficient history has accumulated. See collection_coverage_days().
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

import requests

OPEN_INTEREST_URL = "https://fapi.binance.com/fapi/v1/openInterest"
_HEADERS = {"User-Agent": "Mozilla/5.0 (SharkBay collector)"}
LIQUIDATION_WS = "wss://fstream.binance.com/ws/!forceOrder@arr"


def _db_url(db_url: str | None) -> str:
    resolved = db_url or os.getenv("DATABASE_URL")
    if not resolved:
        raise RuntimeError("DATABASE_URL is not set")
    return resolved


def _heartbeat(conn, collector: str, symbol: str, *, ok: bool) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO collector_heartbeat (collector_name, symbol, last_heartbeat_at, poll_count, success_count, error_count)
            VALUES (%s, %s, NOW(), 1, %s, %s)
            ON CONFLICT (collector_name) DO UPDATE SET
              last_heartbeat_at = NOW(),
              poll_count = collector_heartbeat.poll_count + 1,
              success_count = collector_heartbeat.success_count + %s,
              error_count = collector_heartbeat.error_count + %s
            """,
            (collector, symbol, 1 if ok else 0, 0 if ok else 1, 1 if ok else 0, 0 if ok else 1),
        )


# --- Open interest snapshot polling -----------------------------------------

def fetch_open_interest_snapshot(symbol: str) -> dict:
    r = requests.get(OPEN_INTEREST_URL, params={"symbol": symbol}, headers=_HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()  # {"openInterest": "...", "symbol": "...", "time": ms}


def poll_open_interest_once(conn, symbol: str) -> bool:
    """One snapshot → upsert into open_interest. Returns True on success."""
    try:
        snap = fetch_open_interest_snapshot(symbol)
        ts = datetime.fromtimestamp(int(snap["time"]) / 1000, tz=timezone.utc)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO open_interest (symbol, ts, open_interest)
                VALUES (%s, %s, %s)
                ON CONFLICT (symbol, ts) DO NOTHING
                """,
                (symbol, ts, snap["openInterest"]),
            )
        _heartbeat(conn, "open_interest_collector", symbol, ok=True)
        conn.commit()
        return True
    except Exception:
        _heartbeat(conn, "open_interest_collector", symbol, ok=False)
        conn.commit()
        return False


def run_open_interest_collector(symbols: list[str], interval_seconds: int = 300, db_url: str | None = None) -> None:
    import psycopg
    with psycopg.connect(_db_url(db_url)) as conn:
        while True:
            for s in symbols:
                poll_open_interest_once(conn, s)
            time.sleep(interval_seconds)


# --- Liquidation WebSocket consumer -----------------------------------------

def parse_liquidation_msg(msg: dict) -> dict | None:
    """Parse a !forceOrder@arr payload into a liquidations row, or None."""
    o = msg.get("o") or msg.get("data", {}).get("o")
    if not o:
        return None
    return {
        "symbol": o["s"],
        "event_time": datetime.fromtimestamp(int(o["T"]) / 1000, tz=timezone.utc),
        "side": o["S"],
        "price": o["p"],
        "quantity": o["q"],
        "avg_price": o.get("ap"),
        "order_status": o.get("X"),
    }


def insert_liquidation(conn, row: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO liquidations (symbol, event_time, side, price, quantity, avg_price, order_status)
            VALUES (%(symbol)s, %(event_time)s, %(side)s, %(price)s, %(quantity)s, %(avg_price)s, %(order_status)s)
            ON CONFLICT (symbol, event_time, side, price, quantity) DO NOTHING
            """,
            row,
        )


def run_liquidation_collector(db_url: str | None = None) -> None:  # pragma: no cover - long-running I/O
    """Consume the public !forceOrder@arr stream and persist events.

    Requires the `websocket-client` package and a long-running process (systemd
    service / container). Reconnects on drop. This is the ONLY free source of
    historical liquidations, so it must run continuously to build coverage.
    """
    import psycopg
    import websocket  # type: ignore

    conn = psycopg.connect(_db_url(db_url))

    def on_message(_ws, message):
        row = parse_liquidation_msg(json.loads(message))
        if row:
            insert_liquidation(conn, row)
            _heartbeat(conn, "liquidation_collector", row["symbol"], ok=True)
            conn.commit()

    while True:
        try:
            ws = websocket.WebSocketApp(LIQUIDATION_WS, on_message=on_message)
            ws.run_forever(ping_interval=180)
        except Exception:
            time.sleep(5)  # reconnect


# --- Coverage gate ----------------------------------------------------------

def collection_coverage_days(conn, table: str, symbol: str) -> float:
    """Days between the earliest and latest record — used to gate backtests.

    Forward-collected data must not feed a verdict until this exceeds the
    minimum history the research protocol requires.
    """
    time_col = "ts" if table == "open_interest" else "event_time"
    with conn.cursor() as cur:
        cur.execute(f"SELECT MIN({time_col}), MAX({time_col}) FROM {table} WHERE symbol = %s", (symbol,))
        lo, hi = cur.fetchone()
    if not lo or not hi:
        return 0.0
    return (hi - lo).total_seconds() / 86400.0
