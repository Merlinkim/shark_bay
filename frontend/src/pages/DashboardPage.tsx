import { AlertTriangle } from 'lucide-react';
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis } from 'recharts';
import { MetricCard } from '../components/MetricCard';
import { StatusPill } from '../components/StatusPill';
import { useOperationsPolling } from '../hooks/useOperationsPolling';

const lagHistory = [
  { t: '09:10', lag: 1.2 },
  { t: '09:20', lag: 0.9 },
  { t: '09:30', lag: 1.6 },
  { t: '09:40', lag: 1.1 },
  { t: '09:50', lag: 0.8 },
];

export function DashboardPage() {
  const { health, ingestion, loading, error } = useOperationsPolling();
  const severity = error ? 'error' : health?.status === 'ok' ? 'ok' : 'warn';

  if (loading) return <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">{Array.from({ length: 8 }).map((_, i) => <div key={i} className="h-28 animate-pulse rounded-xl bg-surface-900" />)}</div>;

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Operational Overview</h1>
          <p className="mt-1 text-sm text-text-secondary">System health, ingestion, and data quality snapshot.</p>
        </div>
        <StatusPill label={error ?? 'Stable'} severity={severity} />
      </div>

      {error && <div className="flex items-start gap-2 rounded-xl border border-accent-red/30 bg-accent-red/10 p-3 text-sm text-accent-red"><AlertTriangle size={16} className="mt-0.5" /> API temporarily unavailable. Displaying latest successful values.</div>}

      <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard title="API Health" value={health?.status ?? 'unknown'} />
        <MetricCard title="Ingestion Status" value={ingestion?.ingestion_health ?? 'unknown'} />
        <MetricCard title="Latest Candle" value={ingestion?.latest_candle ?? 'n/a'} />
        <MetricCard title="Lag Seconds" value={ingestion?.lag_seconds ?? 'n/a'} />
        <MetricCard title="Poll Count" value={ingestion?.poll_count ?? 0} />
        <MetricCard title="Reconnect Count" value={ingestion?.reconnect_count ?? 0} />
        <MetricCard title="Gap Recovery" value={ingestion?.gap_recovery_status ?? 'unknown'} />
        <MetricCard title="Data Quality" value={ingestion?.data_quality_summary ?? 'pending'} />
      </section>

      <section className="rounded-xl border border-surface-700 bg-surface-900 p-4 shadow-card">
        <h2 className="mb-3 text-sm font-medium text-text-secondary">Lag trend (seconds)</h2>
        <div className="h-52">
          <ResponsiveContainer>
            <AreaChart data={lagHistory}>
              <defs>
                <linearGradient id="lag" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#5b8cff" stopOpacity={0.28} />
                  <stop offset="100%" stopColor="#5b8cff" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="t" stroke="#7e8797" tickLine={false} axisLine={false} />
              <Tooltip contentStyle={{ borderRadius: '12px', border: '1px solid #222836', backgroundColor: '#11141a', color: '#f2f4f8' }} />
              <Area type="monotone" dataKey="lag" stroke="#5b8cff" fill="url(#lag)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </section>
    </div>
  );
}
