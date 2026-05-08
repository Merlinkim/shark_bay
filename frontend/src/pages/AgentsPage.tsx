import { useEffect, useMemo, useState } from 'react';
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid } from 'recharts';

type AgentStatus = 'idle' | 'reasoning' | 'waiting' | 'degraded' | 'stalled' | 'offline';

type AgentRuntime = {
  name: string;
  role: string;
  model: string;
  status: AgentStatus;
  activeTask: string;
  queueDepth: number;
  lastAction: string;
  latencyMs: number;
  tokenUsage: number;
  retryCount: number;
  heartbeatAgeSec: number;
};

const seed: AgentRuntime[] = [
  { name: 'alpha-researcher', role: 'strategy eval', model: 'gpt-4.1-mini', status: 'reasoning', activeTask: 'Evaluate mean_reversion_v2', queueDepth: 2, lastAction: 'strategy evaluation completed', latencyMs: 780, tokenUsage: 14500, retryCount: 0, heartbeatAgeSec: 6 },
  { name: 'risk-sentinel', role: 'risk validation', model: 'gpt-4.1-nano', status: 'idle', activeTask: 'Awaiting signal batch', queueDepth: 0, lastAction: 'signal validation passed', latencyMs: 320, tokenUsage: 5200, retryCount: 1, heartbeatAgeSec: 18 },
  { name: 'market-observer', role: 'anomaly detection', model: 'gpt-4.1-mini', status: 'degraded', activeTask: 'Detect volatility anomaly', queueDepth: 5, lastAction: 'market anomaly detected', latencyMs: 1420, tokenUsage: 10200, retryCount: 2, heartbeatAgeSec: 35 },
];

const throughput = [{ t: '09', v: 8 }, { t: '10', v: 11 }, { t: '11', v: 9 }, { t: '12', v: 14 }, { t: '13', v: 12 }];
const tokenTrend = [{ t: '09', v: 12 }, { t: '10', v: 14 }, { t: '11', v: 11 }, { t: '12', v: 17 }, { t: '13', v: 15 }];
const latencyTrend = [{ t: '09', v: 610 }, { t: '10', v: 700 }, { t: '11', v: 650 }, { t: '12', v: 780 }, { t: '13', v: 690 }];
const events = ['strategy evaluation completed', 'market anomaly detected', 'signal validation passed', 'retry triggered', 'stale feed ignored'];

const statusColor = (s: AgentStatus) => ({ idle: 'text-text-secondary', reasoning: 'text-accent-green', waiting: 'text-accent-amber', degraded: 'text-accent-amber', stalled: 'text-accent-red', offline: 'text-accent-red' }[s]);

export function AgentsPage() {
  const [rows, setRows] = useState(seed);
  const [uptimeSec, setUptimeSec] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setUptimeSec((v) => v + 10);
      setRows((prev) => prev.map((r) => ({ ...r, heartbeatAgeSec: Math.max(1, r.status === 'reasoning' ? r.heartbeatAgeSec - 1 : r.heartbeatAgeSec + 1) })));
    }, 10_000);
    return () => clearInterval(timer);
  }, []);

  const summary = useMemo(() => {
    const active = rows.filter((r) => r.status === 'reasoning' || r.status === 'waiting').length;
    const queued = rows.reduce((n, r) => n + r.queueDepth, 0);
    const failed = rows.reduce((n, r) => n + r.retryCount, 0);
    const avgLatency = rows.reduce((n, r) => n + r.latencyMs, 0) / rows.length;
    const tokenThroughput = rows.reduce((n, r) => n + r.tokenUsage, 0);
    return { active, queued, failed, avgLatency, tokenThroughput };
  }, [rows]);

  return (
    <div className="space-y-3">
      <div><h1 className="text-xl font-semibold tracking-tight">Agent Orchestration Runtime</h1><p className="text-xs text-text-secondary">Read-only AI orchestration monitoring surface.</p></div>

      <section className="grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-6">
        <div className="rounded-md bg-surface-900 p-2 ring-1 ring-surface-700/60">Active agents<div className="text-text-secondary">{summary.active}</div></div>
        <div className="rounded-md bg-surface-900 p-2 ring-1 ring-surface-700/60">Queued tasks<div className="text-text-secondary">{summary.queued}</div></div>
        <div className="rounded-md bg-surface-900 p-2 ring-1 ring-surface-700/60">Failed tasks<div className="text-text-secondary">{summary.failed}</div></div>
        <div className="rounded-md bg-surface-900 p-2 ring-1 ring-surface-700/60">Avg reasoning latency<div className="text-text-secondary">{summary.avgLatency.toFixed(0)}ms</div></div>
        <div className="rounded-md bg-surface-900 p-2 ring-1 ring-surface-700/60">Token throughput<div className="text-text-secondary">{summary.tokenThroughput}</div></div>
        <div className="rounded-md bg-surface-900 p-2 ring-1 ring-surface-700/60">Orchestration uptime<div className="text-text-secondary">{uptimeSec}s</div></div>
      </section>

      <section className="rounded-lg bg-surface-900 p-3 ring-1 ring-surface-700/70 overflow-x-auto">
        <table className="w-full text-left text-[11px]"><thead className="text-text-muted"><tr><th>agent name</th><th>role</th><th>model</th><th>status</th><th>active task</th><th>queue depth</th><th>last action</th><th>latency</th><th>token usage</th><th>retry</th><th>heartbeat age</th></tr></thead><tbody>{rows.map((r)=><tr key={r.name} className="border-t border-surface-700/50"><td className="py-1.5 font-semibold">{r.name}</td><td>{r.role}</td><td>{r.model}</td><td className={statusColor(r.status)}>{r.status}</td><td>{r.activeTask}</td><td>{r.queueDepth}</td><td>{r.lastAction}</td><td>{r.latencyMs}ms</td><td>{r.tokenUsage}</td><td>{r.retryCount}</td><td>{r.heartbeatAgeSec}s</td></tr>)}</tbody></table>
      </section>

      <section className="grid grid-cols-1 gap-2 md:grid-cols-3">
        {([
          { title: 'Task throughput trend', data: throughput },
          { title: 'Token usage trend', data: tokenTrend },
          { title: 'Orchestration latency trend', data: latencyTrend },
        ] as Array<{ title: string; data: { t: string; v: number }[] }>).map(({ title, data }) => (
          <div key={String(title)} className="rounded-lg bg-surface-900 p-3 ring-1 ring-surface-700/70"><h3 className="mb-2 text-xs text-text-muted">{title}</h3><div className="h-24"><ResponsiveContainer><LineChart data={data as {t:string;v:number}[]}><CartesianGrid stroke="#252d3a" strokeOpacity={0.2} vertical={false}/><XAxis dataKey="t" hide/><YAxis hide/><Tooltip contentStyle={{background:'#12161d',border:'1px solid #252d3a'}}/><Line type="monotone" dataKey="v" stroke="#6f8fdc" dot={false} isAnimationActive={false}/></LineChart></ResponsiveContainer></div></div>
        ))}
      </section>

      <section className="rounded-lg bg-surface-900 p-3 ring-1 ring-surface-700/70"><h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">Recent Agent Events</h2><ul className="space-y-1 text-xs text-text-secondary">{events.map((e)=><li key={e} className="rounded bg-surface-850 px-2 py-1.5">{e}</li>)}</ul></section>
    </div>
  );
}
