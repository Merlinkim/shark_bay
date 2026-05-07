export interface HealthResponse {
  status: string;
  timestamp?: string;
}

export interface IngestionResponse {
  latest_candle?: string;
  lag_seconds?: number;
  poll_count?: number;
  reconnect_count?: number;
  gap_recovery_status?: string;
  data_quality_summary?: string;
  ingestion_health?: string;
}

export type Severity = 'ok' | 'warn' | 'error' | 'unknown';
