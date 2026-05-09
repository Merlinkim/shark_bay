import type { HealthResponse, IngestionApiResponse } from '../types/status';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

export type ResearchFeatureResponse = {
  symbol: string;
  interval: string;
  lookback_hours: number;
  rows_used: number;
  latest_open_time: string | null;
  features: Record<string, string | number | null>;
  quality: { status: string; gaps_detected: number; notes: string[] };
};

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) {
    throw new Error(`${path} failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => getJson<HealthResponse>('/health'),
  ingestionStatus: () => getJson<IngestionApiResponse>('/ingestion/status'),
  researchFeatures: (symbol = 'BTCUSDT', interval = '1m', lookbackHours = 24) =>
    getJson<ResearchFeatureResponse>(`/research/features?symbol=${symbol}&interval=${interval}&lookback_hours=${lookbackHours}`),
};
