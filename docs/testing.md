# Testing and Verification Guide

This guide summarizes the currently available runtime checks and test commands for Shark Bay.

> Scope: operational verification commands for Docker services and API endpoints, plus Python test commands that currently exist in this repository.

## 1) Container status check

- **Purpose**: confirm all expected services are up (or identify restart/crash loops quickly).
- **Command**:
  ```bash
  docker compose ps
  ```
- **Expected result**: `db`, `ingestor`, `api`, `research-ui`, `prometheus`, `grafana`, and `cadvisor` appear with `Up` state (health status should be healthy where defined).
- **Failure usually means**: one or more services failed to start, are repeatedly restarting, or are blocked by dependency/healthcheck failures.

## 2) API health check

- **Purpose**: verify API process is reachable and readiness dependencies are satisfied.
- **Command**:
  ```bash
  curl -sS http://localhost:8000/health
  curl -sS http://localhost:8000/health/live
  curl -sS http://localhost:8000/health/ready
  ```
- **Expected result**: JSON responses indicating healthy/liveness OK; readiness should return success when DB connectivity is available.
- **Failure usually means**: API container is down, startup is incomplete, or DB connectivity/readiness dependency failed.

## 3) Ingestion status check

- **Purpose**: confirm ingestor heartbeat and freshness of ingestion pipeline.
- **Command**:
  ```bash
  curl -sS http://localhost:8000/ingestion/status
  ```
- **Expected result**: structured JSON status with recent heartbeat/updated timestamps and no persistent error indications.
- **Failure usually means**: ingestor is stalled/crashed, cannot fetch source data, or cannot write to PostgreSQL.

## 4) Candle count query

- **Purpose**: validate candles are actually persisted in PostgreSQL.
- **Command**:
  ```bash
  docker compose exec -T db psql -U postgres -d market_data -c "SELECT symbol, interval, COUNT(*) AS candle_count FROM candles_1m GROUP BY symbol, interval ORDER BY symbol, interval;"
  ```
- **Expected result**: one or more rows with non-zero `candle_count` for expected symbols/intervals.
- **Failure usually means**: ingestion not writing data, schema initialization failed, or querying the wrong database/table.

## 5) Gap detection query

- **Purpose**: detect missing 1-minute intervals in stored candle series.
- **Command**:
  ```bash
  docker compose exec -T db psql -U postgres -d market_data -c "WITH ordered AS (SELECT symbol, interval, open_time, LAG(open_time) OVER (PARTITION BY symbol, interval ORDER BY open_time) AS prev_open_time FROM candles_1m) SELECT symbol, interval, prev_open_time, open_time, (EXTRACT(EPOCH FROM (open_time - prev_open_time))/60)::int AS gap_minutes FROM ordered WHERE prev_open_time IS NOT NULL AND open_time - prev_open_time > INTERVAL '1 minute' ORDER BY open_time DESC LIMIT 50;"
  ```
- **Expected result**: ideally zero rows (or known/acceptable rare gaps only).
- **Failure usually means**: ingestion interruptions, source downtime, clock drift, or unfilled historical holes.

## 6) Backfill verification

- **Purpose**: ensure historical data exists over a target window and not only the latest few candles.
- **Command**:
  ```bash
  docker compose exec -T db psql -U postgres -d market_data -c "SELECT symbol, interval, MIN(open_time) AS first_candle, MAX(open_time) AS latest_candle, COUNT(*) AS total_rows FROM candles_1m GROUP BY symbol, interval ORDER BY symbol, interval;"
  ```
- **Expected result**: `first_candle` is sufficiently old for your intended analysis window and `total_rows` is consistent with elapsed time.
- **Failure usually means**: backfill did not run, ingest began recently, or retention/reset removed older rows.

## 7) Prometheus targets check

- **Purpose**: verify scrape status for observability targets.
- **Command**:
  ```bash
  curl -sS http://localhost:9090/api/v1/targets
  ```
- **Expected result**: `api`, `ingestor`, and `cadvisor` targets listed as `up` in active targets.
- **Failure usually means**: target endpoint unreachable, wrong metrics path/port, DNS/network issue inside Docker Compose, or service not running.

## 8) Grafana check

- **Purpose**: validate dashboard stack is reachable and connected to Prometheus data.
- **Command**:
  ```bash
  open http://localhost:3000
  ```
  (Linux alternative: `xdg-open http://localhost:3000` or open in your browser manually.)
- **Expected result**: Grafana login page loads (default `admin` / `admin` unless changed), and the Shark Bay dashboard panels render with data.
- **Failure usually means**: Grafana container not running, provisioning/datasource issue, or Prometheus itself has no valid data.

## 9) Streamlit research UI check

- **Purpose**: verify read-only backtest research interface is reachable and can query FastAPI backtest endpoints.
- **Command**:
  ```bash
  open http://localhost:8501
  ```
  (Linux alternative: `xdg-open http://localhost:8501`.)
- **Expected result**: Streamlit app loads, recent runs list appears (or clean empty state), and selecting a run shows details/equity/fills.
- **Failure usually means**: `research-ui` container unavailable, API endpoint errors, or no accessible backtest records.

## 10) backtest CLI fixed-window reproducibility test

- **Purpose**: confirm deterministic replay for identical input window and settings (`dataset fingerprint` and `config hash` consistency).
- **Command**:
  ```bash
  python -m app.backtest --symbol BTCUSDT --interval 1m --start-time 2026-05-01T00:00:00+00:00 --end-time 2026-05-01T12:00:00+00:00
  python -m app.backtest --symbol BTCUSDT --interval 1m --start-time 2026-05-01T00:00:00+00:00 --end-time 2026-05-01T12:00:00+00:00
  jq '.config_hash, .dataset_fingerprint, .total_return_pct, .final_equity' <run1>/summary.json
  jq '.config_hash, .dataset_fingerprint, .total_return_pct, .final_equity' <run2>/summary.json
  ```
- **Expected result**: matching `config hash`, matching `dataset fingerprint`, and identical deterministic summary metrics between both runs.
- **Failure usually means**: input window mismatch, changed parameters/strategy defaults, non-deterministic logic, or querying different run folders.

## 11) backtest DB persistence verification

- **Purpose**: verify backtest runs are persisted and queryable through API and/or DB.
- **Command**:
  ```bash
  curl -sS http://localhost:8000/backtests
  curl -sS "http://localhost:8000/backtests/<run_id>"
  curl -sS "http://localhost:8000/backtests/<run_id>/fills"
  curl -sS "http://localhost:8000/backtests/<run_id>/equity-curve"
  ```
- **Expected result**: list endpoint returns runs, and detail/fills/equity endpoints return corresponding records for valid `<run_id>`.
- **Failure usually means**: no runs persisted yet, wrong run id, API/DB schema mismatch, or storage write failures during backtest execution.

## 12) strategy registry check

- **Purpose**: verify strategy registry wiring and API exposure of discoverable strategies.
- **Command**:
  ```bash
  curl -sS http://localhost:8000/strategies
  ```
- **Expected result**: JSON list/object containing registered strategy metadata (`strategy_name`, schemas/default parameters, etc.).
- **Failure usually means**: registry registration issue, API route failure, import/runtime error, or incompatible strategy metadata.

## 13) pytest commands that currently work

- **Purpose**: execute unit/integration test modules present in this repository.
- **Command**:
  ```bash
  pytest -q
  pytest tests/test_main.py -q
  pytest tests/test_api.py -q
  pytest tests/test_backtest.py -q
  ```
- **Expected result**: tests pass without failures in a correctly prepared Python environment.
- **Failure usually means**: missing dependencies, environment mismatch, changed behavior vs. tests, or required services not running for integration-style assertions.

---


## 14) data quality validation CLI

- **Purpose**: run read-only candle data quality checks over a lookback window before expanding historical coverage or deploying.
- **Command**:
  ```bash
  python -m app.data_quality --symbol BTCUSDT --interval 1m --lookback-hours 24
  ```
- **Expected result**: JSON report including `total_rows_checked`, `gap_count`, `duplicate_count`, `invalid_ohlc_count`, `invalid_volume_count`, `future_timestamp_count`, `latest_candle_timestamp`, and `data_lag_seconds`.
- **Failure usually means**: database connectivity issues, empty/recently reset datasets, or candle integrity problems requiring remediation before rollout.

## 15) forward gap recovery (v0.2.2) verification

- **Purpose**: validate startup-time safe forward backfill after ingestor downtime/restart.
- **Commands**:
  ```bash
  # baseline quality snapshot
  python -m app.data_quality --symbol BTCUSDT --interval 1m --lookback-hours 6

  # stop ingestor and wait to create a recent forward gap
  docker compose stop ingestor
  sleep 240

  # restart ingestor
  docker compose start ingestor

  # inspect startup logs for backfill lifecycle events
  docker compose logs --since=10m ingestor | rg "gap_detected|backfill_started|candles_fetched|candles_inserted|backfill_completed|backfill_failed"

  # verify ingestion status includes backfill fields
  curl -sS http://localhost:8000/ingestion/status

  # quality check after recovery
  python -m app.data_quality --symbol BTCUSDT --interval 1m --lookback-hours 6
  ```
- **Expected result**:
  - logs show backfill events in order (`gap_detected` → `backfill_started` → ... → `backfill_completed`)
  - `/ingestion/status` returns `last_backfill_status`, `last_backfill_candle_count`, `last_backfill_time`
  - recent `gap_count` from data quality should decrease vs pre-restart snapshot

## Notes

- Prefer running `make up` before operational checks and `make logs-api` / `make logs-ingestor` for debugging.
- For destructive resets, use `make down` and remove volumes only when data loss is acceptable.

## 16) historical Binance Vision import CLI (v0.2.3)

- **Purpose**: validate offline historical kline ingestion from Binance Vision `.csv` / `.zip` files.
- **Commands**:
  ```bash
  python -m app.import_binance_klines --file ./BTCUSDT-1m-2026-04.zip --symbol BTCUSDT --interval 1m --dry-run
  python -m app.import_binance_klines --file ./BTCUSDT-1m-2026-04.zip --symbol BTCUSDT --interval 1m
  python -m app.import_binance_klines --file ./BTCUSDT-1m-2026-04.csv --symbol BTCUSDT --interval 1m --max-rows 50000
  ```
- **Expected result**:
  - logs include `import_start`, `validation_summary`, `import_end`
  - summary includes `rows_read`, `rows_inserted`, `duplicates_skipped_or_upserted`, `invalid_rows_skipped`, `min_open_time`, `max_open_time`
  - re-running same file remains idempotent through upsert conflict handling
- **DB verification**:
  ```bash
  docker compose exec -T db psql -U postgres -d market_data -c "SELECT symbol, MIN(open_time), MAX(open_time), COUNT(*) FROM candles_1m WHERE symbol='BTCUSDT' GROUP BY symbol;"
  ```
