# Shark Bay Research API Reference (Updated)

This reference is aligned with `app/api.py` as of 2026-05-28.

## Conventions

- Base service: FastAPI (default `http://localhost:8000`).
- Time format: ISO-8601 with timezone.
- Errors: `{"detail": "..."}` with `400`, `404`, `500`, `503`.
- Determinism: reproducible when symbol/range/params and underlying dataset are fixed.

## Health and Ops

- `GET /health`
- `GET /health/live`
- `GET /health/ready`
- `GET /ops/health`
- `GET /ops/infrastructure`
- `GET /metrics`

Use this group as preflight before any research workflow.

## Market Data and Ingestion

- `GET /symbols/active`
- `GET /candles?symbol=...&interval=1m&limit=...`
- `GET /ingestion/status`
- `GET /ingestion/telemetry`
- `POST /research/backfill/rest`

`/research/backfill/rest` is for bounded historical gap recovery. Prefer explicit `start/end`, keep window narrow, and use `dry_run` first when uncertain.

## Strategy Metadata

- `GET /strategies`
- `GET /strategies/registry`

Use this to validate strategy availability and registry contract before runs.

## Backtests (Direct)

- `GET /backtests`
- `GET /backtests/{run_id}`
- `GET /backtests/{run_id}/fills`
- `GET /backtests/{run_id}/equity-curve`
- `POST /backtests/run`

`POST /backtests/run` supports deterministic replay and persists artifacts when `save_results=true`.

## Backtest Job Queue (Async)

- `POST /research/jobs/backtest`
- `GET /research/jobs/{job_id}`
- `GET /research/jobs/{job_id}/result`
- `POST /research/jobs/{job_id}/cancel`

Use async jobs for heavier runs or when orchestration needs polling/cancellation semantics.

## Research and Analytics

- `GET /research/features`
- `GET /research/experiments/run`
- `GET /research/experiments/latest`
- `GET /research/experiments/{experiment_id}`
- `GET /research/experiments/{experiment_id}/equity-curve`
- `GET /research/experiments/{experiment_id}/fills`
- `GET /research/analytics`
- `GET /research/dataset/splits`
- `GET /research/walk-forward/run`
- `GET /research/agent/recommendations`

Recommended sequence:
1. `/research/dataset/splits`
2. `/research/experiments/run`
3. `/research/analytics`
4. `/research/agent/recommendations`
5. `/research/walk-forward/run` for robustness checks

## Review and Strategy Lifecycle

- `POST /research/reviews`
- `GET /research/reviews`
- `GET /research/reviews/{review_id}`
- `POST /research/strategies/proposals`
- `GET /research/strategies/{strategy_id}`
- `PATCH /research/strategies/{strategy_id}/status`
- `GET /research/strategies/{strategy_id}/history`

Use this group to formalize decisions and keep an auditable research trail.

## Minimal Agent Runbook

1. Readiness: `/health/ready`, `/ingestion/status`.
2. Data verify: `/symbols/active`, `/candles`.
3. Research run: `/research/dataset/splits`, `/research/experiments/run`.
4. Decision support: `/research/analytics`, `/research/agent/recommendations`.
5. Governance: `/research/reviews`, strategy lifecycle endpoints.

## Related docs

- `docs/project_structure_graph.md`
- `docs/GUIDE_AGENTS.md`
- `docs/codebase_whitepaper.md`
