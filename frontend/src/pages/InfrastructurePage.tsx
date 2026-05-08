import { useEffect, useMemo, useState } from 'react';
import { useOperationsPolling } from '../hooks/useOperationsPolling';

type ServiceCheck = { service: string; status: string; latency_ms: number | null; detail?: string };

type InfraPayload = {
  checked_at: string;
  host_overview: {
    instance_status: string;
    cpu_usage_pct: number | null;
    memory_usage_pct: number | null;
    disk_usage_pct: number | null;
    network_traffic: string | null;
    disk_traffic: string | null;
    uptime: string | null;
  };
  docker_services: ServiceCheck[];
  resource_trends: { cpu: unknown[]; memory: unknown[]; disk_io: unknown[]; network_io: unknown[] };
  storage: { db_size: string | null; disk_remaining: string | null };
};

export function InfrastructurePage() {
  const { ingestion } = useOperationsPolling();
  const [infra, setInfra] = useState<InfraPayload | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const res = await fetch(`${import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'}/ops/infrastructure`);
        if (!res.ok) return;
        const payload = (await res.json()) as InfraPayload;
        if (alive) setInfra(payload);
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

  return (
    <div className="space-y-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Infrastructure</h1>
        <p className="text-xs text-text-secondary">Read-only stack infrastructure monitoring surface.</p>
      </div>

      <section className="grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-3 xl:grid-cols-7">
        {[
          ['Instance', host?.instance_status ?? 'not wired'],
          ['CPU usage', host?.cpu_usage_pct == null ? 'not wired' : `${host.cpu_usage_pct}%`],
          ['Memory usage', host?.memory_usage_pct == null ? 'not wired' : `${host.memory_usage_pct}%`],
          ['Disk usage', host?.disk_usage_pct == null ? 'not wired' : `${host.disk_usage_pct}%`],
          ['Network traffic', host?.network_traffic ?? 'not wired'],
          ['Disk traffic', host?.disk_traffic ?? 'not wired'],
          ['Uptime', host?.uptime ?? 'not wired'],
        ].map(([k, v]) => <div key={String(k)} className="rounded-md bg-surface-900 px-2.5 py-2 ring-1 ring-surface-700/60">{k}<div className="text-text-secondary">{v}</div></div>)}
      </section>

      <section className="rounded-lg bg-surface-900 p-3 ring-1 ring-surface-700/70">
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">Docker Services</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[11px]">
            <thead className="text-text-muted"><tr><th>service</th><th>status</th><th>uptime</th><th>restart</th><th>port</th><th>notes</th></tr></thead>
            <tbody>
              {serviceRows.map((s) => (
                <tr key={s.service} className="border-t border-surface-700/50"><td className="py-1.5 font-semibold uppercase">{s.service}</td><td>{s.status}</td><td>not wired</td><td>not wired</td><td>not wired</td><td className="text-text-secondary">{s.detail ?? (s.latency_ms != null ? `${s.latency_ms}ms` : 'not wired')}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-2 md:grid-cols-2">
        {['CPU %', 'Memory %', 'Disk write/read', 'Network in/out'].map((label) => (
          <div key={label} className="rounded-lg bg-surface-900 p-3 ring-1 ring-surface-700/70"><h3 className="mb-2 text-xs font-semibold text-text-muted">{label}</h3><div className="flex h-20 items-center justify-center rounded bg-surface-850 text-xs text-text-secondary">No trend data wired yet.</div></div>
        ))}
      </section>

      <section className="rounded-lg bg-surface-900 p-3 ring-1 ring-surface-700/70">
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">Storage / Data Growth</h2>
        <div className="grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-5">
          <div className="rounded bg-surface-850 p-2">DB candle rows<div className="text-text-secondary">{ingestion?.totalCandleCount ?? '—'}</div></div>
          <div className="rounded bg-surface-850 p-2">Latest candle<div className="text-text-secondary">{ingestion?.latestCandleTime ?? '—'}</div></div>
          <div className="rounded bg-surface-850 p-2">Freshness<div className="text-text-secondary">{freshness ?? '—'}s</div></div>
          <div className="rounded bg-surface-850 p-2">DB size<div className="text-text-secondary">{infra?.storage.db_size ?? 'not wired'}</div></div>
          <div className="rounded bg-surface-850 p-2">Disk remaining<div className="text-text-secondary">{infra?.storage.disk_remaining ?? 'not wired'}</div></div>
        </div>
      </section>

      <section className="rounded-lg bg-surface-900 p-3 ring-1 ring-surface-700/70">
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">VPS Readiness Checklist</h2>
        <ul className="grid grid-cols-1 gap-1 text-xs sm:grid-cols-2">
          {[
            ['Docker running', 'not wired'],
            ['Compose stack running', 'not wired'],
            ['DB healthy', serviceRows.find((s) => s.service === 'db')?.status ?? 'pending'],
            ['API reachable', serviceRows.find((s) => s.service === 'api')?.status ?? 'pending'],
            ['Ingestor active', serviceRows.find((s) => s.service === 'ingestor')?.status ?? 'pending'],
            ['Prometheus reachable', serviceRows.find((s) => s.service === 'prometheus')?.status ?? 'pending'],
            ['Grafana reachable', serviceRows.find((s) => s.service === 'grafana')?.status ?? 'pending'],
            ['cAdvisor reachable', serviceRows.find((s) => s.service === 'cadvisor')?.status ?? 'pending'],
            ['Tailscale expected', 'not wired'],
            ['Public ports restricted', 'not wired'],
          ].map(([k, v]) => <li key={String(k)} className="rounded bg-surface-850 px-2 py-1.5">{k}: <span className="text-text-secondary">{v}</span></li>)}
        </ul>
      </section>
    </div>
  );
}
