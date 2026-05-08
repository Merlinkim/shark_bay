import { useEffect, useMemo, useState } from 'react';
import { CheckCircle2, CircleDashed, Copy, Info, XCircle } from 'lucide-react';
import { useOperationsPolling } from '../hooks/useOperationsPolling';

type CheckState = 'ready' | 'pending' | 'not_wired' | 'error';
type Service = { name: string; state: CheckState; detail: string; endpoint: string; notes: string };

function StateIcon({ state }: { state: CheckState }) {
  if (state === 'ready') return <CheckCircle2 size={14} className="text-accent-green" />;
  if (state === 'error') return <XCircle size={14} className="text-accent-red" />;
  return <CircleDashed size={14} className="text-text-muted" />;
}

function Badge({ state }: { state: CheckState }) {
  const styles = {
    ready: 'bg-accent-green/15 text-accent-green',
    pending: 'bg-accent-amber/15 text-accent-amber',
    error: 'bg-accent-red/15 text-accent-red',
    not_wired: 'bg-surface-800 text-text-secondary',
  } as const;
  const label = { ready: 'ready', pending: 'pending', error: 'error', not_wired: 'not wired yet' } as const;
  return <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium transition-colors ${styles[state]}`}>{label[state]}</span>;
}

const RUNBOOK_GROUPS = {
  diagnostics: ['docker compose ps', 'curl http://localhost:8000/health', 'curl http://localhost:8000/ingestion/status'],
  logs: ['docker compose logs --tail=200 api', 'docker compose logs --tail=200 ingestor'],
  validation: ['python -m app.data_quality --symbol BTCUSDT --interval 1m --lookback-hours 2'],
  recovery: ['docker compose down && docker compose up --build -d'],
};

export function OperationsPage() {
  const { health, ingestion, error } = useOperationsPolling();
  const [now, setNow] = useState(new Date());
  const [sessionStart] = useState(Date.now());
  const [selected, setSelected] = useState<Service | null>(null);

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const uptimeSeconds = Math.floor((Date.now() - sessionStart) / 1000);

  const services: Service[] = useMemo(() => [
    { name: 'api', state: error ? 'error' : health?.status === 'OK' ? 'ready' : 'pending', detail: error ? 'request failure' : health?.status ?? 'pending', endpoint: '/health', notes: 'Primary control-plane API.' },
    { name: 'ingestor', state: ingestion?.collectorStatus === 'running' ? 'ready' : 'pending', detail: ingestion?.collectorStatus ?? 'pending', endpoint: '/ingestion/status', notes: 'Collector heartbeat-backed status.' },
    { name: 'db', state: 'not_wired', detail: 'not wired yet', endpoint: 'not wired', notes: 'DB telemetry to be integrated via API readiness metrics.' },
    { name: 'prometheus', state: 'not_wired', detail: 'not wired yet', endpoint: 'not wired', notes: 'Scrape target status integration planned.' },
    { name: 'grafana', state: 'not_wired', detail: 'not wired yet', endpoint: 'not wired', notes: 'Panel availability signal pending integration.' },
    { name: 'research-ui', state: 'not_wired', detail: 'not wired yet', endpoint: 'not wired', notes: 'UI heartbeat endpoint pending.' },
    { name: 'cadvisor', state: 'not_wired', detail: 'not wired yet', endpoint: 'not wired', notes: 'Container metric exporter health not wired.' },
  ], [health?.status, ingestion?.collectorStatus, error]);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Operations Readiness</h1>
        <p className="mt-1 text-sm text-text-secondary">Institutional read-only control/readiness surface.</p>
      </div>

      <section className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-3 xl:grid-cols-6">
        <div className="rounded-lg bg-surface-900 p-2 ring-1 ring-surface-700/60">Last health poll<div className="text-text-secondary">{now.toISOString()}</div></div>
        <div className="rounded-lg bg-surface-900 p-2 ring-1 ring-surface-700/60">Last ingestion update<div className="text-text-secondary">{ingestion?.latestCandleTime ?? '—'}</div></div>
        <div className="rounded-lg bg-surface-900 p-2 ring-1 ring-surface-700/60">Frontend uptime<div className="text-text-secondary">{uptimeSeconds}s</div></div>
        <div className="rounded-lg bg-surface-900 p-2 ring-1 ring-surface-700/60">Polling interval<div className="text-text-secondary">10s</div></div>
        <div className="rounded-lg bg-surface-900 p-2 ring-1 ring-surface-700/60">Environment<div className="text-text-secondary">LOCAL</div></div>
        <div className="rounded-lg bg-surface-900 p-2 ring-1 ring-surface-700/60">API latency<div className="text-text-secondary">not wired yet</div></div>
      </section>

      <section className="rounded-xl bg-surface-900 p-4 shadow-card ring-1 ring-surface-700/70">
        <h2 className="mb-3 text-sm font-semibold tracking-wide text-text-secondary">Service Health</h2>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {services.map((service) => (
            <button key={service.name} onClick={() => setSelected(service)} className="rounded-lg bg-surface-850 px-3 py-2 text-left transition-colors hover:bg-surface-800">
              <div className="mb-1 flex items-center justify-between">
                <span className="text-sm font-medium uppercase tracking-wide">{service.name}</span>
                <div className="flex items-center gap-2"><StateIcon state={service.state} /> <Badge state={service.state} /></div>
              </div>
              <p className={`text-xs ${service.state === 'ready' ? 'text-accent-green animate-pulse' : 'text-text-secondary'}`}>{service.detail}</p>
              {service.state === 'not_wired' && <p className="mt-1 flex items-center gap-1 text-[11px] text-text-muted"><Info size={11} /> Awaiting service telemetry wiring.</p>}
            </button>
          ))}
        </div>
      </section>

      <section className="rounded-xl bg-surface-900 p-4 shadow-card ring-1 ring-surface-700/70">
        <h2 className="mb-3 text-sm font-semibold tracking-wide text-text-secondary">Stack Topology</h2>
        <div className="flex flex-col items-start gap-2 text-sm text-text-secondary">
          <div className="rounded-md bg-surface-850 px-3 py-1.5">frontend</div>
          <div>↓</div>
          <div className="rounded-md bg-surface-850 px-3 py-1.5">api</div>
          <div>↓</div>
          <div className="rounded-md bg-surface-850 px-3 py-1.5">postgres</div>
          <div>↓</div>
          <div className="rounded-md bg-surface-850 px-3 py-1.5">prometheus / grafana</div>
        </div>
      </section>

      <section className="rounded-xl bg-surface-900 p-4 shadow-card ring-1 ring-surface-700/70">
        <h2 className="mb-3 text-sm font-semibold tracking-wide text-text-secondary">Agent Debugging Runbook</h2>
        <div className="grid gap-3 md:grid-cols-2">
          {Object.entries(RUNBOOK_GROUPS).map(([group, commands]) => (
            <div key={group} className="rounded-lg bg-surface-850 p-3">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">{group}</h3>
              <div className="space-y-2">
                {commands.map((command) => (
                  <div key={command} className="flex items-center justify-between rounded-md bg-surface-900 px-2 py-1.5">
                    <code className="text-xs text-text-secondary">{command}</code>
                    <button className="rounded p-1 hover:bg-surface-800" onClick={() => navigator.clipboard.writeText(command)}><Copy size={12} /></button>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {selected && (
        <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/50 p-4" onClick={() => setSelected(null)}>
          <div className="w-full max-w-lg rounded-xl bg-surface-900 p-4 ring-1 ring-surface-700" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between"><h3 className="text-lg font-semibold">{selected.name} details</h3><button onClick={() => setSelected(null)}><XCircle size={16} /></button></div>
            <div className="space-y-2 text-sm">
              <div className="flex items-center justify-between"><span>Status</span><Badge state={selected.state} /></div>
              <div className="flex items-center justify-between"><span>Last known check</span><span className="text-text-secondary">{now.toISOString()}</span></div>
              <div className="flex items-center justify-between"><span>Endpoint</span><span className="text-text-secondary">{selected.endpoint}</span></div>
              <div className="flex items-center justify-between"><span>Placeholder metrics</span><span className="text-text-secondary">not wired yet</span></div>
              <p className="rounded-lg bg-surface-850 p-2 text-xs text-text-secondary">Future integration: {selected.notes}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
