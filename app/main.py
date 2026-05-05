import os
import signal
import time

from prometheus_client import start_http_server
from datetime import datetime, timezone
from decimal import Decimal

from app.metrics import (
    candle_insert_total,
    db_connection_status,
    duplicate_candle_total,
    ingest_error_total,
    latest_candle_timestamp,
    missing_candle_gap_count,
    rest_backfill_candles_inserted_total,
    rest_backfill_completed_total,
    rest_backfill_failed_total,
    rest_backfill_requested_total,
    websocket_reconnect_total,
)
from app.observability import StructuredLogger, configure_logging

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"


class IngestionMetrics:
    def __init__(self):
        self.poll_count = 0
        self.success_count = 0
        self.error_count = 0
        self.retry_count = 0
        self.reconnect_count = 0
        self.last_success_at = None
        self.last_backfill_status = "not_run"
        self.last_backfill_candle_count = 0
        self.last_backfill_time = None


def sanitized_db_url(db_url: str) -> str:
    try:
        from urllib.parse import urlsplit, urlunsplit

        parsed = urlsplit(db_url)
        if parsed.username is None and parsed.password is None:
            return db_url
        netloc = parsed.hostname or ""
        if parsed.port:
            netloc = f"{netloc}:{parsed.port}"
        if parsed.username and parsed.password:
            netloc = f"{parsed.username}:***@{netloc}"
        elif parsed.username:
            netloc = f"{parsed.username}@{netloc}"
        return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
    except Exception:
        return "<unparseable DATABASE_URL>"


def ms_to_dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def fetch_latest_klines(symbol: str = "BTCUSDT", interval: str = "1m", limit: int = 2):
    import requests

    response = requests.get(
        BINANCE_KLINES_URL,
        params={"symbol": symbol, "interval": interval, "limit": limit},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def fetch_klines_range(symbol: str, interval: str, start_ms: int, end_ms: int, limit: int):
    import requests

    response = requests.get(
        BINANCE_KLINES_URL,
        params={"symbol": symbol, "interval": interval, "startTime": start_ms, "endTime": end_ms, "limit": limit},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def parse_kline(symbol: str, k):
    return {
        "symbol": symbol,
        "open_time": ms_to_dt(int(k[0])),
        "open": Decimal(k[1]),
        "high": Decimal(k[2]),
        "low": Decimal(k[3]),
        "close": Decimal(k[4]),
        "volume": Decimal(k[5]),
        "close_time": ms_to_dt(int(k[6])),
        "trades": int(k[8]),
        "taker_buy_base": Decimal(k[9]),
        "taker_buy_quote": Decimal(k[10]),
    }


def upsert_candle(conn, candle):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO candles_1m (
                symbol, open_time, close_time, open, high, low, close, volume,
                trades, taker_buy_base, taker_buy_quote
            ) VALUES (
                %(symbol)s, %(open_time)s, %(close_time)s, %(open)s, %(high)s, %(low)s,
                %(close)s, %(volume)s, %(trades)s, %(taker_buy_base)s, %(taker_buy_quote)s
            )
            ON CONFLICT (symbol, open_time)
            DO UPDATE SET
                close_time = EXCLUDED.close_time,
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                trades = EXCLUDED.trades,
                taker_buy_base = EXCLUDED.taker_buy_base,
                taker_buy_quote = EXCLUDED.taker_buy_quote
            RETURNING (xmax = 0) AS inserted;
            """,
            candle,
        )
        return cur.fetchone()[0]


def init_schema(conn):
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        ddl = f.read()
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()


def get_latest_stored_open_time(conn, symbol: str):
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(open_time) FROM candles_1m WHERE symbol = %s", (symbol,))
        row = cur.fetchone()
    return row[0] if row else None


def recover_recent_gap(conn, logger, symbol: str, metrics: IngestionMetrics):
    if os.getenv("ENABLE_GAP_BACKFILL", "true").lower() != "true":
        metrics.last_backfill_status = "disabled"
        metrics.last_backfill_candle_count = 0
        metrics.last_backfill_time = datetime.now(timezone.utc)
        return

    max_candles = int(os.getenv("BACKFILL_MAX_CANDLES_PER_RUN", "500"))
    sleep_seconds = float(os.getenv("REST_BACKFILL_SLEEP_SECONDS", "0.2"))
    interval_ms = 60_000

    latest_stored = get_latest_stored_open_time(conn, symbol)
    latest_closed_kline = fetch_latest_klines(symbol=symbol, interval="1m", limit=2)[-2]
    latest_closed_open_ms = int(latest_closed_kline[0])

    if latest_stored is None:
        missing_candle_gap_count.set(0)
        metrics.last_backfill_status = "skipped_no_local_anchor"
        metrics.last_backfill_candle_count = 0
        metrics.last_backfill_time = datetime.now(timezone.utc)
        return

    next_expected_ms = int(latest_stored.timestamp() * 1000) + interval_ms
    gap_count = max(0, ((latest_closed_open_ms - next_expected_ms) // interval_ms) + 1)
    missing_candle_gap_count.set(gap_count)
    if gap_count <= 0:
        metrics.last_backfill_status = "no_gap"
        metrics.last_backfill_candle_count = 0
        metrics.last_backfill_time = datetime.now(timezone.utc)
        return

    logger.info("gap_detected", symbol=symbol, latest_stored_open_time=latest_stored, latest_closed_open_time=ms_to_dt(latest_closed_open_ms), gap_count=gap_count)
    rest_backfill_requested_total.inc()
    logger.info("backfill_started", symbol=symbol, gap_count=gap_count, max_candles=max_candles)
    candles_to_fetch = min(gap_count, max_candles)
    end_ms = next_expected_ms + (candles_to_fetch - 1) * interval_ms
    try:
        missing_start_time = ms_to_dt(next_expected_ms)
        missing_end_time = ms_to_dt(end_ms)
        klines = fetch_klines_range(symbol, "1m", next_expected_ms, end_ms, candles_to_fetch)
        logger.info("candles_fetched", symbol=symbol, fetched_count=len(klines))
        inserted_count = 0
        for k in klines:
            candle = parse_kline(symbol, k)
            inserted = upsert_candle(conn, candle)
            candle_insert_total.inc()
            if inserted:
                inserted_count += 1
            else:
                duplicate_candle_total.inc()
            latest_candle_timestamp.set(candle["open_time"].timestamp())
        rest_backfill_candles_inserted_total.inc(inserted_count)
        rest_backfill_completed_total.inc()
        metrics.last_backfill_status = "completed"
        metrics.last_backfill_candle_count = inserted_count
        metrics.last_backfill_time = datetime.now(timezone.utc)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rest_backfill_events (
                    symbol, interval, missing_start_time, missing_end_time,
                    recovered_count, status, error_message
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (symbol, "1m", missing_start_time, missing_end_time, inserted_count, "completed", None),
            )
        conn.commit()
        logger.info("candles_inserted", symbol=symbol, inserted_count=inserted_count)
        logger.info("backfill_completed", symbol=symbol, inserted_count=inserted_count)
        time.sleep(sleep_seconds)
    except Exception as exc:
        rest_backfill_failed_total.inc()
        metrics.last_backfill_status = "failed"
        metrics.last_backfill_candle_count = 0
        metrics.last_backfill_time = datetime.now(timezone.utc)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rest_backfill_events (
                    symbol, interval, missing_start_time, missing_end_time,
                    recovered_count, status, error_message
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (symbol, "1m", ms_to_dt(next_expected_ms), ms_to_dt(end_ms), 0, "failed", str(exc)),
            )
        conn.commit()
        logger.exception("backfill_failed", symbol=symbol, error=str(exc))


def write_heartbeat(conn, symbol: str, metrics: IngestionMetrics):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO collector_heartbeat (collector_name, symbol, last_heartbeat_at, poll_count, success_count, error_count, retry_count, reconnect_count, last_backfill_status, last_backfill_candle_count, last_backfill_time)
            VALUES ('ingestor', %s, NOW(), %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (collector_name)
            DO UPDATE SET symbol = EXCLUDED.symbol, last_heartbeat_at = EXCLUDED.last_heartbeat_at,
            poll_count = EXCLUDED.poll_count, success_count = EXCLUDED.success_count,
            error_count = EXCLUDED.error_count, retry_count = EXCLUDED.retry_count, reconnect_count = EXCLUDED.reconnect_count,
            last_backfill_status = EXCLUDED.last_backfill_status, last_backfill_candle_count = EXCLUDED.last_backfill_candle_count,
            last_backfill_time = EXCLUDED.last_backfill_time
            """,
            (
                symbol,
                metrics.poll_count,
                metrics.success_count,
                metrics.error_count,
                metrics.retry_count,
                metrics.reconnect_count,
                metrics.last_backfill_status,
                metrics.last_backfill_candle_count,
                metrics.last_backfill_time,
            ),
        )
    conn.commit()


def detect_missing_candle_structure(conn, symbol: str):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO missing_candle_events (symbol, expected_open_time, detected_at, reason)
            SELECT %s, NOW() - INTERVAL '1 minute', NOW(), 'placeholder_detection'
            WHERE NOT EXISTS (
              SELECT 1 FROM missing_candle_events WHERE symbol = %s AND expected_open_time = NOW() - INTERVAL '1 minute'
            )
            """,
            (symbol, symbol),
        )
    conn.commit()


def run():
    configure_logging()
    logger = StructuredLogger("ingestor")
    running = True
    metrics = IngestionMetrics()

    def handle_shutdown(signum, _frame):
        nonlocal running
        running = False
        logger.info("shutdown_signal_received", signal=signum)

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    db_url = os.environ["DATABASE_URL"]
    poll_seconds = int(os.getenv("POLL_SECONDS", "10"))
    symbol = os.getenv("SYMBOL", "BTCUSDT")

    metrics_port = int(os.getenv("METRICS_PORT", "9100"))
    start_http_server(metrics_port)
    logger.info("ingestor_start", symbol=symbol, poll_seconds=poll_seconds, database_url=sanitized_db_url(db_url), metrics_port=metrics_port)

    import psycopg

    while running:
        try:
            with psycopg.connect(db_url) as conn:
                init_schema(conn)
                logger.info("db_connected")
                db_connection_status.labels(service="ingestor").set(1)
                recover_recent_gap(conn, logger, symbol, metrics)
                while running:
                    metrics.poll_count += 1
                    try:
                        klines = fetch_latest_klines(symbol=symbol, interval="1m", limit=2)
                        for k in klines:
                            candle = parse_kline(symbol, k)
                            inserted = upsert_candle(conn, candle)
                            candle_insert_total.inc()
                            if not inserted:
                                duplicate_candle_total.inc()
                            latest_candle_timestamp.set(candle["open_time"].timestamp())
                            logger.info("candle_upsert", symbol=symbol, open_time=candle["open_time"], inserted=inserted)
                        metrics.success_count += 1
                        metrics.last_success_at = datetime.now(timezone.utc).isoformat()
                        detect_missing_candle_structure(conn, symbol)
                    except Exception as exc:
                        metrics.error_count += 1
                        metrics.retry_count += 1
                        ingest_error_total.inc()
                        logger.exception("ingestion_error", error=str(exc), retry_count=metrics.retry_count)
                    write_heartbeat(conn, symbol, metrics)
                    logger.info("ingestion_metrics", **metrics.__dict__)
                    time.sleep(poll_seconds)
        except Exception as exc:
            metrics.reconnect_count += 1
            websocket_reconnect_total.inc()
            db_connection_status.labels(service="ingestor").set(0)
            logger.exception("database_connection_error", error=str(exc), reconnect_count=metrics.reconnect_count)
            time.sleep(3)

    logger.info("ingestor_stopped")


if __name__ == "__main__":
    run()
