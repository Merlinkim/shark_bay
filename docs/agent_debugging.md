# Agent Debugging Runbook

This runbook is for OpenClaw/agents debugging **without changing secrets, live-trading settings, or deleting volumes**.

## Safety Rules

Allowed:
- Inspect container status/logs and query health/read-only endpoints.
- Suggest fixes and gather diagnostics.
- Restart non-critical services **only when explicitly approved by a human**.

Forbidden:
- Modify secrets or `.env` secret values.
- Run any live trading or risk-setting changes.
- Delete database volumes.
- Execute destructive commands without human approval.

## Copy-Paste Diagnostics

```bash
docker compose ps
docker compose logs --tail=200 api
docker compose logs --tail=200 ingestor
docker compose logs --tail=200 research-ui
docker compose logs --tail=200 prometheus
docker compose logs --tail=200 grafana
curl -sS http://localhost:8000/health
curl -sS http://localhost:8000/ingestion/status
python -m app.data_quality --symbol BTCUSDT --interval 1m --lookback-hours 2
```

### Latest candle DB query

```bash
docker compose exec -T db psql -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-market_data}" \
  -c "SELECT symbol, MAX(open_time) AS latest_open_time, COUNT(*) AS total_rows FROM candles_1m WHERE symbol='BTCUSDT' GROUP BY symbol;"
```

### Recent gap query

```bash
docker compose exec -T db psql -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-market_data}" \
  -c "SELECT ts, gap_count, duplicate_count, data_lag_seconds FROM data_quality_snapshots ORDER BY ts DESC LIMIT 20;"
```

### Backtest fixed-window reproducibility test

```bash
python -m app.backtest --symbol BTCUSDT --interval 1m --start-time 2026-05-01T00:00:00+00:00 --end-time 2026-05-01T12:00:00+00:00
python -m app.backtest --symbol BTCUSDT --interval 1m --start-time 2026-05-01T00:00:00+00:00 --end-time 2026-05-01T12:00:00+00:00
# Compare summary metrics from the two run directories
```

## Failure Triage Table

| Failure | Symptoms | Likely causes | Commands to inspect | Safe recovery actions | Requires human approval |
|---|---|---|---|---|---|
| API down | `/health` fails, 5xx, `api` unhealthy | API crash loop, DB unavailable, bad env wiring | `docker compose ps`; `docker compose logs --tail=200 api`; `docker compose logs --tail=200 db` | Verify DB health and non-secret env values; if approved restart API: `docker compose restart api` | Any secret changes, schema/data-destructive changes |
| ingestor stopped | No fresh candles, stale ingestion status | Crash loop, upstream API failures, DB write failures | `docker compose ps`; `docker compose logs --tail=200 ingestor`; `curl -sS http://localhost:8000/ingestion/status` | Confirm DB reachable; if approved restart ingestor: `docker compose restart ingestor` | Changing symbol/risk-related behavior in production |
| data lag high | `data_lag_seconds` elevated, stale latest candle | ingestor stalled, upstream latency, DB contention | `python -m app.data_quality --symbol BTCUSDT --interval 1m --lookback-hours 2`; latest candle query; ingestor logs | Continue observation, restart ingestor with approval, capture incident timestamps | Any destructive DB action |
| gap_count high | Quality snapshots show rising gaps | missed polls, backfill limits too tight, repeated ingest errors | `python -m app.data_quality ...`; recent gap query; ingestor logs | Run manual read-only diagnostics; approved restart of ingestor | Tuning production settings beyond documented defaults |
| Grafana no data | Panels empty / N/A | Prometheus down, datasource/provisioning issue, scrape targets down | `docker compose logs --tail=200 grafana`; `docker compose logs --tail=200 prometheus`; `curl -sS http://localhost:9090/api/v1/targets` | Restart grafana/prometheus only with approval; verify targets UP | Editing dashboards/provisioning in prod without review |
| Streamlit UI error | UI 500, blank page, API calls fail | research-ui crash, API unreachable, bad API_BASE_URL | `docker compose logs --tail=200 research-ui`; `docker compose logs --tail=200 api`; `curl -sS http://localhost:8000/health` | Restart `research-ui` with approval; verify API is healthy | Config changes in prod without review |
| backtest API error | `/backtests` or `/backtests/run` errors | invalid payload, API exception, DB read issues | `docker compose logs --tail=200 api`; query `/backtests`; run fixed-window reproducibility test | Retry with known-good payload; collect tracebacks for humans | Any strategy/risk behavior changes |
| DB connection failure | API ready fails, ingestor DB errors | DB not healthy, wrong DB URL, exhausted connections | `docker compose ps`; `docker compose logs --tail=200 db`; `docker compose logs --tail=200 api`; `docker compose logs --tail=200 ingestor` | Wait for DB health, restart dependent services with approval | Volume deletion/reset, credential rotation |

