import { useEffect, useMemo, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { Bar, CartesianGrid, ComposedChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

interface Candle {
  symbol: string;
  open_time: string;
  close_time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

const RANGE_LIMIT: Record<'1h' | '6h' | '24h' | '7d', number> = {
  '1h': 60,
  '6h': 360,
  '24h': 1440,
  '7d': 10080,
};

export function LiveMarketChartPage() {
  const [range, setRange] = useState<keyof typeof RANGE_LIMIT>('1h');
  const [polling, setPolling] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [candles, setCandles] = useState<Candle[]>([]);
  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

  const fetchCandles = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${apiBaseUrl}/candles?symbol=BTCUSDT&interval=1m&limit=${RANGE_LIMIT[range]}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      const rows = (payload.candles ?? []) as Candle[];
      setCandles(rows.slice().reverse());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void fetchCandles(); }, [range]);
  useEffect(() => {
    if (!polling) return;
    const timer = setInterval(() => void fetchCandles(), 10_000);
    return () => clearInterval(timer);
  }, [polling, range]);

  const latest = candles.at(-1);
  const lagSeconds = latest ? Math.max(0, Math.floor((Date.now() - new Date(latest.open_time).getTime()) / 1000)) : null;

  const chartData = useMemo(
    () => candles.map((c) => ({
      time: new Date(c.open_time).toISOString().slice(11, 16),
      open: c.open,
      close: c.close,
      high: c.high,
      low: c.low,
      volume: c.volume,
      up: c.close >= c.open ? c.close : c.open,
      down: c.close >= c.open ? c.open : c.close,
      body: Math.abs(c.close - c.open),
      wick: c.high - c.low,
      direction: c.close >= c.open ? 'up' : 'down',
      wickMid: (c.high + c.low) / 2,
      bodyMid: (c.open + c.close) / 2,
    })),
    [candles],
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Live Market Chart</h1>
          <p className="text-sm text-text-secondary">Read-only BTCUSDT visual candle inspection.</p>
        </div>
        <div className="flex gap-2">
          {(['1h', '6h', '24h', '7d'] as const).map((r) => (
            <button key={r} onClick={() => setRange(r)} className={`rounded-lg px-3 py-1.5 text-xs ${range === r ? 'bg-surface-800 text-text-primary' : 'bg-surface-900 text-text-secondary ring-1 ring-surface-700/70'}`}>{r}</button>
          ))}
          <button onClick={() => void fetchCandles()} className="rounded-lg bg-surface-900 px-3 py-1.5 text-xs text-text-secondary ring-1 ring-surface-700/70"><RefreshCw size={12} /></button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-3 lg:grid-cols-6">
        <div className="rounded-lg bg-surface-900 p-2 ring-1 ring-surface-700/60">Symbol <div className="text-text-secondary">BTCUSDT</div></div>
        <div className="rounded-lg bg-surface-900 p-2 ring-1 ring-surface-700/60">Interval <div className="text-text-secondary">1m</div></div>
        <div className="rounded-lg bg-surface-900 p-2 ring-1 ring-surface-700/60">Latest Candle <div className="text-text-secondary">{latest?.open_time ?? '—'}</div></div>
        <div className="rounded-lg bg-surface-900 p-2 ring-1 ring-surface-700/60">Candle Count <div className="text-text-secondary">{candles.length}</div></div>
        <div className="rounded-lg bg-surface-900 p-2 ring-1 ring-surface-700/60">Lag Seconds <div className="text-text-secondary">{lagSeconds ?? '—'}</div></div>
        <label className="flex items-center justify-between rounded-lg bg-surface-900 p-2 ring-1 ring-surface-700/60">Polling 10s <input type="checkbox" checked={polling} onChange={(e) => setPolling(e.target.checked)} /></label>
      </div>

      <section className="rounded-xl bg-surface-900 p-4 shadow-card ring-1 ring-surface-700/70">
        {loading ? (
          <div className="h-[420px] animate-pulse rounded-lg bg-surface-850" />
        ) : error ? (
          <div className="flex h-[420px] items-center justify-center rounded-lg bg-accent-red/10 text-sm text-accent-red">Failed to load candles: {error}</div>
        ) : chartData.length === 0 ? (
          <div className="flex h-[420px] items-center justify-center rounded-lg bg-surface-850 text-sm text-text-muted">No candle data available for selected range.</div>
        ) : (
          <div className="space-y-2">
            <div className="h-[300px]">
              <ResponsiveContainer>
                <ComposedChart data={chartData} margin={{ top: 8, right: 8, left: -15, bottom: 0 }}>
                  <CartesianGrid stroke="#252d3a" strokeDasharray="2 4" vertical={false} />
                  <XAxis dataKey="time" stroke="#818b9b" tickLine={false} axisLine={false} minTickGap={24} />
                  <YAxis stroke="#818b9b" tickLine={false} axisLine={false} domain={['dataMin', 'dataMax']} width={42} />
                  <Tooltip />
                  <Bar dataKey="wick" fill="#94a3b8" barSize={2} />
                  <Bar dataKey="body" fill="#6f8fdc" barSize={6} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            <div className="h-[100px]">
              <ResponsiveContainer>
                <ComposedChart data={chartData}>
                  <CartesianGrid stroke="#252d3a" strokeDasharray="2 4" vertical={false} />
                  <XAxis dataKey="time" stroke="#818b9b" tickLine={false} axisLine={false} minTickGap={24} />
                  <YAxis stroke="#818b9b" tickLine={false} axisLine={false} width={42} />
                  <Bar dataKey="volume" fill="#4b5563" barSize={4} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
