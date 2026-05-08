import { useEffect, useMemo, useRef, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { CandlestickSeries, ColorType, createChart, HistogramSeries, type IChartApi, type ISeriesApi, type UTCTimestamp } from 'lightweight-charts';

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

function mergeCandles(prev: Candle[], incoming: Candle[]): Candle[] {
  const byTime = new Map(prev.map((c) => [c.open_time, c]));
  for (const candle of incoming) {
    byTime.set(candle.open_time, candle);
  }
  return Array.from(byTime.values()).sort((a, b) => new Date(a.open_time).getTime() - new Date(b.open_time).getTime());
}

export function LiveMarketChartPage() {
  const [range, setRange] = useState<keyof typeof RANGE_LIMIT>('1h');
  const [polling, setPolling] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<string | null>(null);
  const [refreshStatus, setRefreshStatus] = useState<'Live' | 'Paused' | 'Error'>('Paused');
  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

  const priceRef = useRef<HTMLDivElement | null>(null);
  const volumeRef = useRef<HTMLDivElement | null>(null);
  const priceChartRef = useRef<IChartApi | null>(null);
  const volumeChartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);

  const fetchCandles = async (isIncremental = false) => {
    if (!isIncremental) setLoading(true);
    try {
      const response = await fetch(`${apiBaseUrl}/candles?symbol=BTCUSDT&interval=1m&limit=${RANGE_LIMIT[range]}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      const incoming = ((payload.candles ?? []) as Candle[])
        .map((c) => ({ ...c, open: Number(c.open), high: Number(c.high), low: Number(c.low), close: Number(c.close), volume: Number(c.volume) }))
        .slice()
        .reverse();

      setCandles((prev) => (isIncremental ? mergeCandles(prev, incoming) : incoming));
      setError(null);
      setLastRefreshedAt(new Date().toISOString());
      setRefreshStatus(polling ? 'Live' : 'Paused');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      setRefreshStatus('Error');
    } finally {
      if (!isIncremental) setLoading(false);
    }
  };

  useEffect(() => {
    void fetchCandles(false);
  }, [range]);

  useEffect(() => {
    if (!polling) {
      setRefreshStatus(error ? 'Error' : 'Paused');
      return;
    }
    setRefreshStatus('Live');
    const timer = setInterval(() => void fetchCandles(true), 10_000);
    return () => clearInterval(timer);
  }, [polling, range, error]);

  const transformed = useMemo(
    () => candles
      .map((c) => ({
        time: Math.floor(new Date(c.open_time).getTime() / 1000) as UTCTimestamp,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
        volume: c.volume,
      }))
      .filter((c) => Number.isFinite(c.time) && Number.isFinite(c.open) && Number.isFinite(c.high) && Number.isFinite(c.low) && Number.isFinite(c.close)),
    [candles],
  );

  useEffect(() => {
    if (loading || error || candles.length === 0 || !priceRef.current || !volumeRef.current) return;

    const commonOptions = {
      layout: { background: { type: ColorType.Solid, color: '#12161d' }, textColor: '#a9b2c1' },
      grid: { vertLines: { color: '#252d3a' }, horzLines: { color: '#252d3a' } },
      rightPriceScale: { borderColor: '#252d3a' },
      timeScale: { borderColor: '#252d3a', timeVisible: true, secondsVisible: false },
    };

    const priceChart = createChart(priceRef.current, { ...commonOptions, width: priceRef.current.clientWidth, height: 320, crosshair: { mode: 0 } });
    const volumeChart = createChart(volumeRef.current, { ...commonOptions, width: volumeRef.current.clientWidth, height: 120, crosshair: { mode: 0 } });

    const candleSeries = priceChart.addSeries(CandlestickSeries, { upColor: '#4f9b79', downColor: '#b97584', borderVisible: false, wickUpColor: '#4f9b79', wickDownColor: '#b97584' });
    const volumeSeries = volumeChart.addSeries(HistogramSeries, { color: '#6b7280', priceFormat: { type: 'volume' } });

    priceChartRef.current = priceChart;
    volumeChartRef.current = volumeChart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;

    const resizeObserver = new ResizeObserver(() => {
      if (!priceRef.current || !volumeRef.current) return;
      priceChart.applyOptions({ width: priceRef.current.clientWidth, height: 320 });
      volumeChart.applyOptions({ width: volumeRef.current.clientWidth, height: 120 });
    });
    resizeObserver.observe(priceRef.current);
    resizeObserver.observe(volumeRef.current);

    return () => {
      resizeObserver.disconnect();
      priceChart.remove();
      volumeChart.remove();
      priceChartRef.current = null;
      volumeChartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
    };
  }, [loading, error, candles.length]);

  useEffect(() => {
    if (!candleSeriesRef.current || !volumeSeriesRef.current || transformed.length === 0) return;

    candleSeriesRef.current.setData(transformed.map((c) => ({ time: c.time, open: c.open, high: c.high, low: c.low, close: c.close })));
    volumeSeriesRef.current.setData(transformed.map((c) => ({ time: c.time, value: c.volume, color: c.close >= c.open ? '#4f9b79aa' : '#b97584aa' })));
    priceChartRef.current?.timeScale().fitContent();
    volumeChartRef.current?.timeScale().fitContent();
  }, [transformed]);

  const latest = candles.length > 0 ? candles[candles.length - 1] : undefined;
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
          <button onClick={() => void fetchCandles(true)} className="rounded-lg bg-surface-900 px-3 py-1.5 text-xs text-text-secondary ring-1 ring-surface-700/70"><RefreshCw size={12} /></button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4 lg:grid-cols-8">
        <div className="rounded-lg bg-surface-900 p-2 ring-1 ring-surface-700/60">Symbol <div className="text-text-secondary">BTCUSDT</div></div>
        <div className="rounded-lg bg-surface-900 p-2 ring-1 ring-surface-700/60">Interval <div className="text-text-secondary">1m</div></div>
        <div className="rounded-lg bg-surface-900 p-2 ring-1 ring-surface-700/60">Latest Candle <div className="text-text-secondary">{latest?.open_time ?? '—'}</div></div>
        <div className="rounded-lg bg-surface-900 p-2 ring-1 ring-surface-700/60">Candle Count <div className="text-text-secondary">{candles.length}</div></div>
        <div className="rounded-lg bg-surface-900 p-2 ring-1 ring-surface-700/60">Lag Seconds <div className="text-text-secondary">{lagSeconds ?? '—'}</div></div>
        <div className="rounded-lg bg-surface-900 p-2 ring-1 ring-surface-700/60">Refresh <div className="text-text-secondary">{refreshStatus}</div></div>
        <div className="rounded-lg bg-surface-900 p-2 ring-1 ring-surface-700/60">Last Refreshed <div className="text-text-secondary">{lastRefreshedAt ?? '—'}</div></div>
        <label className="flex items-center justify-between rounded-lg bg-surface-900 p-2 ring-1 ring-surface-700/60">Live 10s <input type="checkbox" checked={polling} onChange={(e) => setPolling(e.target.checked)} /></label>
      </div>

      <section className="rounded-xl bg-surface-900 p-4 shadow-card ring-1 ring-surface-700/70">
        {loading ? <div className="h-[460px] animate-pulse rounded-lg bg-surface-850" /> : error ? (
          <div className="flex h-[460px] items-center justify-center rounded-lg bg-accent-red/10 text-sm text-accent-red">Failed to load candles: {error}</div>
        ) : candles.length === 0 ? (
          <div className="flex h-[460px] items-center justify-center rounded-lg bg-surface-850 text-sm text-text-muted">No candle data available for selected range.</div>
        ) : (
          <div className="space-y-2">
            <div ref={priceRef} className="h-[320px] min-h-[320px] w-full overflow-hidden rounded-lg" />
            <div ref={volumeRef} className="h-[120px] min-h-[120px] w-full overflow-hidden rounded-lg" />
          </div>
        )}
      </section>
    </div>
  );
}
