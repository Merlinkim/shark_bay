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



export type ExperimentResult = {
  experiment_id: string;
  strategy_name: string;
  strategy_version: string;
  symbol: string;
  interval: string;
  dataset_start: string | null;
  dataset_end: string | null;
  dataset_row_count: number;
  dataset_fingerprint: string;
  parameters: Record<string, unknown>;
  features_used: string[];
  intended_regime: string;
  risk_profile: string;
  total_return_pct: number;
  sharpe: number;
  max_drawdown_pct: number;
  win_rate_pct: number;
  trade_count: number;
  status: string;
  is_simulated: boolean;
  created_at: string;
};

export type StrategyRegistrySpec = {
  strategy_name: string;
  display_name: string;
  description: string;
  status: string;
  mode: string;
  symbols: string[];
  interval: string;
  features_used: string[];
  parameters: Record<string, unknown>;
  risk_profile: string;
  intended_regime: string;
  version: string;
  created_at: string;
  updated_at: string;
};


export type ResearchAgentRecommendation = {
  generated_at: string;
  agent_version: string;
  symbol: string;
  interval: string;
  research_summary: { strategy_count: number; latest_experiment_count: number; analytics_total_experiments: number; notes: string[] };
  overfit_risk: { label: string; flags: string[] };
  strategy_assessments: Array<Record<string, unknown>>;
  recommended_experiments: Array<{ strategy_name: string; reason: string; proposed_params: Record<string, unknown>; proposed_date_range: Record<string, string | null>; priority: string; safety_note: string }>;
  rejected_strategies: Array<{ strategy_name: string; reason: string; severity: string; safety_note: string }>;
  next_actions: string[];
  safety: Record<string, boolean>;
};

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) throw new Error(`${path} failed with ${response.status}`);
  return response.json() as Promise<T>;
}

export const api = {
  health: () => getJson<HealthResponse>('/health'),
  ingestionStatus: () => getJson<IngestionApiResponse>('/ingestion/status'),
  researchFeatures: (symbol = 'BTCUSDT', interval = '1m', lookbackHours = 24) => getJson<ResearchFeatureResponse>(`/research/features?symbol=${symbol}&interval=${interval}&lookback_hours=${lookbackHours}`),
  strategyRegistry: () => getJson<{ strategies: StrategyRegistrySpec[] }>('/strategies/registry'),
  latestExperiments: (symbol = 'BTCUSDT', interval = '1m', limit = 20) => getJson<{ experiments: ExperimentResult[] }>(`/research/experiments/latest?symbol=${symbol}&interval=${interval}&limit=${limit}`),
  researchAnalytics: (symbol = 'BTCUSDT', interval = '1m', limit = 100) => getJson<ResearchAnalyticsResponse>(`/research/analytics?symbol=${symbol}&interval=${interval}&limit=${limit}`),
  researchAgentRecommendations: (symbol = 'BTCUSDT', interval = '1m', strategy?: string, start?: string, end?: string) => {
    const params = new URLSearchParams({ symbol, interval });
    if (strategy) params.set('strategy', strategy);
    if (start) params.set('start', start);
    if (end) params.set('end', end);
    return getJson<ResearchAgentRecommendation>(`/research/agent/recommendations?${params.toString()}`);
  },
};


export type ResearchAnalyticsResponse = {
  summary: {
    total_experiments: number;
    best_strategy_by_sharpe: { strategy_name: string; sharpe: number; experiment_id: string } | null;
    best_strategy_by_return: { strategy_name: string; total_return_pct: number; experiment_id: string } | null;
    worst_strategy_by_drawdown: { strategy_name: string; max_drawdown_pct: number; experiment_id: string } | null;
  };
  strategy_leaderboard: Array<{ strategy_name: string; experiments: number; average_sharpe: number; average_return_pct: number; win_rate_pct: number; trade_count: number; average_drawdown_pct: number }>;
  regime_breakdown: Array<{ regime: string; experiments: number; average_sharpe: number; average_return_pct: number; average_drawdown_pct: number; average_win_rate_pct: number }>;
  recent_rankings: Array<{ experiment_id: string; strategy_name: string; sharpe: number; total_return_pct: number; max_drawdown_pct: number; created_at: string }>;
  generated_at: string;
};
