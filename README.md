# Shark Bay - Operational Baseline (Post Milestone 2)

This phase hardens ingestion/API runtime reliability and observability before dashboards/backtesting/paper trading.

## What's included

- Structured JSON logging for API and ingestor.
- API request logging middleware (method/path/status/duration).
- Ingestion operational metrics (poll/success/error/retry/reconnect).
- Collector heartbeat persisted in PostgreSQL.
- Healthchecks:
  - API liveness: `GET /health/live`
  - API readiness: `GET /health/ready` (DB dependency)
  - existing `GET /health`
- Graceful shutdown handling for ingestor (SIGTERM/SIGINT).
- Missing candle detection structure (event table + placeholder detection write).
- Retry/reconnect tracking metrics surfaced via heartbeat.
- `.env.example` and helper `Makefile` commands.

## Quick start

```bash
cp .env.example .env
make up
```

## Operational endpoints

```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8000/health/live
curl -s http://localhost:8000/health/ready
curl -s http://localhost:8000/ingestion/status
```

## Logs

```bash
make logs-api
make logs-ingestor
```

Logs are JSON, suitable for ingestion by ELK/Loki/CloudWatch.

## Database operational tables

- `collector_heartbeat`: latest collector heartbeat and counters.
- `missing_candle_events`: structure for missing candle event records.

## Testing

```bash
make test
```

## Note

Dashboard/backtesting/paper trading are intentionally not included in this phase.
