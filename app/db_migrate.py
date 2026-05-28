from __future__ import annotations

import os
import time

import psycopg
from psycopg.rows import dict_row

IDEMPOTENT_QUEUE_MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS backtest_jobs (
  id UUID PRIMARY KEY,
  strategy_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'success', 'failed', 'cancelled')),
  payload_json JSONB NOT NULL,
  reproducibility_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  result_json JSONB,
  result_reference TEXT,
  error_message TEXT,
  retry_count INTEGER NOT NULL DEFAULT 0,
  cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_backtest_jobs_status_created_at ON backtest_jobs (status, created_at ASC);

CREATE TABLE IF NOT EXISTS job_events (
  id BIGSERIAL PRIMARY KEY,
  job_id UUID NOT NULL REFERENCES backtest_jobs(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  event_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def get_db_url() -> str:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set")
    return db_url


def run_queue_migration(db_url: str) -> None:
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(IDEMPOTENT_QUEUE_MIGRATION_SQL)
        conn.commit()


def wait_for_table(db_url: str, table_name: str, timeout_seconds: float = 60.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with psycopg.connect(db_url, row_factory=dict_row) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT to_regclass(%s) AS table_name", (f"public.{table_name}",))
                    row = cur.fetchone()
                    if row and row["table_name"] == f"public.{table_name}":
                        return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError(f"Required table not found after migration: {table_name}")


def run_migrations() -> None:
    db_url = get_db_url()
    run_queue_migration(db_url)
    wait_for_table(db_url, "backtest_jobs")
    wait_for_table(db_url, "job_events")


if __name__ == "__main__":
    run_migrations()
