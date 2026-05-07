import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
import psycopg
from psycopg.rows import dict_row

from app.metrics import api_request_latency_seconds, api_request_total, db_connection_status
from app.observability import StructuredLogger, configure_logging
from app.backtest import (
    BacktestRunRepository,
    CandleRepository,
    get_strategy_registry_metadata,
    strategy_registry,
    SimulatedExecutionModel,
    build_config_hash,
    build_dataset_fingerprint,
    build_strategy,
)

configure_logging()
logger = StructuredLogger("api")

app = FastAPI(title="Shark Bay API", version="0.2.0")



def _parse_cors_origins() -> list[str]:
    import os

    raw = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins



app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class BacktestRunSummary(BaseModel):
    run_id: UUID
    status: str
    symbol: str
    interval: str
    start_time: datetime | None
    end_time: datetime | None
    config_hash: str
    dataset_fingerprint: str
    created_at: datetime


class BacktestRunDetail(BacktestRunSummary):
    deterministic_summary_timestamp: datetime | None
    failure_reason: str | None
    total_return: float | None
    final_equity: float | None
    max_drawdown: float | None
    profit_factor: float | None
    average_trade_return: float | None
    trade_count: int | None
    win_rate: float | None


class BacktestFill(BaseModel):
    fill_index: int
    open_time: datetime
    prev_position: int
    new_position: int
    exec_price: float


class BacktestEquityPoint(BaseModel):
    point_index: int
    open_time: datetime
    equity: float


class BacktestRunRequest(BaseModel):
    strategy_name: str
    strategy_params: dict[str, Any] = {}
    symbol: str
    interval: str = "1m"
    start_time: datetime | None = None
    end_time: datetime | None = None
    save_results: bool = True


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
def get_candles(
    symbol: str = Query(..., min_length=3, max_length=20, pattern=r"^[A-Z0-9]+$"),
    interval: str = Query("1m", pattern=r"^(1m)$"),
    limit: int = Query(100, ge=1, le=20000),
):
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

    return {
        "latest_candle_time": last_candle_time,
        "last_candle_time": last_candle_time,
        "total_candle_count": total_candle_count,
        "collector_status": collector_status,
        "last_backfill_status": hb.get("last_backfill_status"),
        "last_backfill_candle_count": hb.get("last_backfill_candle_count"),
        "last_backfill_time": hb.get("last_backfill_time"),
        "heartbeat": hb,
    }


@app.get("/metrics")
def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


def _get_backtest_repo() -> BacktestRunRepository:
    return BacktestRunRepository(get_db_url())


@app.get("/strategies")
def list_strategies():
    return {"strategies": get_strategy_registry_metadata()}


@app.get("/backtests", response_model=list[BacktestRunSummary])
def list_backtests(limit: int = Query(50, ge=1, le=500)):
    try:
        return _get_backtest_repo().list_runs(limit=limit)
    except psycopg.Error:
        logger.exception("database_error_listing_backtests")
        raise HTTPException(status_code=500, detail="Database error")


@app.get("/backtests/{run_id}", response_model=BacktestRunDetail)
def get_backtest(run_id: UUID):
    try:
        row = _get_backtest_repo().get_run_with_metrics(str(run_id))
    except psycopg.Error:
        logger.exception("database_error_getting_backtest", run_id=str(run_id))
        raise HTTPException(status_code=500, detail="Database error")
    if row is None:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    return row


@app.get("/backtests/{run_id}/fills", response_model=list[BacktestFill])
def get_backtest_fills(run_id: UUID):
    try:
        repo = _get_backtest_repo()
        row = repo.get_run_with_metrics(str(run_id))
        if row is None:
            raise HTTPException(status_code=404, detail="Backtest run not found")
        return repo.get_fills(str(run_id))
    except psycopg.Error:
        logger.exception("database_error_getting_backtest_fills", run_id=str(run_id))
        raise HTTPException(status_code=500, detail="Database error")


@app.get("/backtests/{run_id}/equity-curve", response_model=list[BacktestEquityPoint])
def get_backtest_equity_curve(run_id: UUID):
    try:
        repo = _get_backtest_repo()
        row = repo.get_run_with_metrics(str(run_id))
        if row is None:
            raise HTTPException(status_code=404, detail="Backtest run not found")
        return repo.get_equity_curve(str(run_id))
    except psycopg.Error:
        logger.exception("database_error_getting_backtest_equity_curve", run_id=str(run_id))
        raise HTTPException(status_code=500, detail="Database error")


@app.post("/backtests/run")
def run_backtest(request: BacktestRunRequest):
    if request.strategy_name not in get_strategy_registry_metadata():
        raise HTTPException(status_code=400, detail="Unknown strategy_name")
    if request.interval != "1m":
        raise HTTPException(status_code=400, detail="Only interval=1m is supported")

    config = {
        "strategy_name": request.strategy_name,
        "strategy_params": request.strategy_params,
        "symbol": request.symbol,
        "interval": request.interval,
        "start_time": request.start_time.isoformat() if request.start_time else None,
        "end_time": request.end_time.isoformat() if request.end_time else None,
        "initial_cash": 10_000.0,
    }
    config_hash = build_config_hash(config)
    db_url = get_db_url()
    candles = CandleRepository(db_url).get_candles(
        symbol=request.symbol,
        interval=request.interval,
        start_time=request.start_time,
        end_time=request.end_time,
    )
    dataset_fingerprint = build_dataset_fingerprint(candles)
    try:
        validated_params = strategy_registry.validate_params(request.strategy_name, request.strategy_params)
        strategy = build_strategy(request.strategy_name, validated_params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    engine = SimulatedExecutionModel(initial_cash=10_000.0)
    repo = BacktestRunRepository(db_url)
    run_id = repo.create_run(
        symbol=request.symbol,
        interval=request.interval,
        config_hash=config_hash,
        dataset_fingerprint=dataset_fingerprint.fingerprint,
        start_time=request.start_time,
        end_time=request.end_time,
    )
    try:
        result = engine.run(candles, strategy, config_hash=config_hash, dataset_fingerprint=dataset_fingerprint)
        repo.persist_completed(run_id, result)
    except Exception as exc:
        repo.mark_failed(run_id, str(exc))
        raise HTTPException(status_code=500, detail=f"Backtest failed: {exc}")

    return {
        "run_id": run_id,
        "config_hash": result.config_hash,
        "dataset_fingerprint": result.dataset_fingerprint,
        "summary_metrics": {
            "total_return": result.total_return_pct,
            "final_equity": result.final_equity,
            "max_drawdown": result.max_drawdown_pct,
            "profit_factor": result.profit_factor,
            "average_trade_return": result.average_trade_return_pct,
            "trade_count": result.trades,
            "win_rate": result.win_rate_pct,
        },
    }


@app.exception_handler(RuntimeError)
def runtime_error_handler(_, exc: RuntimeError):
    logger.exception("runtime_error", error=str(exc))
    return JSONResponse(status_code=500, content={"detail": str(exc)})
