# Shark Bay — Architecture & Operations Guide

This repository runs a small market-data platform composed of:

- a **PostgreSQL** datastore
- an **ingestor** service that pulls 1-minute candle data and upserts it
- a **FastAPI** service for health/status/data endpoints
- **Prometheus** for metrics scraping
- **Grafana** for dashboards

---

## Docker Compose Architecture

`docker-compose.yml` defines six services and two persistent volumes:

- `db` (PostgreSQL 16)
- `ingestor` (custom Python app image from `./app`)
- `api` (custom Python app image from `./app`)
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
6. `grafana` reads Prometheus (and provisioned datasource config) to show operational dashboards, including container resource panels for `db`, `ingestor`, `api`, `prometheus`, and `grafana`.

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

### 3) `api` — FastAPI data + health + metrics

- Key endpoints:
  - `GET /health`
  - `GET /health/live`
  - `GET /health/ready` (includes DB check)
  - `GET /candles?symbol=BTCUSDT&interval=1m&limit=100`
  - `GET /ingestion/status`
  - `GET /metrics`
- Emits API request count and latency metrics from middleware.

### 4) `prometheus` — Metrics scraper

- Scrape interval/evaluation interval: `10s`.
- Scrapes API, ingestor, and cAdvisor targets configured in `observability/prometheus/prometheus.yml`.

### 5) `cadvisor` — Container resource exporter

- Exposes CPU, memory, restart, network, and filesystem I/O metrics for running containers.
- Mounted read-only host paths allow cAdvisor to observe Docker runtime/container stats.
- Scraped by Prometheus at `cadvisor:8080`.

### 6) `grafana` — Visualization

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
- `latest_candle_timestamp` (Gauge)
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

### Ingestion status

```bash
curl -sS http://localhost:8000/ingestion/status
```

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
