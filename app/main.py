import os
import time
from datetime import datetime, timezone
from decimal import Decimal


BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"


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
                taker_buy_quote = EXCLUDED.taker_buy_quote;
            """,
            candle,
        )
    conn.commit()


def init_schema(conn):
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        ddl = f.read()
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()


def run():
    db_url = os.environ["DATABASE_URL"]
    poll_seconds = int(os.getenv("POLL_SECONDS", "10"))
    symbol = os.getenv("SYMBOL", "BTCUSDT")

    import psycopg

    with psycopg.connect(db_url) as conn:
        init_schema(conn)
        while True:
            try:
                klines = fetch_latest_klines(symbol=symbol, interval="1m", limit=2)
                for k in klines:
                    candle = parse_kline(symbol, k)
                    upsert_candle(conn, candle)
                print(f"[{datetime.now(timezone.utc).isoformat()}] Upserted {len(klines)} {symbol} candles")
            except Exception as exc:
                print(f"Ingestion error: {exc}")
            time.sleep(poll_seconds)


if __name__ == "__main__":
    run()
