import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
import psycopg
from psycopg.rows import dict_row

from app.metrics import api_request_latency_seconds, api_request_total, db_connection_status
from app.observability import StructuredLogger, configure_logging

configure_logging()
logger = StructuredLogger("api")

app = FastAPI(title="Shark Bay API", version="0.2.0")


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_seconds = time.time() - start
    duration_ms = round(duration_seconds * 1000, 2)
    api_request_total.labels(method=request.method, path=request.url.path, status_code=str(response.status_code)).inc()
    api_request_latency_seconds.labels(method=request.method, path=request.url.path).observe(duration_seconds)
    logger.info(
        "api_request",
        method=request.method,
        path=request.url.path,
        query=str(request.url.query),
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
    return response


def get_db_url() -> str:
    import os

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
    return {"status": "OK"}


@app.get("/health/ready")
def health_ready() -> dict[str, str]:
    try:
        with psycopg.connect(get_db_url()) as conn:
            db_connection_status.labels(service="api").set(1)
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return {"status": "READY"}
    except Exception:
        db_connection_status.labels(service="api").set(0)
        raise HTTPException(status_code=503, detail="Database unavailable")


@app.get("/health/live")
def health_live() -> dict[str, str]:
    return {"status": "LIVE"}


@app.get("/candles")
def get_candles(symbol: str = Query(..., min_length=3, max_length=20, pattern=r"^[A-Z0-9]+$"), interval: str = Query("1m", pattern=r"^(1m)$"), limit: int = Query(100, ge=1, le=1000)):
    table = "candles_1m"
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
        logger.exception("database_error_fetching_candles")
        raise HTTPException(status_code=500, detail="Database error")

    candles = [{k: decimal_to_float(v) for k, v in row.items()} for row in rows]
    return {"symbol": symbol, "interval": interval, "limit": limit, "count": len(candles), "candles": candles}


@app.get("/ingestion/status")
def ingestion_status():
    try:
        with psycopg.connect(get_db_url(), row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT MAX(open_time) AS last_candle_time, COUNT(*) AS total_candle_count FROM candles_1m")
                row = cur.fetchone() or {}
                cur.execute("SELECT * FROM collector_heartbeat WHERE collector_name='ingestor'")
                hb = cur.fetchone() or {}
    except psycopg.Error:
        logger.exception("database_error_fetching_ingestion_status")
        raise HTTPException(status_code=500, detail="Database error")

    last_candle_time = row.get("last_candle_time")
    total_candle_count = int(row.get("total_candle_count") or 0)

    collector_status = "unknown"
    if hb.get("last_heartbeat_at"):
        age_seconds = (datetime.now(timezone.utc) - hb["last_heartbeat_at"]).total_seconds()
        collector_status = "running" if age_seconds <= 180 else "stale"

    return {"last_candle_time": last_candle_time, "total_candle_count": total_candle_count, "collector_status": collector_status, "heartbeat": hb}


@app.get("/metrics")
def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.exception_handler(RuntimeError)
def runtime_error_handler(_, exc: RuntimeError):
    logger.exception("runtime_error", error=str(exc))
    return JSONResponse(status_code=500, content={"detail": str(exc)})
