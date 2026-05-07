import { MetricCard } from '../components/MetricCard';
import { useOperationsPolling } from '../hooks/useOperationsPolling';

export function MarketDataPage() {
  const { ingestion } = useOperationsPolling();

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Market Data</h1>
        <p className="mt-1 text-sm text-text-secondary">Read-only operational feed visibility for BTCUSDT ingestion.</p>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard title="Latest BTCUSDT Candle" value={ingestion?.latest_candle ?? 'n/a'} />
        <MetricCard title="Ingestion Metrics" value={ingestion?.ingestion_health ?? 'unknown'} />
        <MetricCard title="Data Quality" value={ingestion?.data_quality_summary ?? 'pending'} />
        <MetricCard title="Latest Backfill" value={ingestion?.gap_recovery_status ?? 'none'} />
      </div>
    </div>
  );
}
