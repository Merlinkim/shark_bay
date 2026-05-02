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

## Tests

```bash
python -m unittest discover -s tests -p 'test_*.py'
```
