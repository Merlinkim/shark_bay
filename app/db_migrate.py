from __future__ import annotations

import os
import time
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


def get_db_url() -> str:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set")
    return db_url


def apply_schema(db_url: str) -> None:
    schema_path = Path(__file__).with_name("schema.sql")
    ddl = schema_path.read_text(encoding="utf-8")
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(ddl)
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
    apply_schema(db_url)
    wait_for_table(db_url, "backtest_jobs")
    wait_for_table(db_url, "job_events")


if __name__ == "__main__":
    run_migrations()
