import type { HealthResponse, IngestionApiResponse } from '../types/status';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

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
};
