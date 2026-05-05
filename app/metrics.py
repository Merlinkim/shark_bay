from prometheus_client import Counter, Gauge, Histogram

candle_insert_total = Counter(
    "candle_insert_total",
    "Total number of candles inserted or upserted by the ingestor",
)

duplicate_candle_total = Counter(
    "duplicate_candle_total",
    "Total number of duplicate candles detected (upsert update path)",
)

ingest_error_total = Counter(
    "ingest_error_total",
    "Total number of ingestion errors",
)

websocket_reconnect_total = Counter(
    "websocket_reconnect_total",
    "Total number of reconnect attempts by ingestor",
)

rest_backfill_requested_total = Counter(
    "rest_backfill_requested_total",
    "Total number of REST gap backfill requests",
)

rest_backfill_completed_total = Counter(
    "rest_backfill_completed_total",
    "Total number of successful REST gap backfills",
)

rest_backfill_failed_total = Counter(
    "rest_backfill_failed_total",
    "Total number of failed REST gap backfills",
)

rest_backfill_candles_inserted_total = Counter(
    "rest_backfill_candles_inserted_total",
    "Total number of candles inserted during REST gap backfills",
)

missing_candle_gap_count = Gauge(
    "missing_candle_gap_count",
    "Current detected number of missing 1m candles in gap recovery",
)

latest_candle_timestamp = Gauge(
    "latest_candle_timestamp",
    "Unix timestamp of latest candle processed",
)


invalid_ohlc_total = Counter(
    "invalid_ohlc_total",
    "Total number of candles with invalid OHLC relationships",
)

invalid_volume_total = Counter(
    "invalid_volume_total",
    "Total number of candles with invalid volume values",
)

future_timestamp_total = Counter(
    "future_timestamp_total",
    "Total number of candles observed with future timestamps",
)

last_backfill_candle_count = Gauge(
    "last_backfill_candle_count",
    "Number of candles inserted by the most recent backfill run",
)

db_connection_status = Gauge(
    "db_connection_status",
    "Database connectivity status (1=up, 0=down)",
    ["service"],
)

api_request_total = Counter(
    "api_request_total",
    "Total number of API requests",
    ["method", "path", "status_code"],
)

api_request_latency_seconds = Histogram(
    "api_request_latency_seconds",
    "API request latency in seconds",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
