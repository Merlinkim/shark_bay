import os
import time

import psycopg

from app.backtest_jobs import BacktestJobRepository, execute_job


def wait_for_queue_tables(db_url: str, poll_seconds: float) -> None:
    while True:
        try:
            with psycopg.connect(db_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT to_regclass('public.backtest_jobs') IS NOT NULL
                           AND to_regclass('public.job_events') IS NOT NULL
                        """
                    )
                    row = cur.fetchone()
                    if row and row[0]:
                        return
        except Exception:
            pass
        time.sleep(poll_seconds)


def run_worker() -> None:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set")
    poll_seconds = float(os.environ.get("BACKTEST_JOB_POLL_SECONDS", "1.0"))
    wait_for_queue_tables(db_url, poll_seconds)
    repo = BacktestJobRepository(db_url)

    while True:
        job = repo.claim_next_job()
        if job is None:
            time.sleep(poll_seconds)
            continue

        job_id = job["id"]
        try:
            if repo.is_cancel_requested(job_id):
                repo.mark_cancelled(job_id)
                continue
            result, result_ref = execute_job(db_url, job)
            if repo.is_cancel_requested(job_id):
                repo.mark_cancelled(job_id)
            else:
                repo.mark_success(job_id, result=result, result_ref=result_ref)
        except Exception as exc:
            if repo.is_cancel_requested(job_id):
                repo.mark_cancelled(job_id)
            else:
                repo.mark_failed(job_id, str(exc))


if __name__ == "__main__":
    run_worker()
