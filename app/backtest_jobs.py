from __future__ import annotations

import hashlib
import json
import os
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.backtest import (
    BacktestRunRepository,
    CandleRepository,
    SimulatedExecutionModel,
    build_config_hash,
    build_dataset_fingerprint,
    build_strategy,
    get_strategy_registry_metadata,
    persist_backtest_outputs,
)

JOB_STATUSES = {"queued", "running", "success", "failed", "cancelled"}


@dataclass
class BacktestJobResult:
    run_id: str
    config_hash: str
    dataset_fingerprint: str
    summary_metrics: dict[str, Any]


class BacktestJobRepository:
    def __init__(self, db_url: str):
        self.db_url = db_url

    def create_job(self, strategy_id: str, payload: dict[str, Any], metadata: dict[str, Any]) -> str:
        job_id = str(uuid.uuid4())
        with psycopg.connect(self.db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO backtest_jobs (
                        id, strategy_id, status, payload_json, reproducibility_json
                    ) VALUES (%s, %s, 'queued', %s::jsonb, %s::jsonb)
                    """,
                    (job_id, strategy_id, json.dumps(payload), json.dumps(metadata)),
                )
                cur.execute(
                    """
                    INSERT INTO job_events (job_id, event_type, event_payload)
                    VALUES (%s, 'queued', %s::jsonb)
                    """,
                    (job_id, json.dumps({"status": "queued"})),
                )
            conn.commit()
        return job_id

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM backtest_jobs WHERE id = %s", (job_id,))
                return cur.fetchone()

    def get_job_result(self, job_id: str) -> dict[str, Any] | None:
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT result_json, result_reference FROM backtest_jobs WHERE id = %s", (job_id,))
                row = cur.fetchone()
                if not row:
                    return None
                return {"result": row["result_json"], "result_reference": row["result_reference"]}

    def request_cancellation(self, job_id: str) -> bool:
        with psycopg.connect(self.db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE backtest_jobs
                    SET cancel_requested = TRUE,
                        status = CASE WHEN status = 'queued' THEN 'cancelled' ELSE status END,
                        started_at = CASE WHEN status = 'queued' THEN started_at ELSE started_at END,
                        finished_at = CASE WHEN status = 'queued' THEN NOW() ELSE finished_at END,
                        updated_at = NOW()
                    WHERE id = %s AND status IN ('queued', 'running')
                    """,
                    (job_id,),
                )
                updated = cur.rowcount > 0
                if updated:
                    cur.execute(
                        """
                        INSERT INTO job_events (job_id, event_type, event_payload)
                        VALUES (%s, 'cancel_requested', %s::jsonb)
                        """,
                        (job_id, json.dumps({"status": "cancel_requested"})),
                    )
            conn.commit()
        return updated

    def claim_next_job(self) -> dict[str, Any] | None:
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    WITH picked AS (
                        SELECT id
                        FROM backtest_jobs
                        WHERE status = 'queued'
                        ORDER BY created_at ASC
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    UPDATE backtest_jobs j
                    SET status = 'running',
                        started_at = NOW(),
                        updated_at = NOW()
                    FROM picked
                    WHERE j.id = picked.id
                    RETURNING j.*
                    """
                )
                row = cur.fetchone()
                if row:
                    cur.execute(
                        "INSERT INTO job_events (job_id, event_type, event_payload) VALUES (%s, 'running', %s::jsonb)",
                        (row["id"], json.dumps({"status": "running"})),
                    )
            conn.commit()
        return row

    def is_cancel_requested(self, job_id: str) -> bool:
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT cancel_requested FROM backtest_jobs WHERE id = %s", (job_id,))
                row = cur.fetchone()
                return bool(row and row["cancel_requested"])

    def mark_success(self, job_id: str, result: dict[str, Any], result_ref: str | None) -> None:
        with psycopg.connect(self.db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE backtest_jobs
                    SET status = 'success', result_json = %s::jsonb, result_reference = %s,
                        finished_at = NOW(), updated_at = NOW(), error_message = NULL
                    WHERE id = %s
                    """,
                    (json.dumps(result), result_ref, job_id),
                )
                cur.execute(
                    "INSERT INTO job_events (job_id, event_type, event_payload) VALUES (%s, 'success', %s::jsonb)",
                    (job_id, json.dumps({"status": "success"})),
                )
            conn.commit()

    def mark_failed(self, job_id: str, error_message: str) -> None:
        with psycopg.connect(self.db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE backtest_jobs
                    SET status = 'failed', error_message = %s, finished_at = NOW(), updated_at = NOW()
                    WHERE id = %s
                    """,
                    (error_message[:2000], job_id),
                )
                cur.execute(
                    "INSERT INTO job_events (job_id, event_type, event_payload) VALUES (%s, 'failed', %s::jsonb)",
                    (job_id, json.dumps({"status": "failed", "error": error_message[:2000]})),
                )
            conn.commit()

    def mark_cancelled(self, job_id: str) -> None:
        with psycopg.connect(self.db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE backtest_jobs
                    SET status = 'cancelled', finished_at = NOW(), updated_at = NOW()
                    WHERE id = %s
                    """,
                    (job_id,),
                )
                cur.execute(
                    "INSERT INTO job_events (job_id, event_type, event_payload) VALUES (%s, 'cancelled', %s::jsonb)",
                    (job_id, json.dumps({"status": "cancelled"})),
                )
            conn.commit()


def build_reproducibility_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    config_serialized = json.dumps(payload, sort_keys=True, default=str)
    metadata = {
        "strategy_version": get_strategy_registry_metadata().get(payload["strategy_id"], {}).get("version", "unknown"),
        "config_hash": hashlib.sha256(config_serialized.encode("utf-8")).hexdigest()[:24],
        "execution_config": payload.get("execution_config", {}),
        "risk_config": payload.get("risk_config", {}),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        metadata["git_commit_hash"] = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        metadata["git_commit_hash"] = None
    return metadata


def execute_job(db_url: str, job_row: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    payload = job_row["payload_json"]
    strategy_id = payload["strategy_id"]
    symbol = payload["candle_query"]["symbol"]
    interval = payload["candle_query"].get("interval", "1m")
    start_time = datetime.fromisoformat(payload["candle_query"]["start_time"]) if payload["candle_query"].get("start_time") else None
    end_time = datetime.fromisoformat(payload["candle_query"]["end_time"]) if payload["candle_query"].get("end_time") else None

    candles = CandleRepository(db_url).get_candles(symbol=symbol, interval=interval, start_time=start_time, end_time=end_time)
    dataset_fingerprint = build_dataset_fingerprint(candles)
    strategy = build_strategy(strategy_id, payload.get("params", {}))
    config_hash = build_config_hash(payload)

    run_repo = BacktestRunRepository(db_url)
    run_id = run_repo.create_run(symbol=symbol, interval=interval, config_hash=config_hash, dataset_fingerprint=dataset_fingerprint.fingerprint, start_time=start_time, end_time=end_time)

    engine = SimulatedExecutionModel(initial_cash=payload.get("execution_config", {}).get("initial_cash", 10000.0))
    result = engine.run(candles, strategy, config_hash=config_hash, dataset_fingerprint=dataset_fingerprint)
    run_repo.persist_completed(run_id, result)

    save_results = payload.get("execution_config", {}).get("save_results", True)
    result_ref = None
    if save_results:
        base_dir = os.getenv("BACKTEST_RESULTS_DIR", "backtest_results")
        result_ref = str(persist_backtest_outputs(base_dir=base_dir, symbol=symbol, interval=interval, result=result))

    job_result = {
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
    return job_result, result_ref
