import { useEffect, useMemo, useState } from 'react';
import { Copy, Info, XCircle } from 'lucide-react';
import { useOperationsPolling } from '../hooks/useOperationsPolling';

type CheckState = 'ready' | 'pending' | 'not_wired' | 'error';
type Service = { name: string; state: CheckState; detail: string; endpoint: string; notes: string };

function StatusDot({ state }: { state: CheckState }) {
  const cls = state === 'ready' ? 'bg-accent-green animate-pulse' : state === 'error' ? 'bg-accent-red' : 'bg-text-muted';
  return <span className={`inline-block h-2 w-2 rounded-full ${cls}`} />;
}

function Badge({ state }: { state: CheckState }) {
  const styles = { ready: 'bg-accent-green/15 text-accent-green', pending: 'bg-accent-amber/15 text-accent-amber', error: 'bg-accent-red/15 text-accent-red', not_wired: 'bg-surface-800 text-text-secondary' } as const;
  const label = { ready: 'ready', pending: 'pending', error: 'error', not_wired: 'not wired yet' } as const;
  return <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${styles[state]}`}>{label[state]}</span>;
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

  useEffect(() => { const t = setInterval(() => setNow(new Date()), 1000); return () => clearInterval(t); }, []);

  const services: Service[] = useMemo(() => [
    { name: 'api', state: error ? 'error' : health?.status === 'OK' ? 'ready' : 'pending', detail: error ? 'request failure' : health?.status ?? 'pending', endpoint: '/health', notes: 'Primary control-plane API.' },
    { name: 'ingestor', state: ingestion?.collectorStatus === 'running' ? 'ready' : 'pending', detail: ingestion?.collectorStatus ?? 'pending', endpoint: '/ingestion/status', notes: 'Collector heartbeat-backed status.' },
    { name: 'db', state: 'not_wired', detail: 'not wired yet', endpoint: 'not wired', notes: 'DB telemetry integration pending.' },
    { name: 'prometheus', state: 'not_wired', detail: 'not wired yet', endpoint: 'not wired', notes: 'Observability scrape status integration pending.' },
    { name: 'grafana', state: 'not_wired', detail: 'not wired yet', endpoint: 'not wired', notes: 'Dashboard availability signal pending.' },
    { name: 'research-ui', state: 'not_wired', detail: 'not wired yet', endpoint: 'not wired', notes: 'UI heartbeat endpoint pending.' },
    { name: 'cadvisor', state: 'not_wired', detail: 'not wired yet', endpoint: 'not wired', notes: 'Container exporter health not wired.' },
  ], [health?.status, ingestion?.collectorStatus, error]);

  const primary = [
    { name: 'API', state: services[0].state, meta: 'latency: not wired' },
    { name: 'INGESTOR', state: services[1].state, meta: `heartbeat: ${services[1].detail}` },
    { name: 'DB', state: services[2].state, meta: 'health: not wired' },
    { name: 'MARKET FEED', state: services[1].state, meta: `latest: ${ingestion?.latestCandleTime ?? '—'}` },
  ];

  return (
    <div className="space-y-3">
      <div className="flex items-end justify-between">
        <div><h1 className="text-xl font-semibold tracking-tight">Operations Readiness</h1><p className="mt-0.5 text-xs text-text-secondary">Institutional operational command surface.</p></div>
        <div className="text-xs text-text-secondary">UTC {now.toISOString().slice(11, 19)}</div>
      </div>

      <section className="rounded-lg bg-surface-900 p-2.5 ring-1 ring-surface-700/70">
        <h2 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-text-muted">Primary System Status</h2>
        <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
          {primary.map((p) => (
            <div key={p.name} className="rounded-md bg-surface-850 px-2.5 py-2">
              <div className="flex items-center justify-between text-xs font-semibold"><span>{p.name}</span><StatusDot state={p.state} /></div>
              <p className="mt-1 text-[10px] text-text-secondary">{p.meta}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-3 xl:grid-cols-6">
        <div className="rounded-md bg-surface-900 px-2.5 py-2 ring-1 ring-surface-700/60">Last health poll<div className="text-text-secondary transition-opacity">{now.toISOString()}</div></div>
        <div className="rounded-md bg-surface-900 px-2.5 py-2 ring-1 ring-surface-700/60">Last ingestion update<div className="text-text-secondary">{ingestion?.latestCandleTime ?? '—'}</div></div>
        <div className="rounded-md bg-surface-900 px-2.5 py-2 ring-1 ring-surface-700/60">Frontend uptime<div className="text-text-secondary">{Math.floor((Date.now() - sessionStart) / 1000)}s</div></div>
        <div className="rounded-md bg-surface-900 px-2.5 py-2 ring-1 ring-surface-700/60">Polling interval<div className="text-text-secondary">10s</div></div>
        <div className="rounded-md bg-surface-900 px-2.5 py-2 ring-1 ring-surface-700/60">Environment<div className="text-text-secondary">LOCAL</div></div>
        <div className="rounded-md bg-surface-900 px-2.5 py-2 ring-1 ring-surface-700/60">API latency<div className="text-text-secondary">not wired yet</div></div>
      </section>

      <section className="rounded-lg bg-surface-900 p-3 shadow-card ring-1 ring-surface-700/70">
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">Service Health</h2>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {services.map((service) => (
            <button key={service.name} onClick={() => setSelected(service)} className="rounded-md bg-surface-850 px-2.5 py-1.5 text-left transition-all hover:bg-surface-800 hover:ring-1 hover:ring-surface-700">
              <div className="mb-0.5 flex items-center justify-between"><span className="text-[11px] font-semibold uppercase tracking-wide">{service.name}</span><div className="flex items-center gap-1.5"><StatusDot state={service.state} /><Badge state={service.state} /></div></div>
              <p className="text-[10px] text-text-secondary">{service.detail}</p>
              {service.state === 'not_wired' && <p className="mt-0.5 flex items-center gap-1 text-[10px] text-text-muted"><Info size={10} /> telemetry pending</p>}
            </button>
          ))}
        </div>
      </section>

      <div className="grid gap-3 xl:grid-cols-2">
        <section className="rounded-lg bg-surface-900 p-3 shadow-card ring-1 ring-surface-700/70">
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">Stack Topology</h2>
          <div className="relative flex flex-wrap items-center justify-center gap-2 text-xs">
            <div className="rounded-md bg-surface-850 px-3 py-1.5 ring-1 ring-surface-700/60">frontend <StatusDot state="ready" /></div>
            <div className="h-px w-5 bg-surface-700" />
            <div className="rounded-md bg-surface-850 px-3 py-1.5 ring-1 ring-surface-700/60">api <StatusDot state={services[0].state} /></div>
            <div className="h-px w-5 bg-surface-700" />
            <div className="rounded-md bg-surface-850 px-3 py-1.5 ring-1 ring-surface-700/60">db <StatusDot state={services[2].state} /></div>
            <div className="w-full text-center text-text-muted">↘</div>
            <div className="rounded-md bg-surface-850 px-3 py-1.5 ring-1 ring-surface-700/60">observability <StatusDot state="not_wired" /></div>
          </div>
        </section>

        <section className="rounded-lg bg-surface-900 p-3 shadow-card ring-1 ring-surface-700/70">
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">System Notes</h2>
          <ul className="space-y-1.5 text-[11px] text-text-secondary">
            <li>Last reboot: not wired yet.</li>
            <li>Backfill status: {ingestion?.lastBackfillStatus ?? 'not wired yet'}.</li>
            <li>Known gaps: not wired yet.</li>
            <li>Pending integrations: db/prometheus/grafana telemetry.</li>
            <li>Latest validation summary: data quality CLI available.</li>
          </ul>
        </section>
      </div>

      <section className="rounded-lg bg-surface-900 p-3 shadow-card ring-1 ring-surface-700/70">
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">Agent Debugging Runbook</h2>
        <div className="grid gap-2 md:grid-cols-2">
          {Object.entries(RUNBOOK_GROUPS).map(([group, commands]) => (
            <div key={group} className="rounded-md bg-surface-850 p-2">
              <h3 className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-text-muted">{group}</h3>
              <div className="space-y-1.5">
                {commands.map((command) => (
                  <div key={command} className="flex items-center justify-between rounded bg-surface-900 px-2 py-1">
                    <code className="text-[11px] text-text-secondary">{command}</code>
                    <button className="rounded p-1 hover:bg-surface-800" onClick={() => navigator.clipboard.writeText(command)}><Copy size={11} /></button>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {selected && (
        <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/50 p-3" onClick={() => setSelected(null)}>
          <div className="w-full max-w-lg rounded-lg bg-surface-900 p-3 ring-1 ring-surface-700" onClick={(e) => e.stopPropagation()}>
            <div className="mb-2 flex items-center justify-between"><h3 className="text-base font-semibold">{selected.name} details</h3><button onClick={() => setSelected(null)}><XCircle size={16} /></button></div>
            <div className="space-y-1.5 text-xs">
              <div className="flex items-center justify-between"><span>Status</span><Badge state={selected.state} /></div>
              <div className="flex items-center justify-between"><span>Last known check</span><span className="text-text-secondary">{now.toISOString()}</span></div>
              <div className="flex items-center justify-between"><span>Endpoint</span><span className="text-text-secondary">{selected.endpoint}</span></div>
              <div className="flex items-center justify-between"><span>Placeholder metrics</span><span className="text-text-secondary">not wired yet</span></div>
              <p className="rounded bg-surface-850 p-2 text-[11px] text-text-secondary">Future integration: {selected.notes}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
