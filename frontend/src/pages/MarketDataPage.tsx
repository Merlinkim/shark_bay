import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { MetricCard } from '../components/MetricCard';
import { useOperationsPolling } from '../hooks/useOperationsPolling';
import { api, type IngestionTelemetryResponse } from '../services/api';

export function MarketDataPage() {
  const { ingestion } = useOperationsPolling();
  const [telemetry, setTelemetry] = useState<IngestionTelemetryResponse | null>(null);

  useEffect(() => {
    api.ingestionTelemetry().then(setTelemetry).catch(() => setTelemetry(null));
  }, []);

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

      <section className="rounded-lg bg-surface-900 p-3 ring-1 ring-surface-700/70 overflow-x-auto">
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">Ingestion Telemetry</h2>
        {!telemetry ? <div className="text-xs text-text-secondary">Telemetry unavailable.</div> : <table className="w-full text-left text-[11px]"><thead className="text-text-muted"><tr><th>symbol</th><th>latest candle timestamp</th><th>ingestion lag (s)</th><th>reconnect count</th></tr></thead><tbody>{telemetry.symbols.map((symbol)=><tr key={symbol} className="border-t border-surface-700/50"><td className="py-1.5 font-semibold">{symbol}</td><td>{telemetry.symbol_metrics[symbol]?.latest_candle_timestamp ?? "—"}</td><td>{telemetry.symbol_metrics[symbol]?.ingestion_lag_seconds?.toFixed?.(1) ?? "—"}</td><td>{telemetry.symbol_metrics[symbol]?.reconnect_total ?? 0}</td></tr>)}</tbody></table>}
      </section>
    </div>
  );
}
