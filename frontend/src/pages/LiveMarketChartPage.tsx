import { useEffect, useMemo, useRef, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { ColorType, createChart, type IChartApi, type ISeriesApi, type Time } from 'lightweight-charts';

interface Candle {
  open_time: string;
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

  const priceRef = useRef<HTMLDivElement | null>(null);
  const volumeRef = useRef<HTMLDivElement | null>(null);
  const priceChartRef = useRef<IChartApi | null>(null);
  const volumeChartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);

  const fetchCandles = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${apiBaseUrl}/candles?symbol=BTCUSDT&interval=1m&limit=${RANGE_LIMIT[range]}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      setCandles(((payload.candles ?? []) as Candle[]).slice().reverse());
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

  const transformed = useMemo(() => candles.map((c) => ({
    time: Math.floor(new Date(c.open_time).getTime() / 1000) as Time,
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
    volume: c.volume,
  })), [candles]);

  useEffect(() => {
    if (!priceRef.current || !volumeRef.current) return;

    const commonOptions = {
      layout: { background: { type: ColorType.Solid, color: '#12161d' }, textColor: '#a9b2c1' },
      grid: { vertLines: { color: '#252d3a' }, horzLines: { color: '#252d3a' } },
      crosshair: { mode: 0 as const },
      rightPriceScale: { borderColor: '#252d3a' },
      timeScale: { borderColor: '#252d3a', timeVisible: true, secondsVisible: false },
    };

    const priceChart = createChart(priceRef.current, { ...commonOptions, width: priceRef.current.clientWidth, height: 320 });
    const volumeChart = createChart(volumeRef.current, { ...commonOptions, width: volumeRef.current.clientWidth, height: 120 });

    const candleSeries = priceChart.addCandlestickSeries({
      upColor: '#4f9b79',
      downColor: '#b97584',
      borderVisible: false,
      wickUpColor: '#4f9b79',
      wickDownColor: '#b97584',
    });

    const volumeSeries = volumeChart.addHistogramSeries({ color: '#6b7280', priceFormat: { type: 'volume' } });

    priceChartRef.current = priceChart;
    volumeChartRef.current = volumeChart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;

    const resize = () => {
      if (!priceRef.current || !volumeRef.current) return;
      priceChart.applyOptions({ width: priceRef.current.clientWidth });
      volumeChart.applyOptions({ width: volumeRef.current.clientWidth });
    };

    window.addEventListener('resize', resize);
    return () => {
      window.removeEventListener('resize', resize);
      priceChart.remove();
      volumeChart.remove();
    };
  }, []);

  useEffect(() => {
    if (!candleSeriesRef.current || !volumeSeriesRef.current) return;
    candleSeriesRef.current.setData(transformed);
    volumeSeriesRef.current.setData(transformed.map((c) => ({ time: c.time, value: c.volume, color: c.close >= c.open ? '#4f9b79aa' : '#b97584aa' })));
    priceChartRef.current?.timeScale().fitContent();
    volumeChartRef.current?.timeScale().fitContent();
  }, [transformed]);

  const latest = candles.at(-1);
  const lagSeconds = latest ? Math.max(0, Math.floor((Date.now() - new Date(latest.open_time).getTime()) / 1000)) : null;

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Live Market Chart</h1>
          <p className="text-sm text-text-secondary">Read-only BTCUSDT 1m candlestick inspection.</p>
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
        {loading ? <div className="h-[460px] animate-pulse rounded-lg bg-surface-850" /> : error ? (
          <div className="flex h-[460px] items-center justify-center rounded-lg bg-accent-red/10 text-sm text-accent-red">Failed to load candles: {error}</div>
        ) : candles.length === 0 ? (
          <div className="flex h-[460px] items-center justify-center rounded-lg bg-surface-850 text-sm text-text-muted">No candle data available for selected range.</div>
        ) : (
          <div className="space-y-2">
            <div ref={priceRef} className="h-[320px] w-full overflow-hidden rounded-lg" />
            <div ref={volumeRef} className="h-[120px] w-full overflow-hidden rounded-lg" />
          </div>
        )}
      </section>
    </div>
  );
}
