import { useEffect, useMemo, useState } from 'react';
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid, BarChart, Bar } from 'recharts';

type RiskStatus = 'ok' | 'warn' | 'breach';

type RiskCheck = {
  check: string;
  status: RiskStatus;
  threshold: string;
  current: string;
  action: string;
  lastChecked: string;
};

const baseChecks: RiskCheck[] = [
  { check: 'max daily loss', status: 'ok', threshold: '-2.0%', current: '-0.6%', action: 'pause strategy set', lastChecked: 'now' },
  { check: 'max drawdown', status: 'warn', threshold: '-5.0%', current: '-3.4%', action: 'raise risk alert', lastChecked: 'now' },
  { check: 'max position exposure', status: 'ok', threshold: '30%', current: '18%', action: 'trim new entries', lastChecked: 'now' },
  { check: 'max symbol concentration', status: 'ok', threshold: '40%', current: '26%', action: 'block symbol adds', lastChecked: 'now' },
  { check: 'stale market feed', status: 'ok', threshold: '<60s', current: '14s', action: 'freeze signal intake', lastChecked: 'now' },
  { check: 'excessive latency', status: 'warn', threshold: '<450ms', current: '390ms', action: 'degrade execution mode', lastChecked: 'now' },
  { check: 'strategy heartbeat stale', status: 'ok', threshold: '<45s', current: '21s', action: 'disable stale strategy', lastChecked: 'now' },
  { check: 'order rejection spike', status: 'ok', threshold: '<5/hr', current: '2/hr', action: 'throttle order path', lastChecked: 'now' },
  { check: 'duplicate signal protection', status: 'ok', threshold: '0 duplicates', current: '0', action: 'drop duplicate signal', lastChecked: 'now' },
  { check: 'live trading disabled', status: 'ok', threshold: 'enabled', current: 'enabled', action: 'hard block execution', lastChecked: 'now' },
];

const ddTrend = [{ t: '09', v: -0.4 }, { t: '10', v: -0.8 }, { t: '11', v: -1.2 }, { t: '12', v: -1.0 }, { t: '13', v: -1.4 }];
const exposureTrend = [{ t: '09', v: 12 }, { t: '10', v: 15 }, { t: '11', v: 21 }, { t: '12', v: 19 }, { t: '13', v: 22 }];
const latencyTrend = [{ t: '09', v: 280 }, { t: '10', v: 320 }, { t: '11', v: 360 }, { t: '12', v: 340 }, { t: '13', v: 390 }];
const rejectTrend = [{ t: '09', v: 1 }, { t: '10', v: 0 }, { t: '11', v: 1 }, { t: '12', v: 2 }, { t: '13', v: 1 }];

const statusColor = (s: RiskStatus) => ({ ok: 'text-accent-green', warn: 'text-accent-amber', breach: 'text-accent-red' }[s]);

export function RiskControlPage() {
  const [checks, setChecks] = useState(baseChecks);

  useEffect(() => {
    const timer = setInterval(() => {
      setChecks((prev) => prev.map((c) => ({ ...c, lastChecked: new Date().toISOString().slice(11, 19) })));
    }, 10_000);
    return () => clearInterval(timer);
  }, []);

  const summary = useMemo(() => ({
    riskMode: 'paper-only / live-disabled',
    killSwitch: 'armed (read-only)',
    maxDailyDd: '-2.0%',
    currentDd: '-1.4%',
    exposure: '22%',
    staleGuard: 'active',
    circuitBreaker: 'standby',
    latencyGuard: 'active',
  }), []);

  return (
    <div className="space-y-3">
      <div><h1 className="text-xl font-semibold tracking-tight">Risk Control</h1><p className="text-xs text-text-secondary">Read-only risk operations surface for paper/live-disabled runtime.</p></div>

      <section className="grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-4 xl:grid-cols-8">
        {[
          ['Risk mode', summary.riskMode], ['Kill switch', summary.killSwitch], ['Max daily drawdown', summary.maxDailyDd], ['Current drawdown', summary.currentDd],
          ['Total exposure', summary.exposure], ['Stale feed guard', summary.staleGuard], ['Circuit breaker', summary.circuitBreaker], ['Latency guard', summary.latencyGuard],
        ].map(([k, v]) => <div key={String(k)} className="rounded-md bg-surface-900 p-2 ring-1 ring-surface-700/60">{k}<div className="text-text-secondary">{v}</div></div>)}
      </section>

      <section className="rounded-lg bg-surface-900 p-3 ring-1 ring-surface-700/70 overflow-x-auto">
        <table className="w-full text-left text-[11px]"><thead className="text-text-muted"><tr><th>risk check</th><th>status</th><th>threshold</th><th>current value</th><th>action if breached</th><th>last checked</th></tr></thead><tbody>{checks.map((c)=> <tr key={c.check} className="border-t border-surface-700/50"><td className="py-1.5 font-semibold">{c.check}</td><td className={statusColor(c.status)}>{c.status}</td><td>{c.threshold}</td><td>{c.current}</td><td>{c.action}</td><td>{c.lastChecked}</td></tr>)}</tbody></table>
      </section>

      <section className="grid grid-cols-1 gap-2 md:grid-cols-2">
        {[['Drawdown trend', ddTrend, 'v'], ['Exposure trend', exposureTrend, 'v'], ['Latency guard trend', latencyTrend, 'v']].map(([title, data, key]) => (
          <div key={String(title)} className="rounded-lg bg-surface-900 p-3 ring-1 ring-surface-700/70"><h3 className="mb-2 text-xs text-text-muted">{title}</h3><div className="h-24"><ResponsiveContainer><LineChart data={data as {t:string;v:number}[]}><CartesianGrid stroke="#252d3a" strokeOpacity={0.2} vertical={false}/><XAxis dataKey="t" hide/><YAxis hide/><Tooltip contentStyle={{background:'#12161d',border:'1px solid #252d3a'}}/><Line type="monotone" dataKey={String(key)} stroke="#6f8fdc" dot={false} isAnimationActive={false}/></LineChart></ResponsiveContainer></div></div>
        ))}
        <div className="rounded-lg bg-surface-900 p-3 ring-1 ring-surface-700/70"><h3 className="mb-2 text-xs text-text-muted">Rejected order count (placeholder)</h3><div className="h-24"><ResponsiveContainer><BarChart data={rejectTrend}><CartesianGrid stroke="#252d3a" strokeOpacity={0.2} vertical={false}/><XAxis dataKey="t" hide/><YAxis hide/><Tooltip contentStyle={{background:'#12161d',border:'1px solid #252d3a'}}/><Bar dataKey="v" fill="#ac9060" /></BarChart></ResponsiveContainer></div></div>
      </section>
    </div>
  );
}
