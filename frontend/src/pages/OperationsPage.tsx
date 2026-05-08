import { useEffect, useMemo, useState } from 'react';
import { Copy, Info, XCircle } from 'lucide-react';
import { useOperationsPolling } from '../hooks/useOperationsPolling';

type CheckState = 'ready' | 'pending' | 'error' | 'timeout';
type Service = { name: string; state: CheckState; detail: string; endpoint: string; notes: string; latencyMs?: number | null };

function StatusDot({ state }: { state: CheckState }) {
  const cls = state === 'ready' ? 'bg-accent-green animate-pulse' : state === 'error' ? 'bg-accent-red' : state === 'timeout' ? 'bg-accent-amber' : 'bg-text-muted';
  return <span className={`inline-block h-2 w-2 rounded-full ${cls}`} />;
}
function Badge({ state }: { state: CheckState }) {
  const styles = { ready: 'bg-accent-green/15 text-accent-green', pending: 'bg-surface-800 text-text-secondary', error: 'bg-accent-red/15 text-accent-red', timeout: 'bg-accent-amber/15 text-accent-amber' } as const;
  return <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${styles[state]}`}>{state}</span>;
}

const RUNBOOK_GROUPS = {
  diagnostics: ['docker compose ps', 'curl http://localhost:8000/health', 'curl http://localhost:8000/ingestion/status'],
  logs: ['docker compose logs --tail=200 api', 'docker compose logs --tail=200 ingestor'],
  validation: ['python -m app.data_quality --symbol BTCUSDT --interval 1m --lookback-hours 2'],
  recovery: ['docker compose down && docker compose up --build -d'],
};

async function timedFetch(url: string, timeoutMs = 5000) {
  const start = performance.now();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: controller.signal });
    return { ok: res.ok, status: res.status, latencyMs: Math.round(performance.now() - start), timeout: false };
  } catch {
    return { ok: false, status: 0, latencyMs: Math.round(performance.now() - start), timeout: true };
  } finally {
    clearTimeout(timer);
  }
}

export function OperationsPage() {
  const { health, ingestion, error } = useOperationsPolling();
  const [now, setNow] = useState(new Date());
  const [sessionStart] = useState(Date.now());
  const [selected, setSelected] = useState<Service | null>(null);
  const [ext, setExt] = useState<Record<string, { state: CheckState; latencyMs: number | null; detail: string }>>({});

  useEffect(() => { const t = setInterval(() => setNow(new Date()), 1000); return () => clearInterval(t); }, []);

  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const res = await fetch(`${import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'}/ops/health`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const payload = await res.json();
        if (!alive) return;
        const next: Record<string, { state: CheckState; latencyMs: number | null; detail: string }> = {};
        for (const svc of payload.services ?? []) {
          const map: Record<string, CheckState> = {
            healthy: 'ready', degraded: 'pending', unreachable: 'error', timeout: 'timeout', not_configured: 'pending',
          };
          next[svc.service] = { state: map[svc.status] ?? 'pending', latencyMs: svc.latency_ms ?? null, detail: svc.detail ?? svc.status };
        }
        setExt(next);
      } catch {
        if (!alive) return;
        setExt((prev) => ({
          ...prev,
          prometheus: { state: 'error', latencyMs: null, detail: 'ops health unavailable' },
          grafana: { state: 'error', latencyMs: null, detail: 'ops health unavailable' },
          cadvisor: { state: 'error', latencyMs: null, detail: 'ops health unavailable' },
        }));
      }
    };
    void poll();
    const timer = setInterval(() => void poll(), 10_000);
    return () => { alive = false; clearInterval(timer); };
  }, []);

  const freshness = ingestion?.latestCandleTime ? Math.floor((Date.now() - new Date(ingestion.latestCandleTime).getTime()) / 1000) : null;

  const services: Service[] = useMemo(() => [
    { name: 'api', state: error ? 'error' : health?.status === 'OK' ? 'ready' : 'pending', detail: error ? 'request failure' : health?.status ?? 'pending', endpoint: '/health', notes: 'Primary control-plane API.', latencyMs: null },
    { name: 'ingestor', state: ingestion?.collectorStatus === 'running' ? 'ready' : 'pending', detail: ingestion?.collectorStatus ?? 'pending', endpoint: '/ingestion/status', notes: 'Collector heartbeat-backed status.', latencyMs: null },
    { name: 'db', state: ext.db?.state ?? 'pending', detail: ext.db?.detail ?? 'polling', endpoint: '/health/ready', notes: `latest candle: ${ingestion?.latestCandleTime ?? '—'}, rows: ${ingestion?.totalCandleCount ?? '—'}, freshness: ${freshness ?? '—'}s`, latencyMs: ext.db?.latencyMs ?? null },
    { name: 'prometheus', state: ext.prometheus?.state ?? 'pending', detail: ext.prometheus?.detail ?? 'polling', endpoint: 'http://localhost:9090/-/healthy', notes: 'Prometheus health endpoint check.', latencyMs: ext.prometheus?.latencyMs ?? null },
    { name: 'grafana', state: ext.grafana?.state ?? 'pending', detail: ext.grafana?.detail ?? 'polling', endpoint: 'http://localhost:3000/api/health', notes: 'Grafana API health endpoint check.', latencyMs: ext.grafana?.latencyMs ?? null },
    { name: 'research-ui', state: 'pending', detail: 'not polled', endpoint: 'n/a', notes: 'No health endpoint configured.', latencyMs: null },
    { name: 'cadvisor', state: ext.cadvisor?.state ?? 'pending', detail: ext.cadvisor?.detail ?? 'polling', endpoint: 'http://localhost:8080/metrics', notes: 'cAdvisor metrics endpoint check.', latencyMs: ext.cadvisor?.latencyMs ?? null },
  ], [health?.status, ingestion, error, ext, freshness]);

  const primary = [
    { name: 'API', state: services[0].state, meta: `latency: ${services[0].latencyMs ?? '—'}ms` },
    { name: 'INGESTOR', state: services[1].state, meta: `heartbeat: ${services[1].detail}` },
    { name: 'DB', state: services[2].state, meta: `latency: ${services[2].latencyMs ?? '—'}ms` },
    { name: 'MARKET FEED', state: services[1].state, meta: `freshness: ${freshness ?? '—'}s` },
  ];

  return (
    <div className="space-y-3">
      <div className="flex items-end justify-between"><div><h1 className="text-xl font-semibold tracking-tight">Operations Readiness</h1><p className="mt-0.5 text-xs text-text-secondary">Institutional operational command surface.</p></div><div className="text-xs text-text-secondary">UTC {now.toISOString().slice(11, 19)}</div></div>

      <section className="rounded-lg bg-surface-900 p-2.5 ring-1 ring-surface-700/70"><h2 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-text-muted">Primary System Status</h2><div className="grid grid-cols-2 gap-2 lg:grid-cols-4">{primary.map((p) => <div key={p.name} className="rounded-md bg-surface-850 px-2.5 py-2"><div className="flex items-center justify-between text-xs font-semibold"><span>{p.name}</span><StatusDot state={p.state} /></div><p className="mt-1 text-[10px] text-text-secondary">{p.meta}</p></div>)}</div></section>

      <section className="grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-3 xl:grid-cols-6">
        <div className="rounded-md bg-surface-900 px-2.5 py-2 ring-1 ring-surface-700/60">Last health poll<div className="text-text-secondary">{now.toISOString()}</div></div>
        <div className="rounded-md bg-surface-900 px-2.5 py-2 ring-1 ring-surface-700/60">Last ingestion update<div className="text-text-secondary">{ingestion?.latestCandleTime ?? '—'}</div></div>
        <div className="rounded-md bg-surface-900 px-2.5 py-2 ring-1 ring-surface-700/60">Frontend uptime<div className="text-text-secondary">{Math.floor((Date.now() - sessionStart) / 1000)}s</div></div>
        <div className="rounded-md bg-surface-900 px-2.5 py-2 ring-1 ring-surface-700/60">Polling interval<div className="text-text-secondary">10s</div></div>
        <div className="rounded-md bg-surface-900 px-2.5 py-2 ring-1 ring-surface-700/60">Environment<div className="text-text-secondary">LOCAL</div></div>
        <div className="rounded-md bg-surface-900 px-2.5 py-2 ring-1 ring-surface-700/60">API latency<div className="text-text-secondary">{services[0].latencyMs ?? '—'}ms</div></div>
      </section>

      <section className="rounded-lg bg-surface-900 p-3 shadow-card ring-1 ring-surface-700/70"><h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">Service Health</h2><div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">{services.map((service) => <button key={service.name} onClick={() => setSelected(service)} className="rounded-md bg-surface-850 px-2.5 py-1.5 text-left transition-all hover:bg-surface-800 hover:ring-1 hover:ring-surface-700"><div className="mb-0.5 flex items-center justify-between"><span className="text-[11px] font-semibold uppercase tracking-wide">{service.name}</span><div className="flex items-center gap-1.5"><StatusDot state={service.state} /><Badge state={service.state} /></div></div><p className="text-[10px] text-text-secondary">{service.detail}{service.latencyMs != null ? ` · ${service.latencyMs}ms` : ''}</p>{service.state === 'pending' && <p className="mt-0.5 flex items-center gap-1 text-[10px] text-text-muted"><Info size={10} /> waiting/stale telemetry</p>}</button>)}</div></section>

      <section className="rounded-lg bg-surface-900 p-3 shadow-card ring-1 ring-surface-700/70"><h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">Agent Debugging Runbook</h2><div className="grid gap-2 md:grid-cols-2">{Object.entries(RUNBOOK_GROUPS).map(([group, commands]) => <div key={group} className="rounded-md bg-surface-850 p-2"><h3 className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-text-muted">{group}</h3><div className="space-y-1.5">{commands.map((command) => <div key={command} className="flex items-center justify-between rounded bg-surface-900 px-2 py-1"><code className="text-[11px] text-text-secondary">{command}</code><button className="rounded p-1 hover:bg-surface-800" onClick={() => navigator.clipboard.writeText(command)}><Copy size={11} /></button></div>)}</div></div>)}</div></section>

      {selected && <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/50 p-3" onClick={() => setSelected(null)}><div className="w-full max-w-lg rounded-lg bg-surface-900 p-3 ring-1 ring-surface-700" onClick={(e) => e.stopPropagation()}><div className="mb-2 flex items-center justify-between"><h3 className="text-base font-semibold">{selected.name} details</h3><button onClick={() => setSelected(null)}><XCircle size={16} /></button></div><div className="space-y-1.5 text-xs"><div className="flex items-center justify-between"><span>Status</span><Badge state={selected.state} /></div><div className="flex items-center justify-between"><span>Last known check</span><span className="text-text-secondary">{now.toISOString()}</span></div><div className="flex items-center justify-between"><span>Endpoint</span><span className="text-text-secondary">{selected.endpoint}</span></div><div className="flex items-center justify-between"><span>Latency</span><span className="text-text-secondary">{selected.latencyMs ?? '—'}ms</span></div><p className="rounded bg-surface-850 p-2 text-[11px] text-text-secondary">{selected.notes}</p></div></div></div>}
    </div>
  );
}
