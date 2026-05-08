import { useEffect, useMemo, useState } from 'react';
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid } from 'recharts';
import { useOperationsPolling } from '../hooks/useOperationsPolling';

type ServiceCheck = { service: string; status: string; latency_ms: number | null; detail?: string; uptime?: string; restart_count?: number | null; port?: string | null; notes?: string };
type Point = { t: string; cpu: number; memory: number; diskWrite: number; netOut: number };

type InfraPayload = {
  checked_at: string;
  host_overview: {
    instance_status: string;
    cpu_usage_pct: number | null;
    memory_usage_pct: number | null;
    disk_usage_pct: number | null;
    network_traffic: { bytes_sent: number; bytes_recv: number } | null;
    disk_traffic: { read_bytes: number; write_bytes: number } | null;
    uptime_seconds: number | null;
    host_name?: string | null;
    platform?: string | null;
    kernel?: string | null;
    docker_engine_reachable?: boolean | null;
  };
  docker_services: ServiceCheck[];
  storage: { db_size_bytes: number | null; disk_remaining_bytes: number | null };
};

const fmtBytes = (n: number | null | undefined) => {
  if (n == null) return '—';
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(2)} GB`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)} MB`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(2)} KB`;
  return `${n} B`;
};
const fmtRate = (n: number | null | undefined) => (n == null ? '—' : `${fmtBytes(n)}/s`);
const fmtUptime = (seconds: number | null | undefined) => {
  if (seconds == null) return '—';
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
};
const statusColor = (s: string) => (s === 'healthy' ? 'bg-accent-green' : s === 'degraded' || s === 'pending' ? 'bg-accent-amber' : 'bg-accent-red');

export function InfrastructurePage() {
  const { ingestion } = useOperationsPolling();
  const [infra, setInfra] = useState<InfraPayload | null>(null);
  const [trend, setTrend] = useState<Point[]>([]);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const res = await fetch(`${import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'}/ops/infrastructure`);
        if (!res.ok) return;
        const payload = (await res.json()) as InfraPayload;
        if (!alive) return;
        setInfra(payload);
        setTrend((prev) => [...prev.slice(-29), {
          t: new Date().toISOString().slice(11, 19),
          cpu: payload.host_overview.cpu_usage_pct ?? 0,
          memory: payload.host_overview.memory_usage_pct ?? 0,
          diskWrite: payload.host_overview.disk_traffic?.write_bytes ?? 0,
          netOut: payload.host_overview.network_traffic?.bytes_sent ?? 0,
        }]);
      } catch {
        if (alive) setInfra(null);
      }
    };
    void load();
    const timer = setInterval(() => void load(), 10_000);
    return () => { alive = false; clearInterval(timer); };
  }, []);

  const freshness = useMemo(() => ingestion?.latestCandleTime ? Math.floor((Date.now() - new Date(ingestion.latestCandleTime).getTime()) / 1000) : null, [ingestion?.latestCandleTime]);
  const host = infra?.host_overview;
  const serviceRows = infra?.docker_services ?? [];
  const dbHealthy = serviceRows.find((s) => s.service === 'db')?.status === 'healthy';
  const prometheusHealthy = serviceRows.find((s) => s.service === 'prometheus')?.status === 'healthy';
  const grafanaHealthy = serviceRows.find((s) => s.service === 'grafana')?.status === 'healthy';

  return (
    <div className="space-y-3">
      <div><h1 className="text-xl font-semibold tracking-tight">Infrastructure</h1><p className="text-xs text-text-secondary">Read-only stack infrastructure monitoring surface.</p></div>

      <section className="grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-3 xl:grid-cols-10">
        {[
          ['Host', host?.host_name ?? '—'], ['Platform', host?.platform ?? '—'], ['Kernel', host?.kernel ?? '—'], ['Instance', host?.instance_status ?? 'unknown'],
          ['CPU usage', host?.cpu_usage_pct == null ? '—' : `${host.cpu_usage_pct}%`], ['Memory usage', host?.memory_usage_pct == null ? '—' : `${host.memory_usage_pct}%`],
          ['Disk usage', host?.disk_usage_pct == null ? '—' : `${host.disk_usage_pct}%`], ['Net traffic', fmtRate(host?.network_traffic?.bytes_recv)], ['Disk traffic', fmtRate(host?.disk_traffic?.write_bytes)], ['Uptime', fmtUptime(host?.uptime_seconds)],
        ].map(([k, v]) => <div key={String(k)} className="rounded-md bg-surface-900 px-2.5 py-2 ring-1 ring-surface-700/60">{k}<div className="text-text-secondary">{v}</div></div>)}
      </section>

      <section className="rounded-lg bg-surface-900 p-3 ring-1 ring-surface-700/70"><h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">Docker Services</h2><div className="overflow-x-auto"><table className="w-full text-left text-[11px]"><thead className="text-text-muted"><tr><th>service</th><th>status</th><th>uptime</th><th>restart</th><th>port</th><th>notes</th></tr></thead><tbody>{serviceRows.map((s) => <tr key={s.service} className="border-t border-surface-700/50"><td className="py-1.5 font-semibold uppercase">{s.service}</td><td><span className={`mr-1 inline-block h-2 w-2 rounded-full ${statusColor(s.status)}`} />{s.status}</td><td>{s.uptime === 'not_available' || !s.uptime ? '—' : s.uptime}</td><td>{s.restart_count == null ? '—' : s.restart_count}</td><td>{s.port ?? '—'}</td><td className="text-text-secondary">{s.detail ?? s.notes ?? (s.latency_ms != null ? `${s.latency_ms}ms` : '—')}</td></tr>)}</tbody></table></div></section>

      <section className="grid grid-cols-1 gap-2 md:grid-cols-2">
        {([['CPU %','cpu'],['Memory %','memory'],['Disk Write','diskWrite'],['Network Out','netOut']] as const).map(([label,key]) => (
          <div key={label} className="rounded-lg bg-surface-900 p-3 ring-1 ring-surface-700/70"><h3 className="mb-2 text-xs font-semibold text-text-muted">{label}</h3><div className="h-24">{trend.length===0?<div className="flex h-full items-center justify-center rounded bg-surface-850 text-xs text-text-secondary">No trend data yet.</div>:<ResponsiveContainer><LineChart data={trend}><CartesianGrid stroke="#252d3a" strokeOpacity={0.25} vertical={false}/><XAxis dataKey="t" hide/><YAxis hide domain={['auto','auto']}/><Tooltip contentStyle={{background:'#12161d',border:'1px solid #252d3a',color:'#eef2f7'}}/><Line type="monotone" dataKey={key} stroke="#6f8fdc" strokeWidth={1.5} dot={false} isAnimationActive={false}/></LineChart></ResponsiveContainer>}</div></div>
        ))}
      </section>

      <section className="rounded-lg bg-surface-900 p-3 ring-1 ring-surface-700/70"><h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">Storage / Data Growth</h2><div className="grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-5"><div className="rounded bg-surface-850 p-2">DB candle rows<div className="text-text-secondary">{ingestion?.totalCandleCount ?? '—'}</div></div><div className="rounded bg-surface-850 p-2">Latest candle<div className="text-text-secondary">{ingestion?.latestCandleTime ?? '—'}</div></div><div className="rounded bg-surface-850 p-2">Freshness<div className="text-text-secondary">{freshness ?? '—'}s</div></div><div className="rounded bg-surface-850 p-2">DB size<div className="text-text-secondary">{fmtBytes(infra?.storage.db_size_bytes)}</div></div><div className="rounded bg-surface-850 p-2">Disk remaining<div className="text-text-secondary">{fmtBytes(infra?.storage.disk_remaining_bytes)}</div></div></div></section>

      <section className="rounded-lg bg-surface-900 p-3 ring-1 ring-surface-700/70"><h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">VPS Readiness Checklist</h2><ul className="grid grid-cols-1 gap-1 text-xs sm:grid-cols-2">{[['Docker running',host?.docker_engine_reachable ? 'healthy' : 'pending'],['Compose stack running','pending'],['DB healthy',dbHealthy?'healthy':'pending'],['API reachable',serviceRows.find((s)=>s.service==='api')?.status??'pending'],['Ingestor freshness < 60s', freshness != null && freshness < 60 ? 'healthy':'pending'],['Prometheus reachable',prometheusHealthy?'healthy':'pending'],['Grafana reachable',grafanaHealthy?'healthy':'pending'],['cAdvisor reachable',serviceRows.find((s)=>s.service==='cadvisor')?.status??'pending'],['Tailscale expected','pending'],['Disk remaining > threshold', (infra?.storage.disk_remaining_bytes ?? 0) > 20_000_000_000 ? 'healthy':'pending']].map(([k,v])=><li key={String(k)} className="rounded bg-surface-850 px-2 py-1.5">{k}: <span className="text-text-secondary">{v}</span></li>)}</ul></section>
    </div>
  );
}
