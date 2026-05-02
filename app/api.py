import logging
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
import psycopg
from psycopg.rows import dict_row


def configure_logging() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
        force=True,
    )


configure_logging()
logger = logging.getLogger("api")

app = FastAPI(title="Shark Bay API", version="0.1.0")


def get_db_url() -> str:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set")
    return db_url


def decimal_to_float(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    return v


@app.get("/health")
def health() -> dict[str, str]:
    logger.info("health check called")
    return {"status": "OK"}


@app.get("/candles")
def get_candles(
    symbol: str = Query(..., min_length=3, max_length=20, pattern=r"^[A-Z0-9]+$"),
    interval: str = Query("1m", pattern=r"^(1m)$"),
    limit: int = Query(100, ge=1, le=1000),
):
    logger.info("candles query symbol=%s interval=%s limit=%s", symbol, interval, limit)
    table = "candles_1m" if interval == "1m" else None
    if table is None:
        raise HTTPException(status_code=400, detail="Unsupported interval")

    try:
        with psycopg.connect(get_db_url(), row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT symbol, open_time, close_time, open, high, low, close, volume,
                           trades, taker_buy_base, taker_buy_quote
                    FROM {table}
                    WHERE symbol = %s
                    ORDER BY open_time DESC
                    LIMIT %s
                    """,
                    (symbol, limit),
                )
                rows = cur.fetchall()
    except psycopg.Error:
        logger.exception("database error fetching candles")
        raise HTTPException(status_code=500, detail="Database error")

    candles = []
    for row in rows:
        candles.append({k: decimal_to_float(v) for k, v in row.items()})

    return {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
        "count": len(candles),
        "candles": candles,
    }


@app.get("/ingestion/status")
def ingestion_status():
    logger.info("ingestion status called")
    try:
        with psycopg.connect(get_db_url(), row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT MAX(open_time) AS last_candle_time,
                           COUNT(*) AS total_candle_count
                    FROM candles_1m
                    """
                )
                row = cur.fetchone() or {}
    except psycopg.Error:
        logger.exception("database error fetching ingestion status")
        raise HTTPException(status_code=500, detail="Database error")

    last_candle_time = row.get("last_candle_time")
    total_candle_count = int(row.get("total_candle_count") or 0)

    collector_status = "unknown"
    if last_candle_time:
        age_seconds = (datetime.now(timezone.utc) - last_candle_time).total_seconds()
        collector_status = "running" if age_seconds <= 180 else "stale"

    return {
        "last_candle_time": last_candle_time,
        "total_candle_count": total_candle_count,
        "collector_status": collector_status,
    }


@app.exception_handler(RuntimeError)
def runtime_error_handler(_, exc: RuntimeError):
    logger.exception("runtime error")
    return JSONResponse(status_code=500, content={"detail": str(exc)})
