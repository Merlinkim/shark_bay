import { useEffect, useMemo, useState } from 'react';
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid, Bar, BarChart } from 'recharts';

type StrategyStatus = 'running' | 'paused' | 'stale' | 'degraded' | 'crashed';

type StrategyRuntime = {
  strategy: string;
  mode: 'paper' | 'live-disabled';
  status: StrategyStatus;
  heartbeatAgeSec: number;
  symbol: string;
  timeframe: string;
  lastSignal: 'buy' | 'sell' | 'hold';
  pnlPct: number;
  tradesToday: number;
  latencyMs: number;
  stale: boolean;
};

const seedData: StrategyRuntime[] = [
  { strategy: 'mean_reversion_v2', mode: 'paper', status: 'running', heartbeatAgeSec: 6, symbol: 'BTCUSDT', timeframe: '1m', lastSignal: 'hold', pnlPct: 1.84, tradesToday: 12, latencyMs: 82, stale: false },
  { strategy: 'momentum_breakout', mode: 'paper', status: 'degraded', heartbeatAgeSec: 14, symbol: 'ETHUSDT', timeframe: '5m', lastSignal: 'buy', pnlPct: -0.42, tradesToday: 8, latencyMs: 210, stale: false },
  { strategy: 'volatility_scalper', mode: 'live-disabled', status: 'stale', heartbeatAgeSec: 96, symbol: 'BTCUSDT', timeframe: '1m', lastSignal: 'sell', pnlPct: 0.31, tradesToday: 3, latencyMs: 165, stale: true },
];

const pnlSeries = [
  { t: '09:00', pnl: 0.2 }, { t: '10:00', pnl: 0.6 }, { t: '11:00', pnl: 0.9 }, { t: '12:00', pnl: 1.1 }, { t: '13:00', pnl: 1.73 },
];
const signalsSeries = [
  { t: '09', count: 5 }, { t: '10', count: 7 }, { t: '11', count: 4 }, { t: '12', count: 6 }, { t: '13', count: 8 },
];
const latencySeries = [
  { t: '09:00', latency: 120 }, { t: '10:00', latency: 105 }, { t: '11:00', latency: 140 }, { t: '12:00', latency: 98 }, { t: '13:00', latency: 130 },
];

const statusColor = (s: StrategyStatus) => ({ running: 'text-accent-green', paused: 'text-text-secondary', stale: 'text-accent-amber', degraded: 'text-accent-amber', crashed: 'text-accent-red' }[s]);

export function StrategiesPage() {
  const [rows, setRows] = useState<StrategyRuntime[]>(seedData);

  useEffect(() => {
    const timer = setInterval(() => {
      setRows((prev) => prev.map((r) => ({ ...r, heartbeatAgeSec: r.status === 'running' ? Math.max(2, r.heartbeatAgeSec - 1) : r.heartbeatAgeSec + 1, stale: r.heartbeatAgeSec > 60 })));
    }, 10_000);
    return () => clearInterval(timer);
  }, []);

  const summary = useMemo(() => {
    const active = rows.filter((r) => r.status === 'running').length;
    const stale = rows.filter((r) => r.stale || r.status === 'stale').length;
    const totalPnl = rows.reduce((n, r) => n + r.pnlPct, 0);
    const signals = rows.filter((r) => r.lastSignal !== 'hold').length;
    const avgLatency = rows.reduce((n, r) => n + r.latencyMs, 0) / rows.length;
    return { active, stale, totalPnl, signals, avgLatency };
  }, [rows]);

  return (
    <div className="space-y-3">
      <div><h1 className="text-xl font-semibold tracking-tight">Strategy Runtime</h1><p className="text-xs text-text-secondary">Read-only paper strategy runtime monitoring.</p></div>

      <section className="grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-5">
        <div className="rounded-md bg-surface-900 p-2 ring-1 ring-surface-700/60">Active strategies<div className="text-text-secondary">{summary.active}</div></div>
        <div className="rounded-md bg-surface-900 p-2 ring-1 ring-surface-700/60">Stale strategies<div className="text-text-secondary">{summary.stale}</div></div>
        <div className="rounded-md bg-surface-900 p-2 ring-1 ring-surface-700/60">Total paper PnL<div className="text-text-secondary">{summary.totalPnl.toFixed(2)}%</div></div>
        <div className="rounded-md bg-surface-900 p-2 ring-1 ring-surface-700/60">Signals today<div className="text-text-secondary">{summary.signals}</div></div>
        <div className="rounded-md bg-surface-900 p-2 ring-1 ring-surface-700/60">Avg latency<div className="text-text-secondary">{summary.avgLatency.toFixed(0)}ms</div></div>
      </section>

      <section className="rounded-lg bg-surface-900 p-3 ring-1 ring-surface-700/70 overflow-x-auto">
        <table className="w-full text-left text-[11px]">
          <thead className="text-text-muted"><tr><th>strategy</th><th>mode</th><th>status</th><th>heartbeat age</th><th>symbol</th><th>timeframe</th><th>last signal</th><th>pnl %</th><th>trades today</th><th>latency ms</th><th>stale</th></tr></thead>
          <tbody>
            {rows.map((r) => <tr key={r.strategy} className="border-t border-surface-700/50"><td className="py-1.5 font-semibold">{r.strategy}</td><td>{r.mode}</td><td className={statusColor(r.status)}>{r.status}</td><td>{r.heartbeatAgeSec}s</td><td>{r.symbol}</td><td>{r.timeframe}</td><td>{r.lastSignal}</td><td>{r.pnlPct.toFixed(2)}%</td><td>{r.tradesToday}</td><td>{r.latencyMs}</td><td>{r.stale ? 'yes' : 'no'}</td></tr>)}
          </tbody>
        </table>
      </section>

      <section className="grid grid-cols-1 gap-2 md:grid-cols-3">
        <div className="rounded-lg bg-surface-900 p-3 ring-1 ring-surface-700/70"><h3 className="mb-2 text-xs text-text-muted">PnL trend</h3><div className="h-24"><ResponsiveContainer><LineChart data={pnlSeries}><CartesianGrid stroke="#252d3a" strokeOpacity={0.2} vertical={false}/><XAxis dataKey="t" hide/><YAxis hide/><Tooltip contentStyle={{background:'#12161d',border:'1px solid #252d3a'}}/><Line type="monotone" dataKey="pnl" stroke="#6f8fdc" dot={false} isAnimationActive={false}/></LineChart></ResponsiveContainer></div></div>
        <div className="rounded-lg bg-surface-900 p-3 ring-1 ring-surface-700/70"><h3 className="mb-2 text-xs text-text-muted">Signals/hour</h3><div className="h-24"><ResponsiveContainer><BarChart data={signalsSeries}><CartesianGrid stroke="#252d3a" strokeOpacity={0.2} vertical={false}/><XAxis dataKey="t" hide/><YAxis hide/><Tooltip contentStyle={{background:'#12161d',border:'1px solid #252d3a'}}/><Bar dataKey="count" fill="#6f8fdc" /></BarChart></ResponsiveContainer></div></div>
        <div className="rounded-lg bg-surface-900 p-3 ring-1 ring-surface-700/70"><h3 className="mb-2 text-xs text-text-muted">Execution latency trend</h3><div className="h-24"><ResponsiveContainer><LineChart data={latencySeries}><CartesianGrid stroke="#252d3a" strokeOpacity={0.2} vertical={false}/><XAxis dataKey="t" hide/><YAxis hide/><Tooltip contentStyle={{background:'#12161d',border:'1px solid #252d3a'}}/><Line type="monotone" dataKey="latency" stroke="#ac9060" dot={false} isAnimationActive={false}/></LineChart></ResponsiveContainer></div></div>
      </section>
    </div>
  );
}
