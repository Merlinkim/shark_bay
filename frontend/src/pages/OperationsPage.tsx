import { useOperationsPolling } from '../hooks/useOperationsPolling';

type CheckState = 'ready' | 'pending' | 'not_wired';

function Badge({ state }: { state: CheckState }) {
  const styles = {
    ready: 'bg-accent-green/15 text-accent-green',
    pending: 'bg-accent-amber/15 text-accent-amber',
    not_wired: 'bg-surface-800 text-text-secondary',
  } as const;
  const label = { ready: 'ready', pending: 'pending', not_wired: 'not wired yet' } as const;
  return <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${styles[state]}`}>{label[state]}</span>;
}

function Checklist({ title, items }: { title: string; items: Array<{ label: string; state: CheckState }> }) {
  return (
    <section className="rounded-xl bg-surface-900 p-4 shadow-card ring-1 ring-surface-700/70">
      <h2 className="mb-3 text-sm font-semibold tracking-wide text-text-secondary">{title}</h2>
      <ul className="space-y-2">
        {items.map((item) => (
          <li key={item.label} className="flex items-center justify-between rounded-lg bg-surface-850 px-3 py-2 text-sm">
            <span>{item.label}</span>
            <Badge state={item.state} />
          </li>
        ))}
      </ul>
    </section>
  );
}

const RUNBOOK_COMMANDS = [
  'docker compose ps',
  'docker compose logs --tail=200 api',
  'docker compose logs --tail=200 ingestor',
  'curl http://localhost:8000/health',
  'curl http://localhost:8000/ingestion/status',
  'python -m app.data_quality --symbol BTCUSDT --interval 1m --lookback-hours 2',
];

export function OperationsPage() {
  const { health, ingestion, error } = useOperationsPolling();

  const services = [
    { name: 'api', state: error ? 'pending' : health?.status === 'OK' ? 'ready' : 'pending', detail: error ? 'request failure' : health?.status ?? 'pending' },
    { name: 'ingestor', state: ingestion?.collectorStatus === 'running' ? 'ready' : 'pending', detail: ingestion?.collectorStatus ?? 'pending' },
    { name: 'db', state: 'not_wired', detail: 'not wired yet' },
    { name: 'prometheus', state: 'not_wired', detail: 'not wired yet' },
    { name: 'grafana', state: 'not_wired', detail: 'not wired yet' },
    { name: 'research-ui', state: 'not_wired', detail: 'not wired yet' },
    { name: 'cadvisor', state: 'not_wired', detail: 'not wired yet' },
  ] as const;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Operations Readiness</h1>
        <p className="mt-1 text-sm text-text-secondary">Read-only control/readiness view for stack operations.</p>
      </div>

      <section className="rounded-xl bg-surface-900 p-4 shadow-card ring-1 ring-surface-700/70">
        <h2 className="mb-3 text-sm font-semibold tracking-wide text-text-secondary">Service Health</h2>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {services.map((service) => (
            <div key={service.name} className="rounded-lg bg-surface-850 px-3 py-2">
              <div className="mb-1 flex items-center justify-between">
                <span className="text-sm font-medium uppercase tracking-wide">{service.name}</span>
                <Badge state={service.state as CheckState} />
              </div>
              <p className="text-xs text-text-secondary">{service.detail}</p>
            </div>
          ))}
        </div>
      </section>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Checklist
          title="Deployment Readiness"
          items={[
            { label: 'Docker Compose config valid', state: 'pending' },
            { label: '.env present', state: 'pending' },
            { label: 'DB volume mounted', state: 'pending' },
            { label: 'Grafana reachable', state: 'not_wired' },
            { label: 'Prometheus reachable', state: 'not_wired' },
            { label: 'Ingestion status reachable', state: error ? 'pending' : 'ready' },
            { label: 'Data quality check available', state: 'ready' },
            { label: 'Rollback documented', state: 'ready' },
          ]}
        />

        <Checklist
          title="Reboot Recovery"
          items={[
            { label: 'DB restart policy enabled', state: 'pending' },
            { label: 'Ingestor restart policy enabled', state: 'pending' },
            { label: 'API restart policy enabled', state: 'pending' },
            { label: 'Compose stack recovery verified', state: 'pending' },
            { label: 'Latest reboot check', state: 'pending' },
          ]}
        />
      </div>

      <section className="rounded-xl bg-surface-900 p-4 shadow-card ring-1 ring-surface-700/70">
        <h2 className="mb-3 text-sm font-semibold tracking-wide text-text-secondary">Agent Debugging Runbook</h2>
        <div className="grid gap-2">
          {RUNBOOK_COMMANDS.map((command) => (
            <code key={command} className="block rounded-lg bg-surface-850 px-3 py-2 text-xs text-text-secondary">{command}</code>
          ))}
        </div>
      </section>

      <section className="rounded-xl bg-accent-amber/10 p-4 ring-1 ring-accent-amber/30">
        <h2 className="mb-2 text-sm font-semibold text-accent-amber">Safety Notices</h2>
        <ul className="list-disc space-y-1 pl-5 text-sm text-text-primary">
          <li>No database volume deletion from UI.</li>
          <li>No live trading controls.</li>
          <li>No agent self-healing yet.</li>
          <li>Human approval required for destructive actions.</li>
        </ul>
      </section>
    </div>
  );
}
