import { Link } from 'react-router-dom';
import { MetricCard } from '../components/MetricCard';
import { useOperationsPolling } from '../hooks/useOperationsPolling';

export function MarketDataPage() {
  const { ingestion } = useOperationsPolling();

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Market Data</h1>
          <p className="mt-1 text-sm text-text-secondary">Read-only operational feed visibility for BTCUSDT ingestion.</p>
        </div>
        <Link to="/market-data/live-chart" className="rounded-lg bg-surface-900 px-3 py-2 text-xs text-text-secondary ring-1 ring-surface-700/70">Open Live Chart</Link>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard title="Latest BTCUSDT Candle" value={ingestion?.latestCandleTime ?? '—'} />
        <MetricCard title="Collector Status" value={ingestion?.collectorStatus ?? '—'} />
        <MetricCard title="Total Candles" value={ingestion?.totalCandleCount ?? '—'} />
        <MetricCard title="Latest Backfill" value={ingestion?.lastBackfillStatus ?? '—'} />
      </div>
    </div>
  );
}
