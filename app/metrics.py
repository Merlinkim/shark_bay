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

latest_candle_timestamp = Gauge(
    "latest_candle_timestamp",
    "Unix timestamp of latest candle processed",
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
