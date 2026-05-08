export interface HealthResponse {
  status: string;
}

export interface IngestionApiResponse {
  latest_candle_time?: string | null;
  last_candle_time?: string | null;
  total_candle_count?: number;
  collector_status?: string;
  last_backfill_status?: string | null;
  last_backfill_candle_count?: number | null;
  last_backfill_time?: string | null;
  heartbeat?: {
    last_heartbeat_at?: string | null;
    [key: string]: unknown;
  };
}

export interface IngestionViewModel {
  latestCandleTime: string | null;
  collectorStatus: string;
  totalCandleCount: number;
  lastBackfillStatus: string | null;
  lastBackfillCandleCount: number | null;
  lastBackfillTime: string | null;
  heartbeatAgeSeconds: number | null;
}

export type Severity = 'ok' | 'warn' | 'error' | 'unknown';
