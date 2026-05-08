import { useEffect, useState } from 'react';
import { api } from '../services/api';
import type { HealthResponse, IngestionApiResponse, IngestionViewModel } from '../types/status';

function toIngestionViewModel(raw: IngestionApiResponse): IngestionViewModel {
  const lastHeartbeat = raw.heartbeat?.last_heartbeat_at;
  const heartbeatAgeSeconds = lastHeartbeat
    ? Math.max(0, Math.floor((Date.now() - new Date(lastHeartbeat).getTime()) / 1000))
    : null;

  return {
    latestCandleTime: raw.latest_candle_time ?? raw.last_candle_time ?? null,
    collectorStatus: raw.collector_status ?? 'unknown',
    totalCandleCount: raw.total_candle_count ?? 0,
    lastBackfillStatus: raw.last_backfill_status ?? null,
    lastBackfillCandleCount: raw.last_backfill_candle_count ?? null,
    lastBackfillTime: raw.last_backfill_time ?? null,
    heartbeatAgeSeconds,
  };
}

export function useOperationsPolling(intervalMs = 10_000) {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [ingestion, setIngestion] = useState<IngestionViewModel | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;

    const fetchStatus = async () => {
      try {
        const [healthData, ingestionData] = await Promise.all([api.health(), api.ingestionStatus()]);
        if (!alive) return;
        setHealth(healthData);
        setIngestion(toIngestionViewModel(ingestionData));
        setError(null);
      } catch (fetchError) {
        if (!alive) return;
        setError(fetchError instanceof Error ? fetchError.message : 'Unknown API error');
      } finally {
        if (alive) setLoading(false);
      }
    };

    void fetchStatus();
    const timer = setInterval(() => void fetchStatus(), intervalMs);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [intervalMs]);

  return { health, ingestion, loading, error };
}
