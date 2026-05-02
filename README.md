# Shark Bay - Operational Monitoring (Milestone 3)

This milestone adds **operational monitoring only** for ingestion and API reliability using Prometheus + Grafana.

## What's included

- Prometheus service in Docker Compose (`http://localhost:9090`).
- Grafana service in Docker Compose (`http://localhost:3000`, default `admin/admin`).
- Metrics endpoint(s):
  - API: `GET /metrics`
  - Ingestor: Prometheus exporter on port `9100`
- Python metrics via `prometheus_client`.
- Prometheus scrape configuration for API and ingestor targets.
- Grafana datasource provisioning for:
  - Prometheus
  - PostgreSQL
- Grafana dashboard provisioning with core operational panels.

## Exposed metrics

- `candle_insert_total`
- `duplicate_candle_total`
- `ingest_error_total`
- `websocket_reconnect_total`
- `latest_candle_timestamp`
- `db_connection_status`
- `api_request_total`
- `api_request_latency_seconds`

## Dashboard panels

- ingestion health
- latest candle timestamp
- candle insert count/rate
- duplicate count
- error count
- reconnect count
- API request count
- API latency
- DB connection status

## Quick start

```bash
cp .env.example .env
make up
```

Open:

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000
- API docs: http://localhost:8000/docs

## Testing

```bash
make test
```

## Scope note

This milestone excludes backtesting, paper trading, strategy execution, and live trading.
