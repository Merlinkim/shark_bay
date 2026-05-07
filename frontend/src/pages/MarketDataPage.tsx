import { MetricCard } from '../components/MetricCard';
import { useOperationsPolling } from '../hooks/useOperationsPolling';

export function MarketDataPage() {
  const { ingestion } = useOperationsPolling();
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Market Data Operations</h1>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <MetricCard title="Latest BTCUSDT Candle" value={ingestion?.latest_candle ?? 'n/a'} />
        <MetricCard title="Ingestion Metrics" value={ingestion?.ingestion_health ?? 'unknown'} />
        <MetricCard title="Data Quality" value={ingestion?.data_quality_summary ?? 'pending'} />
        <MetricCard title="Backfill Activity" value={ingestion?.gap_recovery_status ?? 'none'} />
      </div>
    </div>
  );
}
