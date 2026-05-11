# Shark Bay — Architecture & Operations Guide

This repository runs a small market-data platform composed of:

- a **PostgreSQL** datastore
- an **ingestor** service that pulls 1-minute candle data and upserts it
- a **FastAPI** service for health/status/data endpoints
- **Prometheus** for metrics scraping
- **Grafana** for dashboards

---


## CI (GitHub Actions)

A lightweight CI workflow runs on every pull request and on pushes to `main` via `.github/workflows/ci.yml`.

What it checks:
- Python 3.11 environment setup
- Dependency install from `app/requirements.txt` and `dashboard/requirements.txt`
- Targeted fast tests only:
  - `tests/test_backtest.py`
  - `tests/test_data_quality.py`
  - `tests/test_import_binance_klines.py`
- Python compile checks:
  - `python -m py_compile app/*.py dashboard/app.py`
- `docker compose config` syntax validation when Docker Compose is available on the runner

Notes:
- CI does **not** require Binance network access, secrets, or starting full Docker services.
- `tests/test_api.py` / `tests/test_main.py` are intentionally not part of this v0.4.2 CI target set to keep runtime short and deterministic; they can still be run locally.
- `httpx` is installed in CI test dependencies to avoid FastAPI/TestClient dependency gaps in environments that run API tests.

## Docker Compose Architecture

`docker-compose.yml` defines eight services and three persistent volumes:

- `db` (PostgreSQL 16)
- `ingestor` (custom Python app image from `./app`)
- `api` (custom Python app image from `./app`)
- `research-ui` (Streamlit backtest research dashboard)
- `frontend` (React/Vite production build served by Nginx)
- `prometheus` (Prometheus v2.54.1)
- `grafana` (Grafana 11.2.2)
- `cadvisor` (container resource exporter)
- Volumes:
  - `pgdata` for Postgres data durability
  - `grafana-data` for Grafana state

### Runtime flow (high level)

1. `db` starts and must pass healthcheck (`pg_isready`).
2. `ingestor` and `api` both wait for healthy `db`.
3. `ingestor` initializes schema, fetches Binance klines, upserts into `candles_1m`, writes heartbeat, and exports metrics.
4. `api` exposes health/readiness, candle query, ingestion status, and `/metrics`.
5. `prometheus` scrapes:
   - `api:8000/metrics`
   - `ingestor:9100`
   - `cadvisor:8080/metrics`
6. `research-ui` serves a local, read-only dashboard that consumes existing FastAPI backtest endpoints only.
7. `frontend` serves the production React app on Nginx and proxies `/api/*` traffic to `api:8000` over the Compose network.
8. `grafana` reads Prometheus (and provisioned datasource config) to show operational dashboards, including container resource panels for `db`, `ingestor`, `api`, `prometheus`, and `grafana`.

---

## Service Descriptions

### 1) `db` — PostgreSQL

- Purpose: persistent storage for market candles and operational heartbeat/status tables.
- Uses credentials/environment from Compose:
  - `POSTGRES_USER=postgres`
  - `POSTGRES_PASSWORD=postgres`
  - `POSTGRES_DB=market_data`
- Healthcheck gate for downstream services.

### 2) `ingestor` — Candle collector/upserter

- Polls Binance REST klines endpoint (`/api/v3/klines`) on interval (`POLL_SECONDS`, default 10s).
- Parses candles and upserts into `candles_1m` (`ON CONFLICT` update path).
- Tracks collector heartbeat and placeholder missing-candle event logic.
- Exposes Prometheus metrics via `start_http_server` on `METRICS_PORT` (default `9100`).
- Handles SIGTERM/SIGINT for graceful stop.
- On startup, runs **safe forward gap recovery** for `BTCUSDT` `1m` only:
  - compares latest stored candle vs latest closed Binance 1m candle
  - fetches only missing forward range with REST klines
  - upserts recovered candles using `symbol + open_time` key (idempotent)
  - bounded by `BACKFILL_MAX_CANDLES_PER_RUN`

#### Gap recovery safety controls

- `ENABLE_GAP_BACKFILL=true` (default)
- `BACKFILL_MAX_CANDLES_PER_RUN=500` (default)
- `REST_BACKFILL_SLEEP_SECONDS=0.2` (default)

### 3) `api` — FastAPI data + health + metrics

- Key endpoints:
  - `GET /health`
  - `GET /health/live`
  - `GET /health/ready` (includes DB check)
  - `GET /candles?symbol=BTCUSDT&interval=1m&limit=100`
  - `GET /ingestion/status`
  - `GET /metrics`
- Emits API request count and latency metrics from middleware.

### 4) `research-ui` — Streamlit backtest research dashboard

- Purpose: read-only explorer for persisted backtest runs and deterministic backtest outputs.
- Consumes **only** FastAPI endpoints:
  - `GET /backtests`
  - `GET /backtests/{run_id}`
  - `GET /backtests/{run_id}/fills`
  - `GET /backtests/{run_id}/equity-curve`
- Features:
  - recent run list with key run metadata and summary metrics
  - selectable run details
  - equity curve chart
  - fills/trades table
  - deterministic metadata cards/fields
  - loading/error states and optional auto-refresh
- No strategy execution, async workers, paper/live trading, or portfolio actions are implemented in this UI.

### 5) `frontend` — React/Vite production UI

- Built with a multi-stage Dockerfile (`node:20-alpine` build stage + `nginx:alpine` runtime stage).
- Runtime serves static `dist/` artifacts from Nginx on container port `80`.
- SPA-safe routing is enabled via `try_files ... /index.html` fallback.
- `/api/` is reverse-proxied to `http://api:8000/` (Compose service DNS), so browser traffic never needs container-localhost mappings.
- Build-time API base URL uses `VITE_API_BASE_URL` (Compose default: `/api`).

### 6) `prometheus` — Metrics scraper

- Scrape interval/evaluation interval: `10s`.
- Scrapes API, ingestor, and cAdvisor targets configured in `observability/prometheus/prometheus.yml`.

### 7) `cadvisor` — Container resource exporter

- Exposes CPU, memory, restart, network, and filesystem I/O metrics for running containers.
- Mounted read-only host paths allow cAdvisor to observe Docker runtime/container stats.
- Scraped by Prometheus at `cadvisor:8080`.

### 8) `grafana` — Visualization

- Starts with provisioned datasources/dashboards from `observability/grafana/provisioning/...`.
- Default login from Compose env:
  - username: `admin`
  - password: `admin`

---

## Ports

Host-mapped ports from Compose:

- `3000` → Grafana UI (`http://localhost:3000`)
- `5432` → PostgreSQL
- `8000` → API (`http://localhost:8000`)
- `5173` → Frontend UI (`http://localhost:5173`)
- `8501` → Backtest Research UI (`http://localhost:8501`)
- `9090` → Prometheus UI (`http://localhost:9090`)
- `8080` → cAdvisor UI/metrics (`http://localhost:8080`)
- `9100` → Ingestor metrics exporter (inside Compose network target is `ingestor:9100`; host mapping is not required for Prometheus scraping)

---

## Metrics

Implemented metrics (from `app/metrics.py`):

- `candle_insert_total` (Counter)
- `duplicate_candle_total` (Counter)
- `ingest_error_total` (Counter)
- `websocket_reconnect_total` (Counter)
- `rest_backfill_requested_total` (Counter)
- `rest_backfill_completed_total` (Counter)
- `rest_backfill_failed_total` (Counter)
- `rest_backfill_candles_inserted_total` (Counter)
- `latest_candle_timestamp` (Gauge)
- `invalid_ohlc_total` (Counter, cumulative validation events)
- `invalid_volume_total` (Counter, cumulative validation events)
- `future_timestamp_total` (Counter, cumulative validation events)
- `data_quality_invalid_ohlc_count` (Gauge, latest data quality check)
- `data_quality_invalid_volume_count` (Gauge, latest data quality check)
- `data_quality_future_timestamp_count` (Gauge, latest data quality check)
- `data_quality_gap_count` (Gauge, latest data quality check)
- `data_quality_duplicate_count` (Gauge, latest data quality check)
- `last_backfill_candle_count` (Gauge)
- `db_connection_status{service="..."}` (Gauge)
- `api_request_total{method,path,status_code}` (Counter)
- `api_request_latency_seconds{method,path}` (Histogram)

### Where metrics are exposed

- API metrics endpoint: `http://localhost:8000/metrics`
- Ingestor metrics endpoint (container): `http://ingestor:9100/` (scraped by Prometheus)

---

## Startup / Shutdown Commands

Use Make targets:

```bash
make up
```

- Runs: `docker compose up --build -d`

```bash
make down
```

- Runs: `docker compose down`

Useful log tails:

```bash
make logs-api
make logs-ingestor
```

---

## Verification Commands

After startup, verify each layer:

### Container/service status

```bash
docker compose ps
```

### API health/readiness/liveness

```bash
curl -sS http://localhost:8000/health
curl -sS http://localhost:8000/health/live
curl -sS http://localhost:8000/health/ready
```

### Query candles

```bash
curl -sS "http://localhost:8000/candles?symbol=BTCUSDT&interval=1m&limit=5"
```


### Backtest research UI

```bash
open http://localhost:8501
```

The Streamlit dashboard is read-only and uses FastAPI backtest endpoints only.

### Frontend production UI

```bash
curl -I http://localhost:5173
```

```bash
curl -sS http://localhost:5173/api/health
```

```bash
docker compose logs frontend --tail=100
```

- Open `http://localhost:5173` and verify operations/infrastructure pages and charts load.
- API calls should flow through Nginx proxy (`/api/*`) to `api:8000` with no browser CORS errors.

### Backtest result APIs (read-only)

```bash
curl -sS "http://localhost:8000/backtests"
```

```bash
curl -sS "http://localhost:8000/backtests/<run_id>"
```

```bash
curl -sS "http://localhost:8000/backtests/<run_id>/fills"
```

```bash
curl -sS "http://localhost:8000/backtests/<run_id>/equity-curve"
```


### Data quality validation (read-only)

Run the candle quality validator for a recent window:

```bash
python -m app.data_quality --symbol BTCUSDT --interval 1m --lookback-hours 24
```

Expected JSON output fields:

- `total_rows_checked`
- `gap_count`
- `duplicate_count`
- `invalid_ohlc_count`
- `invalid_volume_count`
- `future_timestamp_count`
- `latest_candle_timestamp`
- `data_lag_seconds`

### Ingestion status

```bash
curl -sS http://localhost:8000/ingestion/status
curl -sS http://localhost:8000/ops/health
curl -sS http://localhost:8000/ops/infrastructure
```

Includes:
- `last_backfill_status`
- `last_backfill_candle_count`
- `last_backfill_time`

### Metrics checks

```bash
curl -sS http://localhost:8000/metrics | head
curl -sS http://localhost:8080/metrics | head
curl -sS http://localhost:9090/api/v1/targets
```

### cAdvisor target verification (Prometheus UI)

1. Open `http://localhost:9090/targets`.
2. Verify the `cadvisor` target is **UP**.
3. In the Prometheus expression browser, run:
   - `container_memory_usage_bytes`
   - `rate(container_cpu_usage_seconds_total[1m])`

Optional CLI check:

```bash
curl -sS http://localhost:9090/api/v1/targets | rg cadvisor
```

In Grafana (`http://localhost:3000`), open **Shark Bay Operational Monitoring** and confirm these panels show series for `db`, `ingestor`, `api`, `prometheus`, and `grafana`:

- Container CPU usage (cores)
- Container memory usage (bytes)
- Container restart count
- Container network RX/TX (bytes/s)
- Container disk I/O (bytes/s)

### Prometheus / Grafana web UIs

- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000`

---

## Troubleshooting

### 1) API readiness fails (`/health/ready` returns 503)

Checks:

```bash
docker compose ps
docker compose logs --tail=200 db
docker compose logs --tail=200 api
```

Likely causes:

- DB not healthy yet
- wrong `DATABASE_URL`
- transient DB startup timing

### 2) No fresh candles in `/ingestion/status`

Checks:

```bash
docker compose logs --tail=200 ingestor
curl -sS http://localhost:8000/ingestion/status
curl -sS http://localhost:8000/ops/health
curl -sS http://localhost:8000/ops/infrastructure
```

Likely causes:

- network reachability to Binance endpoint
- DB write errors
- ingestor crash/restart loop

### 3) Prometheus target is down

Checks:

```bash
curl -sS http://localhost:9090/api/v1/targets
docker compose logs --tail=200 prometheus
docker compose logs --tail=200 api
docker compose logs --tail=200 ingestor
```

Likely causes:

- scrape target unavailable
- incorrect metrics path/port
- service not running in Compose network

### 4) Grafana has no data

Checks:

```bash
docker compose logs --tail=200 grafana
curl -sS http://localhost:9090/api/v1/query?query=up
```

Likely causes:

- Prometheus datasource provisioning issue
- Prometheus not scraping targets
- dashboard variables/time-range mismatch

### 5) Need a clean reset

```bash
make down
docker volume rm shark_bay_pgdata shark_bay_grafana-data  # optional destructive reset
make up
```

> Only remove volumes if you intentionally want to delete persisted DB and Grafana state.

## Reproducible Backtests

Run the backtest CLI with a fixed dataset window to freeze the candle set used in replay:

```bash
python -m app.backtest \
  --symbol BTCUSDT \
  --interval 1m \
  --short-window 5 \
  --long-window 20 \
  --start-time 2026-05-01T00:00:00+00:00 \
  --end-time 2026-05-01T12:00:00+00:00
```

You can optionally combine a fixed window with `--limit`.

Each run now writes dataset metadata to `summary.json` and terminal output:

- `dataset_fingerprint`
- `dataset_row_count`
- `dataset_min_open_time`
- `dataset_max_open_time`

### Verify two runs are identical for the same window

```bash
python -m app.backtest --symbol BTCUSDT --interval 1m --start-time 2026-05-01T00:00:00+00:00 --end-time 2026-05-01T12:00:00+00:00
python -m app.backtest --symbol BTCUSDT --interval 1m --start-time 2026-05-01T00:00:00+00:00 --end-time 2026-05-01T12:00:00+00:00
```

Compare the output summaries:

```bash
jq '.config_hash, .dataset_fingerprint, .total_return_pct, .final_equity' <run1>/summary.json
jq '.config_hash, .dataset_fingerprint, .total_return_pct, .final_equity' <run2>/summary.json
```

For matching windows and strategy settings, `config_hash` and `dataset_fingerprint` should match, and deterministic metrics should be identical.

---

## Strategy Plugin + Indicator Layer

Strategies are now plugin-like classes discovered through the strategy registry in `app/backtest.py`.

### Create a new strategy

1. Add a strategy class with required metadata:
   - `strategy_name`
   - `description`
   - `parameter_schema`
   - `default_parameters`
2. Implement `on_candle(self, candle) -> int` and keep logic deterministic and side-effect free.
3. Reuse indicators from `IndicatorLibrary` (`sma`, `ema`, `rsi`, `atr`, `bollinger_bands`) instead of duplicating math.

### Register a strategy

Register with the global registry:

```python
strategy_registry.register(MyNewStrategy)
```

### Expose parameters to UI/API

- The API `/strategies` endpoint returns strategy metadata from the registry.
- The Streamlit UI auto-builds strategy parameter controls from `parameter_schema` + `default_parameters`.
- The API `/backtests/run` validates both `strategy_name` and `strategy_params` using the strategy registry before execution.

### Example strategy template

```python
class MyNewStrategy:
    strategy_name = "my_new_strategy"
    description = "Describe strategy behavior"
    parameter_schema = {
        "lookback": {"type": "int", "min": 2, "max": 200},
    }
    default_parameters = {"lookback": 20}

    def __init__(self, lookback: int = 20):
        self.lookback = lookback

    def on_candle(self, candle: Candle) -> int:
        return 0
```

## Historical Data Import (v0.2.3)

Use the Binance historical importer to load Binance Vision kline files into PostgreSQL using duplicate-safe upserts.

Example Binance Vision path pattern:

```text
https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1m/
```

Example imports:

```bash
python -m app.import_binance_klines --file ./BTCUSDT-1m-2026-04.zip --symbol BTCUSDT --interval 1m
python -m app.import_binance_klines --file ./BTCUSDT-1m-2026-04.csv --symbol BTCUSDT --interval 1m --max-rows 10000
python -m app.import_binance_klines --file ./BTCUSDT-1m-2026-04.zip --symbol BTCUSDT --interval 1m --dry-run
```

### Historical Import Layer v0

For deterministic long-range research/backtesting, use the monthly Binance Vision importer to pull historical spot klines (initial target: BTCUSDT 1m, up to 80 months where available).

Source pattern:

`https://data.binance.vision/data/spot/monthly/klines/{symbol}/{interval}/{symbol}-{interval}-{YYYY-MM}.zip`

Examples:

```bash
python -m app.historical_import --symbol BTCUSDT --interval 1m --months 80
python -m app.historical_import --symbol BTCUSDT --interval 1m --start-month 2020-01 --end-month 2026-04
python -m app.historical_import --symbol BTCUSDT --interval 1m --months 80 --dry-run
python -m app.historical_import --symbol BTCUSDT --interval 1m --months 80 --skip-existing --sleep-seconds 0.2
```

Notes:
- Binance monthly availability varies by symbol/month; missing files are skipped and reported.
- Large imports can take significant time, network bandwidth, and disk space.
- Import is idempotent through duplicate-safe upsert behavior in `candles_1m`.

### REST Historical Backfill Layer v0

Use REST backfill for **partial/current-month** gaps that are not yet available in Binance Vision monthly files.

- Monthly importer (`app.historical_import`) is best for long-range closed months.
- REST backfill (`app.rest_backfill`) is best for recent windows like `2026-05-01` to `2026-05-11`.

Examples:

```bash
python -m app.rest_backfill --symbol BTCUSDT --interval 1m --start "2026-05-01T00:00:00Z" --end "2026-05-11T00:00:00Z"
python -m app.rest_backfill --symbol BTCUSDT --interval 1m --start "2026-05-01T00:00:00Z" --end "2026-05-02T00:00:00Z" --dry-run
python -m app.rest_backfill --symbol BTCUSDT --interval 1m --start "2026-05-01T00:00:00Z" --end "2026-05-11T00:00:00Z" --skip-existing --sleep-seconds 0.2 --limit 1000
```

Optional maintenance endpoint:

- `POST /research/backfill/rest`
- Admin-style/read-only control plane endpoint; no trading behavior.

Rate limit warning:

- Binance REST enforces request limits. Prefer `--sleep-seconds` pacing for larger windows and avoid running many concurrent jobs.

DB verification query:

```bash
docker compose exec -T db psql -U postgres -d market_data -c "SELECT symbol, MIN(open_time) AS first_open_time, MAX(open_time) AS last_open_time, COUNT(*) AS rows FROM candles_1m WHERE symbol='BTCUSDT' GROUP BY symbol;"
```


### Grafana data quality dashboard verification (v0.2.4)

1. Open Grafana (`http://localhost:3000`) and load **Shark Bay Operational Monitoring**.
2. Validate dashboard sections:
   - **Ingestion Health**
   - **Data Quality**
   - **Backfill Recovery**
3. Check status colors and expected ranges:
   - green = healthy, yellow = warning, red = critical
   - `Data lag seconds`: green < 90, yellow >= 90, red >= 180
   - `Recent gap count`: green = 0, yellow >= 1, red >= 5
   - `Invalid OHLC/volume/future timestamp` (1h): green = 0, yellow >= 1, red threshold panel-specific
   - `Backfill failed count` (1h): green = 0, yellow >= 1, red >= 3
4. Example failure indicators:
   - sustained red on `Data lag seconds` with rising `ingest_error_total`
   - non-zero `Future timestamp count (1h)`
   - repeated `Websocket reconnect count (1h)` spikes plus failed backfills

---

## v0.4.1 Deployment Readiness

### Environment configuration

1. Copy env template:

```bash
cp .env.example .env
```

2. Review and set environment values before deployment.
3. Never commit real secrets.

### Persistent volumes

- `pgdata` → PostgreSQL data (`/var/lib/postgresql/data`)
- `grafana-data` → Grafana state (`/var/lib/grafana`)
- `prometheus-data` → Prometheus TSDB (`/prometheus`)

### PostgreSQL backup and restore

Backup:

```bash
docker compose exec -T db pg_dump -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-market_data}" > backup_market_data.sql
```

Restore (to a running DB):

```bash
cat backup_market_data.sql | docker compose exec -T db psql -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-market_data}"
```

## Deployment checklist (safe VPS rollout)

- [ ] Pull latest code on VPS and verify target branch/tag.
- [ ] Create/update `.env` from `.env.example`.
- [ ] Verify required ports are available (3000/5432/8000/8501/9090/8080).
- [ ] Build and start: `docker compose up --build -d`.
- [ ] Verify health endpoints and ingestion status.
- [ ] Reboot verification: run `docker compose ps` and confirm `db` is `Up`/healthy.
- [ ] Reboot verification: run `curl -sS http://localhost:8000/health`.
- [ ] Reboot verification: run `curl -sS http://localhost:8000/ingestion/status`.
- [ ] Reboot verification: run `python -m app.data_quality --symbol BTCUSDT --interval 1m --lookback-hours 2`.
- [ ] Verify Prometheus targets are UP.
- [ ] Verify Grafana dashboard has data.
- [ ] Capture `docker compose ps` and recent logs for deployment record.

## Rollback checklist

- [ ] Keep previous image/code revision available.
- [ ] Stop new stack safely: `docker compose down`.
- [ ] Checkout previous known-good revision.
- [ ] Start previous revision: `docker compose up --build -d`.
- [ ] Validate `/health`, `/ingestion/status`, and Grafana/Prometheus.
- [ ] If schema drift suspected, restore from latest verified DB backup.

## Health verification commands

```bash
docker compose ps
curl -sS http://localhost:8000/health
curl -sS http://localhost:8000/health/live
curl -sS http://localhost:8000/health/ready
curl -sS http://localhost:8000/ingestion/status
python -m app.data_quality --symbol BTCUSDT --interval 1m --lookback-hours 2
curl -sS http://localhost:8000/ops/health
curl -sS http://localhost:8000/ops/infrastructure
curl -sS http://localhost:9090/api/v1/targets
```

For detailed failure triage and copy-paste debugging commands, see `docs/agent_debugging.md`.


### Local React dev CORS

For local Vite React development (`http://localhost:5173`), the API now supports configurable CORS origins using `CORS_ALLOW_ORIGINS`.

Default local-safe value:

```bash
CORS_ALLOW_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Notes:
- No wildcard (`*`) origin is enabled by default.
- Production should set `CORS_ALLOW_ORIGINS` explicitly to trusted origins only.


## Research Layer v0 (read-only feature telemetry)

CLI snapshot from `candles_1m`:

```bash
python -m app.features --symbol BTCUSDT --interval 1m --lookback-hours 24
```

API endpoint:

```bash
curl "http://localhost:8000/research/features?symbol=BTCUSDT&interval=1m&lookback_hours=24"
```

This research telemetry surface is deterministic and read-only. It computes feature engineering outputs only (no execution, paper trading, or order controls).

## Strategy Registry v0 (Deterministic Metadata Layer)

A read-only strategy metadata registry is available for connecting research features to upcoming backtest and paper-trading workflows, without enabling execution.

- Module: `app/strategy_registry.py`
- CLI: `python -m app.strategy_registry`
- API: `GET /strategies/registry`

Example:

```bash
curl "http://localhost:8000/strategies/registry?status=research_ready&symbol=BTCUSDT&interval=1m"
```

This layer is deterministic and metadata-only (no live trading, paper trading, or order execution).

## Backtest Experiment Layer v0 / Research Memory Layer v0

Read-only deterministic experiment runs are available for research workflows.

### CLI

```bash
python -m app.experiments --strategy ema_cross_v1 --symbol BTCUSDT --interval 1m --lookback-hours 24

# Persist deterministic experiment metadata/results into research_experiments
python -m app.experiments --strategy ema_cross_v1 --symbol BTCUSDT --interval 1m --lookback-hours 24 --persist
```

### API

- `GET /research/experiments/latest?symbol=BTCUSDT&interval=1m&limit=20`
- `GET /research/experiments/{experiment_id}`
- `POST /research/experiments/run?strategy=ema_cross_v1&symbol=BTCUSDT&interval=1m&lookback_hours=24&persist=true`

Schema purpose:
- `research_experiments` stores deterministic research experiment metadata/results only.
- Storage is analytical/read-only memory for historical comparison.
- Idempotent upsert is keyed by `experiment_id`.
- No live trading, no paper trading, no order execution.

Notes:
- v0 experiments are deterministic and read-only.
- v0 uses simulated placeholder backtest logic where full execution is not implemented.
- Research memory is read-only analytical storage, not trading execution.

## Research Analytics Layer v0

Read-only analytics are available over persisted deterministic/simulated `research_experiments` records.
No live trading, paper trading, order execution, or agent execution is performed by this layer.

### API endpoint

```bash
curl "http://localhost:8000/research/analytics?symbol=BTCUSDT&interval=1m&limit=100"
```

Response shape includes:
- `summary`
- `strategy_leaderboard`
- `regime_breakdown`
- `recent_rankings`
- `generated_at`

### CLI usage

```bash
python -m app.research_analytics --symbol BTCUSDT --interval 1m --limit 100
```

This prints analytics JSON computed from persisted research memory only.
