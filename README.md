# Shark Bay - Milestone 1

Milestone 1 implements a minimal data-ingestion stack:

- PostgreSQL database
- Python ingestor service
- BTCUSDT 1m candle fetch from Binance public API
- Insert/upsert into PostgreSQL

## Run with Docker Compose

```bash
docker compose up --build
```

## Verify inserts

```bash
docker compose exec db psql -U postgres -d market_data -c "SELECT symbol, open_time, open, high, low, close, volume FROM candles_1m ORDER BY open_time DESC LIMIT 5;"
```

## Observability and logs

The ingestor now writes structured Python logs to stdout/stderr so `docker compose logs` shows runtime activity.

### View ingestor logs

```bash
docker compose logs -f ingestor
```

You should see logs for:
- Startup configuration (with masked DB password)
- Database connection success/failure
- REST polling start
- Per-candle insert/upsert events
- Exception traces for failures

### Verify ingestion from logs + DB

1. Confirm recent `inserted` or `upserted` candle log lines:

```bash
docker compose logs --tail=100 ingestor
```

2. Confirm rows are present and updating in PostgreSQL:

```bash
docker compose exec db psql -U postgres -d market_data -c "SELECT symbol, open_time, close_time, open, high, low, close, volume, trades FROM candles_1m ORDER BY open_time DESC LIMIT 5;"
```

## Tests

```bash
python -m unittest discover -s tests -p 'test_*.py'
```
