import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

const datasets = [
  { dataset: 'candles_1m', symbol: 'BTCUSDT', interval: '1m', rows: 145230, oldest: '2024-01-01', latest: '2026-05-08T00:00:00Z', freshness: '14s', quality: 'good' },
  { dataset: 'candles_5m', symbol: 'ETHUSDT', interval: '5m', rows: 38220, oldest: '2024-03-01', latest: '2026-05-08T00:00:00Z', freshness: '32s', quality: 'good' },
];

const features = [
  { feature: 'return_1m', latest: 0.0012, mean: 0.0004, z: 0.8, status: 'normal' },
  { feature: 'return_5m', latest: -0.0024, mean: 0.0002, z: -1.1, status: 'normal' },
  { feature: 'volatility_20', latest: 0.018, mean: 0.014, z: 1.6, status: 'watch' },
  { feature: 'volume_zscore', latest: 2.2, mean: 0.1, z: 2.2, status: 'elevated' },
  { feature: 'trend_strength', latest: 0.63, mean: 0.54, z: 0.9, status: 'normal' },
  { feature: 'drawdown', latest: -0.034, mean: -0.018, z: -1.5, status: 'watch' },
  { feature: 'regime_label', latest: 'trend', mean: '-', z: '-', status: 'derived' },
];

const runs = [
  { id: 'run_20260508_001', strategy: 'mean_reversion_v2', dataset: 'candles_1m', params: 'lookback=20,risk=0.8', sharpe: 1.42, dd: -4.1, win: 56.2, status: 'completed', created: '2026-05-08T00:10:00Z' },
  { id: 'run_20260508_002', strategy: 'momentum_breakout', dataset: 'candles_5m', params: 'breakout=2.0,stop=1.2', sharpe: 0.88, dd: -5.6, win: 49.8, status: 'completed', created: '2026-05-08T00:35:00Z' },
  { id: 'run_20260508_003', strategy: 'volatility_scalper', dataset: 'candles_1m', params: 'vol_window=20', sharpe: 0.0, dd: 0, win: 0, status: 'running', created: '2026-05-08T01:02:00Z' },
];

const dist = [{ b: '-2σ', v: 4 }, { b: '-1σ', v: 12 }, { b: '0σ', v: 22 }, { b: '+1σ', v: 10 }, { b: '+2σ', v: 3 }];
const regime = [{ t: '09', v: 0.3 }, { t: '10', v: 0.5 }, { t: '11', v: 0.45 }, { t: '12', v: 0.62 }, { t: '13', v: 0.58 }];
const equity = [{ t: '09', v: 10000 }, { t: '10', v: 10080 }, { t: '11', v: 10120 }, { t: '12', v: 10090 }, { t: '13', v: 10160 }];

export function ResearchPage() {
  return (
    <div className="space-y-3">
      <div><h1 className="text-xl font-semibold tracking-tight">Research Workspace</h1><p className="text-xs text-text-secondary">Read-only quantitative research and experiment monitoring.</p></div>

      <section className="grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-6">
        <div className="rounded-md bg-surface-900 p-2 ring-1 ring-surface-700/60">Datasets available<div className="text-text-secondary">{datasets.length}</div></div>
        <div className="rounded-md bg-surface-900 p-2 ring-1 ring-surface-700/60">Features tracked<div className="text-text-secondary">{features.length}</div></div>
        <div className="rounded-md bg-surface-900 p-2 ring-1 ring-surface-700/60">Backtest runs<div className="text-text-secondary">{runs.length}</div></div>
        <div className="rounded-md bg-surface-900 p-2 ring-1 ring-surface-700/60">Experiments today<div className="text-text-secondary">3</div></div>
        <div className="rounded-md bg-surface-900 p-2 ring-1 ring-surface-700/60">Best Sharpe<div className="text-text-secondary">1.42</div></div>
        <div className="rounded-md bg-surface-900 p-2 ring-1 ring-surface-700/60">Latest research run<div className="text-text-secondary">run_20260508_003</div></div>
      </section>

      <section className="rounded-lg bg-surface-900 p-3 ring-1 ring-surface-700/70 overflow-x-auto"><h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">Research Dataset Overview</h2><table className="w-full text-left text-[11px]"><thead className="text-text-muted"><tr><th>dataset</th><th>symbol</th><th>interval</th><th>row count</th><th>oldest</th><th>latest</th><th>freshness</th><th>quality</th></tr></thead><tbody>{datasets.map((d)=><tr key={d.dataset+d.symbol} className="border-t border-surface-700/50"><td className="py-1.5 font-semibold">{d.dataset}</td><td>{d.symbol}</td><td>{d.interval}</td><td>{d.rows}</td><td>{d.oldest}</td><td>{d.latest}</td><td>{d.freshness}</td><td>{d.quality}</td></tr>)}</tbody></table></section>

      <section className="rounded-lg bg-surface-900 p-3 ring-1 ring-surface-700/70 overflow-x-auto"><h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">Feature Monitor</h2><table className="w-full text-left text-[11px]"><thead className="text-text-muted"><tr><th>feature</th><th>latest value</th><th>rolling mean</th><th>z-score</th><th>status</th></tr></thead><tbody>{features.map((f)=><tr key={f.feature} className="border-t border-surface-700/50"><td className="py-1.5 font-semibold">{f.feature}</td><td>{String(f.latest)}</td><td>{String(f.mean)}</td><td>{String(f.z)}</td><td>{f.status}</td></tr>)}</tbody></table></section>

      <section className="rounded-lg bg-surface-900 p-3 ring-1 ring-surface-700/70 overflow-x-auto"><h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">Experiment Runs</h2><table className="w-full text-left text-[11px]"><thead className="text-text-muted"><tr><th>run id</th><th>strategy</th><th>dataset</th><th>parameters</th><th>Sharpe</th><th>max drawdown</th><th>win rate</th><th>status</th><th>created at</th></tr></thead><tbody>{runs.map((r)=><tr key={r.id} className="border-t border-surface-700/50"><td className="py-1.5 font-semibold">{r.id}</td><td>{r.strategy}</td><td>{r.dataset}</td><td>{r.params}</td><td>{r.sharpe}</td><td>{r.dd}%</td><td>{r.win}%</td><td>{r.status}</td><td>{r.created}</td></tr>)}</tbody></table></section>

      <section className="grid grid-cols-1 gap-2 md:grid-cols-2">
        <div className="rounded-lg bg-surface-900 p-3 ring-1 ring-surface-700/70"><h3 className="mb-2 text-xs text-text-muted">Return distribution</h3><div className="h-24"><ResponsiveContainer><BarChart data={dist}><CartesianGrid stroke="#252d3a" strokeOpacity={0.2} vertical={false}/><XAxis dataKey="b" hide/><YAxis hide/><Tooltip contentStyle={{background:'#12161d',border:'1px solid #252d3a'}}/><Bar dataKey="v" fill="#6f8fdc"/></BarChart></ResponsiveContainer></div></div>
        <div className="rounded-lg bg-surface-900 p-3 ring-1 ring-surface-700/70"><h3 className="mb-2 text-xs text-text-muted">Volatility regime trend</h3><div className="h-24"><ResponsiveContainer><LineChart data={regime}><CartesianGrid stroke="#252d3a" strokeOpacity={0.2} vertical={false}/><XAxis dataKey="t" hide/><YAxis hide/><Tooltip contentStyle={{background:'#12161d',border:'1px solid #252d3a'}}/><Line type="monotone" dataKey="v" stroke="#6f8fdc" dot={false} isAnimationActive={false}/></LineChart></ResponsiveContainer></div></div>
        <div className="rounded-lg bg-surface-900 p-3 ring-1 ring-surface-700/70"><h3 className="mb-2 text-xs text-text-muted">Feature correlation placeholder</h3><div className="flex h-24 items-center justify-center rounded bg-surface-850 text-xs text-text-secondary">Correlation heatmap integration pending.</div></div>
        <div className="rounded-lg bg-surface-900 p-3 ring-1 ring-surface-700/70"><h3 className="mb-2 text-xs text-text-muted">Backtest equity curve placeholder</h3><div className="h-24"><ResponsiveContainer><LineChart data={equity}><CartesianGrid stroke="#252d3a" strokeOpacity={0.2} vertical={false}/><XAxis dataKey="t" hide/><YAxis hide/><Tooltip contentStyle={{background:'#12161d',border:'1px solid #252d3a'}}/><Line type="monotone" dataKey="v" stroke="#ac9060" dot={false} isAnimationActive={false}/></LineChart></ResponsiveContainer></div></div>
      </section>

      <section className="rounded-lg bg-surface-900 p-3 ring-1 ring-surface-700/70"><h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">Research Notes</h2><ul className="space-y-1 text-xs text-text-secondary"><li className="rounded bg-surface-850 px-2 py-1.5">Current hypothesis: short-term volatility compression precedes breakout continuation.</li><li className="rounded bg-surface-850 px-2 py-1.5">Next experiment: regime-aware stop-loss scaling with volatility_20 buckets.</li><li className="rounded bg-surface-850 px-2 py-1.5">Data quality warning: sporadic volume_zscore spikes under high volatility windows.</li><li className="rounded bg-surface-850 px-2 py-1.5">Pending validation: cross-symbol robustness on ETHUSDT 5m dataset.</li></ul></section>
    </div>
  );
}
