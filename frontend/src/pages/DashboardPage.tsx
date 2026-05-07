import { Activity, AlertTriangle } from 'lucide-react';
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis } from 'recharts';
import { MetricCard } from '../components/MetricCard';
import { StatusPill } from '../components/StatusPill';
import { useOperationsPolling } from '../hooks/useOperationsPolling';

const lagHistory = [
  { t: '09:10', lag: 1.2 }, { t: '09:20', lag: 0.9 }, { t: '09:30', lag: 1.6 }, { t: '09:40', lag: 1.1 }, { t: '09:50', lag: 0.8 },
];

export function DashboardPage() {
  const { health, ingestion, loading, error } = useOperationsPolling();
  const severity = error ? 'error' : health?.status === 'ok' ? 'ok' : 'warn';

  if (loading) return <div className="grid gap-4 md:grid-cols-4">{Array.from({ length: 8 }).map((_, i) => <div key={i} className="h-24 animate-pulse rounded-xl bg-terminal-panel" />)}</div>;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Operations Overview</h1>
        <StatusPill label={error ?? 'All systems nominal'} severity={severity} />
      </div>
      {error && <div className="flex items-center gap-2 rounded-lg border border-neon-red/40 bg-neon-red/10 p-3 text-sm text-neon-red"><AlertTriangle size={16} /> API failure detected, showing latest cached state.</div>}
      <section className="grid gap-4 md:grid-cols-4">
        <MetricCard title="API Health" value={health?.status ?? 'unknown'} />
        <MetricCard title="Ingestion Status" value={ingestion?.ingestion_health ?? 'unknown'} />
        <MetricCard title="Latest Candle" value={ingestion?.latest_candle ?? 'n/a'} />
        <MetricCard title="Lag Seconds" value={ingestion?.lag_seconds ?? 'n/a'} />
        <MetricCard title="Poll Count" value={ingestion?.poll_count ?? 0} />
        <MetricCard title="Reconnect Count" value={ingestion?.reconnect_count ?? 0} />
        <MetricCard title="Gap Recovery" value={ingestion?.gap_recovery_status ?? 'unknown'} />
        <MetricCard title="Data Quality" value={ingestion?.data_quality_summary ?? 'pending'} />
      </section>
      <section className="rounded-xl border border-terminal-border bg-terminal-panel/70 p-4">
        <div className="mb-4 flex items-center gap-2 text-sm"><Activity size={16} className="text-neon-cyan" />Lag Trend (seconds)</div>
        <div className="h-56"><ResponsiveContainer><AreaChart data={lagHistory}><defs><linearGradient id="lag" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#29d3ff" stopOpacity={0.4}/><stop offset="95%" stopColor="#29d3ff" stopOpacity={0}/></linearGradient></defs><XAxis dataKey="t" stroke="#6f8399"/><Tooltip/><Area type="monotone" dataKey="lag" stroke="#29d3ff" fill="url(#lag)" strokeWidth={2}/></AreaChart></ResponsiveContainer></div>
      </section>
    </div>
  );
}
