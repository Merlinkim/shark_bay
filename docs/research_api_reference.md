# Shark Bay Research API Reference

## Conventions
- Base: FastAPI service (default `:8000`).
- Timestamps: ISO-8601 UTC (`...Z` or `+00:00`), datetime query params must include timezone where required.
- Errors: `{"detail": "..."}` with HTTP status (`400`, `404`, `500`, `503`).
- Pagination: `limit` appears on list endpoints; no cursor pagination yet.
- Sorting: usually fixed server-side (`open_time DESC` for candles, `created_at DESC` for experiment lists).
- Filtering: query params (`symbol`, `interval`, `status`, date ranges, split settings).

## Ingestion
### GET `/ingestion/status`
- Purpose: latest ingestion heartbeat and candle counts.
- Response: latest/last candle time, total count, collector status, backfill status fields, heartbeat payload.
- Determinism: snapshot at query time from DB state.
- Intended agents: Arthur (ops), Merlin (diagnostics).

### GET `/ingestion/telemetry`
- Purpose: per-symbol lag/reconnect/upsert visibility.
- Params: none (uses configured symbols).
- Response: `{symbols, symbol_metrics}`.
- Determinism: consistent for same DB snapshot.
- Intended agents: Arthur, Lancelot.

### POST `/research/backfill/rest`
- Purpose: controlled historical REST backfill.
- Body: `symbol, interval=1m, start, end, dry_run, sleep_seconds, limit, skip_existing`.
- Response: backfill summary with requested/fetched/upserted counts + errors.
- Determinism: deterministic for fixed source data and window; external exchange history may evolve in near-real-time for unfinished candles.
- Intended agents: Arthur (data hygiene), Galahad (dataset prep).

## Candles
### GET `/candles`
- Params: `symbol` (required), `interval=1m`, `limit<=20000`.
- Response: `{symbol, interval, limit, count, candles[]}`.
- Determinism: fixed ordering (`open_time DESC`) and DB snapshot semantics.
- Workflow: data sanity pull, feature pre-check.

### GET `/symbols/active`
- Purpose: discover active symbols in DB.
- Response: `{symbols, count}`.

## Backtesting
### GET `/backtests`
- Params: `limit<=500`.
- Response: list of run summaries.

### GET `/backtests/{run_id}`
### GET `/backtests/{run_id}/fills`
### GET `/backtests/{run_id}/equity-curve`
- Purpose: inspect persisted run details + artifacts.
- Determinism: immutable run data once persisted.

### POST `/backtests/run`
- Body: `strategy_name, strategy_params, symbol, interval=1m, start_time?, end_time?, save_results`.
- Response: `run_id`, hashes, summary metrics.
- Determinism: deterministic for identical candle dataset and strategy params.
- Intended agents: Merlin, Galahad.

## Walk-Forward
### GET `/research/walk-forward/run`
- Params: strategy, symbol, interval, start/end, train/validation/test days, step_days, include_holdout, persist.
- Response: window metrics + aggregate stability/degradation/pass-fail.
- Determinism: deterministic window generation and segment replay over fixed dataset.
- Intended agents: Galahad, Merlin.

## Experiments
### GET `/research/experiments/run`
- Params include `strategy, symbol, interval, lookback_hours, start/end, persist, split_mode, include_holdout`.
- Response: experiment payload (with optional holdout metrics).

### GET `/research/experiments/latest`
- Params: `symbol, interval, limit<=200`.
- Response: `{experiments: [...]}` sorted newest first.

### GET `/research/experiments/{experiment_id}`
### GET `/research/experiments/{experiment_id}/equity-curve`
### GET `/research/experiments/{experiment_id}/fills`
- Purpose: retrieve full experiment and artifact slices.

## Analytics
### GET `/research/features`
- Params: `symbol, interval=1m, lookback_hours`.
- Response: feature snapshot with regime + notes.

### GET `/research/analytics`
- Params: `symbol, interval=1m, limit<=500`.
- Response: aggregate analytics over recent experiments.

### GET `/research/dataset/splits`
- Params: symbol, interval, split_mode (`ratio|rolling`), include_holdout, start/end, and window day params.
- Response: deterministic split/window payload.

## Research-Agent
### GET `/research/agent/recommendations`
- Params: symbol, interval, optional strategy/start/end.
- Purpose: recommendation bundle for research agent workflows.
- Intended agents: Merlin primarily.

## Strategy-Registry
### GET `/strategies`
- Purpose: runtime strategy metadata view.

### GET `/strategies/registry`
- Params: optional `status`, `symbol`, `interval`.
- Purpose: registry-contract filtering for research planning.

## Telemetry / Health
### GET `/health`, `/health/live`, `/health/ready`
### GET `/ops/health`, `/ops/infrastructure`
### GET `/metrics`
- Support debugging/observability and readiness automation.
