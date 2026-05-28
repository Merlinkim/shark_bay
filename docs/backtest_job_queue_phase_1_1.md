# Shark Bay Backend — Phase 1.1 Backtest Job Queue

## Architecture choices
- Kept the existing FastAPI + PostgreSQL architecture and introduced queue semantics via persistent DB rows in `backtest_jobs`.
- Used a simple polling worker process (`app.backtest_worker`) instead of adding external queue frameworks, keeping Docker Compose compatibility.
- Reused existing backtest execution components (`StrategyLoader` path via `build_strategy`, `CandleRepository`, `SimulatedExecutionModel`, `BacktestRunRepository`) rather than rewriting orchestration.

## What was added
- Persistent job model and status lifecycle: `queued`, `running`, `success`, `failed`, `cancelled`.
- Job API endpoints:
  - `POST /research/jobs/backtest`
  - `GET /research/jobs/{job_id}`
  - `GET /research/jobs/{job_id}/result`
  - `POST /research/jobs/{job_id}/cancel`
- Reproducibility metadata capture (`strategy_version`, config hash, execution/risk config, git commit hash when available).
- Worker flow that claims queued jobs with `FOR UPDATE SKIP LOCKED`, executes backtests off-request, and persists success/failure/cancel state.
- Event stream table (`job_events`) for status transition auditability.
- Additional validation in execution path for empty candle datasets.

## Remaining limitations
- Running job cancellation is cooperative (checked before and after execution) and does not hard-interrupt long-running Python computation mid-flight.
- No retry/backoff policy is implemented yet beyond stored `retry_count` field.
- Progress reporting is currently static (`progress: null`) until granular progress hooks are added to the simulation engine.
- Single worker model scales vertically; horizontal scaling is possible but not yet tuned (e.g., per-strategy prioritization, tenancy isolation).
