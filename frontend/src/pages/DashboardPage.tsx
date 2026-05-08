import { AlertTriangle } from 'lucide-react';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
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
  const severity = error ? 'error' : health?.status === 'OK' ? 'ok' : 'warn';

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-12 w-64 animate-pulse rounded-lg bg-surface-900" />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">{Array.from({ length: 8 }).map((_, i) => <div key={i} className="h-32 animate-pulse rounded-xl bg-surface-900" />)}</div>
        <div className="h-64 animate-pulse rounded-xl bg-surface-900" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-[28px] font-semibold tracking-tight">Operational Overview</h1>
          <p className="mt-1 text-sm text-text-secondary">Health, ingestion stability, and data quality.</p>
        </div>
        <StatusPill label={error ?? 'Stable'} severity={severity} />
      </div>

      {error && <div className="flex items-start gap-2 rounded-xl bg-accent-red/10 px-3 py-2.5 text-sm text-accent-red"><AlertTriangle size={16} className="mt-0.5" /> API request failed. Check connectivity to backend.</div>}

      <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard title="API Health" value={health?.status ?? '—'} status="live" />
        <MetricCard title="Ingestion Status" value={ingestion?.collectorStatus ?? '—'} status="live" />
        <MetricCard title="Latest Candle" value={ingestion?.latestCandleTime ?? '—'} hint="UTC timestamp" />
        <MetricCard title="Lag Seconds" value={ingestion?.heartbeatAgeSeconds ?? '—'} hint="heartbeat age" />
        <MetricCard title="Total Candles" value={ingestion?.totalCandleCount ?? '—'} hint="stored rows" />
        <MetricCard title="Last Backfill Count" value={ingestion?.lastBackfillCandleCount ?? '—'} hint="most recent run" />
        <MetricCard title="Backfill Status" value={ingestion?.lastBackfillStatus ?? '—'} />
        <MetricCard title="Last Backfill Time" value={ingestion?.lastBackfillTime ?? '—'} />
      </section>

      <section className="rounded-xl bg-surface-900 p-4 shadow-card ring-1 ring-surface-700/70 md:p-5">
        <h2 className="mb-4 text-sm font-medium text-text-secondary">Lag trend (seconds)</h2>
        <div className="h-56">
          {lagHistory.length === 0 ? (
            <div className="flex h-full items-center justify-center rounded-lg bg-surface-850 text-sm text-text-muted">No lag data yet.</div>
          ) : (
            <ResponsiveContainer>
              <AreaChart data={lagHistory} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                <defs>
                  <linearGradient id="lag" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#6f8fdc" stopOpacity={0.18} />
                    <stop offset="100%" stopColor="#6f8fdc" stopOpacity={0.01} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#252d3a" strokeDasharray="2 4" vertical={false} />
                <XAxis dataKey="t" stroke="#818b9b" tickLine={false} axisLine={false} fontSize={11} />
                <YAxis stroke="#818b9b" tickLine={false} axisLine={false} fontSize={11} width={28} />
                <Tooltip contentStyle={{ borderRadius: '10px', border: '1px solid #252d3a', backgroundColor: '#12161d', color: '#eef2f7', fontSize: '12px' }} />
                <Area type="monotone" dataKey="lag" stroke="#6f8fdc" fill="url(#lag)" strokeWidth={1.4} />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </section>
    </div>
  );
}
