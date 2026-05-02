import os
import signal
import time
from datetime import datetime, timezone
from decimal import Decimal

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


def write_heartbeat(conn, symbol: str, metrics: IngestionMetrics):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO collector_heartbeat (collector_name, symbol, last_heartbeat_at, poll_count, success_count, error_count, retry_count, reconnect_count)
            VALUES ('ingestor', %s, NOW(), %s, %s, %s, %s, %s)
            ON CONFLICT (collector_name)
            DO UPDATE SET symbol = EXCLUDED.symbol, last_heartbeat_at = EXCLUDED.last_heartbeat_at,
            poll_count = EXCLUDED.poll_count, success_count = EXCLUDED.success_count,
            error_count = EXCLUDED.error_count, retry_count = EXCLUDED.retry_count, reconnect_count = EXCLUDED.reconnect_count
            """,
            (symbol, metrics.poll_count, metrics.success_count, metrics.error_count, metrics.retry_count, metrics.reconnect_count),
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

    logger.info("ingestor_start", symbol=symbol, poll_seconds=poll_seconds, database_url=sanitized_db_url(db_url))

    import psycopg

    while running:
        try:
            with psycopg.connect(db_url) as conn:
                init_schema(conn)
                logger.info("db_connected")
                while running:
                    metrics.poll_count += 1
                    try:
                        klines = fetch_latest_klines(symbol=symbol, interval="1m", limit=2)
                        for k in klines:
                            candle = parse_kline(symbol, k)
                            inserted = upsert_candle(conn, candle)
                            logger.info("candle_upsert", symbol=symbol, open_time=candle["open_time"], inserted=inserted)
                        metrics.success_count += 1
                        metrics.last_success_at = datetime.now(timezone.utc).isoformat()
                        detect_missing_candle_structure(conn, symbol)
                    except Exception as exc:
                        metrics.error_count += 1
                        metrics.retry_count += 1
                        logger.exception("ingestion_error", error=str(exc), retry_count=metrics.retry_count)
                    write_heartbeat(conn, symbol, metrics)
                    logger.info("ingestion_metrics", **metrics.__dict__)
                    time.sleep(poll_seconds)
        except Exception as exc:
            metrics.reconnect_count += 1
            logger.exception("database_connection_error", error=str(exc), reconnect_count=metrics.reconnect_count)
            time.sleep(3)

    logger.info("ingestor_stopped")


if __name__ == "__main__":
    run()
