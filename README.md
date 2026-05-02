# Shark Bay - Milestone 2

Milestone 2 exposes ingested candle data via a FastAPI service.

## Services

- PostgreSQL database
- Python ingestor service
- FastAPI API service

## Run with Docker Compose

```bash
docker compose up --build
```

## API endpoints

### Health

```bash
curl -s http://localhost:8000/health
```

Example response:

```json
{"status":"OK"}
```

### Candles

```bash
curl -s "http://localhost:8000/candles?symbol=BTCUSDT&interval=1m&limit=100"
```

### Ingestion status

```bash
curl -s http://localhost:8000/ingestion/status
```

Expected fields:
- `last_candle_time`
- `total_candle_count`
- `collector_status`

## Logs

View API logs:

```bash
docker compose logs -f api
```

View ingestor logs:

```bash
docker compose logs -f ingestor
```

## Quick DB check

```bash
docker compose exec db psql -U postgres -d market_data -c "SELECT symbol, open_time, close FROM candles_1m ORDER BY open_time DESC LIMIT 5;"
```
