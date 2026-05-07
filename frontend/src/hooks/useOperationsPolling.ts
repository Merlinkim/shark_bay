import { useEffect, useState } from 'react';
import { api } from '../services/api';
import type { HealthResponse, IngestionResponse } from '../types/status';

export function useOperationsPolling(intervalMs = 10_000) {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [ingestion, setIngestion] = useState<IngestionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;

    const fetchStatus = async () => {
      try {
        const [healthData, ingestionData] = await Promise.all([api.health(), api.ingestionStatus()]);
        if (!alive) return;
        setHealth(healthData);
        setIngestion(ingestionData);
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
