import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
import psycopg
import requests
import psutil
import platform
from psycopg.rows import dict_row

from app.metrics import api_request_latency_seconds, api_request_total, db_connection_status
from app.observability import StructuredLogger, configure_logging
from app.features import build_snapshot
from app.strategy_registry import list_strategy_specs
from app.experiments import ExperimentResult, ResearchExperimentRepository, run_deterministic_placeholder_experiment
from app.research_analytics import build_research_analytics
from app.dataset_splits import build_split_payload
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


def _probe_service(name: str, url: str | None, timeout_seconds: float = 3.0) -> dict[str, Any]:
    checked_at = datetime.now(timezone.utc).isoformat()
    if not url:
        return {"service": name, "status": "not_configured", "latency_ms": None, "checked_at": checked_at, "detail": "url not configured"}
    start = time.time()
    try:
        response = requests.get(url, timeout=timeout_seconds)
        latency_ms = round((time.time() - start) * 1000, 2)
        if response.ok:
            status = "healthy" if latency_ms <= 1500 else "degraded"
            return {"service": name, "status": status, "latency_ms": latency_ms, "checked_at": checked_at}
        return {"service": name, "status": "unreachable", "latency_ms": latency_ms, "checked_at": checked_at, "detail": f"http {response.status_code}"}
    except requests.Timeout:
        latency_ms = round((time.time() - start) * 1000, 2)
        return {"service": name, "status": "timeout", "latency_ms": latency_ms, "checked_at": checked_at, "detail": "request timeout"}
    except Exception as exc:
        latency_ms = round((time.time() - start) * 1000, 2)
        return {"service": name, "status": "unreachable", "latency_ms": latency_ms, "checked_at": checked_at, "detail": str(exc)}


@app.get("/ops/health")
def ops_health() -> dict[str, Any]:
    import os

    services = [
        ("prometheus", os.getenv("PROMETHEUS_URL", "http://prometheus:9090/-/healthy")),
        ("grafana", os.getenv("GRAFANA_URL", "http://grafana:3000/api/health")),
        ("cadvisor", os.getenv("CADVISOR_URL", "http://cadvisor:8080/metrics")),
    ]
    checks = [_probe_service(name, url) for name, url in services]
    return {"checked_at": datetime.now(timezone.utc).isoformat(), "services": checks}



@app.get("/ops/infrastructure")
def ops_infrastructure() -> dict[str, Any]:
    import os

    now = datetime.now(timezone.utc).isoformat()
    vm = psutil.virtual_memory()
    du = psutil.disk_usage('/')
    boot = datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc)
    uptime_seconds = int((datetime.now(timezone.utc) - boot).total_seconds())
    dio = psutil.disk_io_counters()
    nio = psutil.net_io_counters()

    db_size_bytes = None
    try:
        with psycopg.connect(get_db_url()) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_database_size(current_database())")
                row = cur.fetchone()
                db_size_bytes = int(row[0]) if row and row[0] is not None else None
    except Exception:
        db_size_bytes = None

    service_checks = [
        _probe_service("api", os.getenv("API_INTERNAL_URL", "http://api:8000/health")),
        _probe_service("ingestor", os.getenv("INGESTOR_METRICS_URL", "http://ingestor:9100/")),
        _probe_service("db", os.getenv("DB_HEALTH_URL", "http://api:8000/health/ready")),
        _probe_service("prometheus", os.getenv("PROMETHEUS_URL", "http://prometheus:9090/-/healthy")),
        _probe_service("grafana", os.getenv("GRAFANA_URL", "http://grafana:3000/api/health")),
        _probe_service("cadvisor", os.getenv("CADVISOR_URL", "http://cadvisor:8080/metrics")),
        _probe_service("research-ui", os.getenv("RESEARCH_UI_URL", "http://research-ui:8501/")),
    ]

    known_ports = {
        "api": "8000", "ingestor": "9100", "db": "5432", "prometheus": "9090", "grafana": "3000", "cadvisor": "8080", "research-ui": "8501"
    }
    services = []
    for check in service_checks:
        services.append({
            "service": check["service"],
            "status": check["status"],
            "latency_ms": check.get("latency_ms"),
            "detail": check.get("detail"),
            "uptime": "not_available",
            "restart_count": None,
            "port": known_ports.get(check["service"]),
            "notes": "read-only probe",
        })

    return {
        "checked_at": now,
        "host_overview": {
            "instance_status": "healthy",
            "cpu_usage_pct": round(psutil.cpu_percent(interval=0.1), 2),
            "memory_usage_pct": round(vm.percent, 2),
            "disk_usage_pct": round(du.percent, 2),
            "network_traffic": {"bytes_sent": nio.bytes_sent, "bytes_recv": nio.bytes_recv},
            "disk_traffic": {"read_bytes": dio.read_bytes if dio else 0, "write_bytes": dio.write_bytes if dio else 0},
            "uptime_seconds": uptime_seconds,
            "host_name": platform.node(),
            "platform": platform.platform(),
            "kernel": platform.release(),
            "docker_engine_reachable": None,
        },
        "docker_services": services,
        "resource_trends": {
            "cpu": [], "memory": [], "disk_io": [], "network_io": []
        },
        "storage": {
            "db_size_bytes": db_size_bytes,
            "disk_remaining_bytes": du.free,
        },
    }

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


@app.get("/strategies/registry")
def list_strategy_registry(
    status: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    interval: str | None = Query(default=None),
):
    return {"strategies": list_strategy_specs(status=status, symbol=symbol, interval=interval)}


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


@app.get("/research/features")
def research_features(
    symbol: str = Query("BTCUSDT", min_length=3, max_length=20, pattern=r"^[A-Z0-9]+$"),
    interval: str = Query("1m", pattern=r"^(1m)$"),
    lookback_hours: int = Query(24, ge=1, le=24*30),
):
    try:
        return build_snapshot(symbol=symbol, interval=interval, lookback_hours=lookback_hours)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except psycopg.Error:
        logger.exception("database_error_fetching_research_features")
        raise HTTPException(status_code=500, detail="Database error")




def _get_research_experiment_repo() -> ResearchExperimentRepository:
    repo = ResearchExperimentRepository(get_db_url())
    repo.ensure_schema()
    return repo


@app.post("/research/experiments/run")
def run_research_experiment(
    strategy: str = Query("ema_cross_v1"),
    symbol: str = Query("BTCUSDT", min_length=3, max_length=20, pattern=r"^[A-Z0-9]+$"),
    interval: str = Query("1m", pattern=r"^(1m)$"),
    lookback_hours: int = Query(24, ge=1, le=24*30),
    persist: bool = Query(False),
    split_mode: str = Query("ratio", pattern=r"^(ratio|rolling)$"),
    include_holdout: bool = Query(False),
):
    try:
        result = run_deterministic_placeholder_experiment(
            strategy_name=strategy,
            symbol=symbol,
            interval=interval,
            lookback_hours=lookback_hours,
            db_url=get_db_url(),
        )
        result_payload = result.__dict__.copy()
        result_payload["split_mode"] = split_mode
        if persist:
            _get_research_experiment_repo().upsert(result)
        if not include_holdout:
            result_payload.pop("holdout_metrics", None)
        return result_payload
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except psycopg.Error:
        logger.exception("database_error_running_research_experiment")
        raise HTTPException(status_code=500, detail="Database error")


@app.get("/research/experiments/latest")
def latest_research_experiments(
    symbol: str = Query("BTCUSDT", min_length=3, max_length=20, pattern=r"^[A-Z0-9]+$"),
    interval: str = Query("1m", pattern=r"^(1m)$"),
    limit: int = Query(20, ge=1, le=200),
):
    try:
        rows = _get_research_experiment_repo().list_latest(symbol=symbol, interval=interval, limit=limit)
    except psycopg.Error:
        logger.exception("database_error_listing_research_experiments")
        raise HTTPException(status_code=500, detail="Database error")
    return {"experiments": rows}




@app.get("/research/analytics")
def research_analytics(
    symbol: str = Query("BTCUSDT", min_length=3, max_length=20, pattern=r"^[A-Z0-9]+$"),
    interval: str = Query("1m", pattern=r"^(1m)$"),
    limit: int = Query(100, ge=1, le=500),
):
    try:
        rows = _get_research_experiment_repo().list_latest(symbol=symbol, interval=interval, limit=limit)
    except psycopg.Error:
        logger.exception("database_error_listing_research_analytics")
        raise HTTPException(status_code=500, detail="Database error")
    return build_research_analytics(rows, recent_limit=min(limit, 20))


@app.get("/research/dataset/splits")
def research_dataset_splits(
    symbol: str = Query("BTCUSDT", min_length=3, max_length=20, pattern=r"^[A-Z0-9]+$"),
    interval: str = Query("1m", pattern=r"^(1m)$"),
    split_mode: str = Query("ratio", pattern=r"^(ratio|rolling)$"),
    include_holdout: bool = Query(False),
    lookback_days: int = Query(365, ge=30, le=3650),
    train_days: int = Query(180, ge=1, le=3650),
    validation_days: int = Query(30, ge=1, le=3650),
    test_days: int = Query(30, ge=1, le=3650),
    step_days: int | None = Query(None, ge=1, le=3650),
):
    end_time = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start_time = end_time - timedelta(days=lookback_days)
    candles = CandleRepository(get_db_url()).get_candles(symbol=symbol, interval=interval, start_time=start_time, end_time=end_time)
    return build_split_payload(
        symbol=symbol,
        interval=interval,
        candles=candles,
        split_mode=split_mode,
        include_holdout=include_holdout,
        train_days=train_days,
        validation_days=validation_days,
        test_days=test_days,
        step_days=step_days,
    )
@app.get("/research/experiments/{experiment_id}")
def get_research_experiment(experiment_id: str):
    try:
        row = _get_research_experiment_repo().get(experiment_id)
    except psycopg.Error:
        logger.exception("database_error_fetching_research_experiment")
        raise HTTPException(status_code=500, detail="Database error")
    if not row:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return row

@app.exception_handler(RuntimeError)
def runtime_error_handler(_, exc: RuntimeError):
    logger.exception("runtime_error", error=str(exc))
    return JSONResponse(status_code=500, content={"detail": str(exc)})
