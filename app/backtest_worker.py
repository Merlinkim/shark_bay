import os
import time

from app.backtest_jobs import BacktestJobRepository, execute_job


def run_worker() -> None:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set")
    poll_seconds = float(os.environ.get("BACKTEST_JOB_POLL_SECONDS", "1.0"))
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
