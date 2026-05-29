import { useEffect, useRef, useState } from 'react';
import {
  createChart,
  ColorType,
  CrosshairMode,
  type IChartApi,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
} from 'lightweight-charts';
import axios from 'axios';

const API = 'http://localhost:3000';

interface ChartData {
  candles: { time: number; open: number; high: number; low: number; close: number }[];
  volumes: { time: number; value: number; color: string }[];
  indicators: {
    ema50?: { time: number; value: number }[];
    ema200?: { time: number; value: number }[];
    bbUpper?: { time: number; value: number }[];
    bbLower?: { time: number; value: number }[];
    bbMid?: { time: number; value: number }[];
  };
}

interface CandlestickChartProps {
  symbol: string;
}

const TIMEFRAMES = [
  { label: '5m', value: '5m' },
  { label: '15m', value: '15m' },
  { label: '1H', value: '1h' },
  { label: '1D', value: '1d' },
  { label: '1W', value: '1wk' },
];

export function CandlestickChart({ symbol }: CandlestickChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [timeframe, setTimeframe] = useState('1d');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!chartContainerRef.current) return;

    // Destroy previous chart
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const container = chartContainerRef.current;

    const chart = createChart(container, {
      width: container.clientWidth,
      height: 500,
      layout: {
        background: { type: ColorType.Solid, color: '#0f1629' },
        textColor: '#94a3b8',
        fontSize: 12,
        fontFamily: "'Inter', sans-serif",
      },
      grid: {
        vertLines: { color: 'rgba(30, 45, 71, 0.5)' },
        horzLines: { color: 'rgba(30, 45, 71, 0.5)' },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: 'rgba(34, 211, 238, 0.3)', labelBackgroundColor: '#22d3ee' },
        horzLine: { color: 'rgba(34, 211, 238, 0.3)', labelBackgroundColor: '#22d3ee' },
      },
      rightPriceScale: {
        borderColor: '#1e2d47',
      },
      timeScale: {
        borderColor: '#1e2d47',
        timeVisible: timeframe !== '1d' && timeframe !== '1wk',
        secondsVisible: false,
      },
    });

    chartRef.current = chart;

    // Fetch data and render
    const fetchAndRender = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await axios.get(`${API}/api/engine/chart-data/${symbol}`, {
          params: { timeframe },
          timeout: 30000,
        });
        const data: ChartData = res.data;

        if (!data.candles || data.candles.length === 0) {
          setError('No chart data available for this timeframe.');
          setLoading(false);
          return;
        }

        // Candlestick series
        const candleSeries = chart.addSeries(CandlestickSeries, {
          upColor: '#10b981',
          downColor: '#f87171',
          borderUpColor: '#10b981',
          borderDownColor: '#f87171',
          wickUpColor: '#10b981',
          wickDownColor: '#f87171',
        });
        candleSeries.setData(data.candles as any);

        // Volume histogram
        const volumeSeries = chart.addSeries(HistogramSeries, {
          priceFormat: { type: 'volume' },
          priceScaleId: 'volume',
        });
        chart.priceScale('volume').applyOptions({
          scaleMargins: { top: 0.85, bottom: 0 },
        });
        volumeSeries.setData(data.volumes as any);

        // EMA 50 line
        if (data.indicators.ema50 && data.indicators.ema50.length > 0) {
          const ema50Series = chart.addSeries(LineSeries, {
            color: '#fbbf24',
            lineWidth: 1,
            title: 'EMA 50',
          });
          ema50Series.setData(data.indicators.ema50 as any);
        }

        // EMA 200 line
        if (data.indicators.ema200 && data.indicators.ema200.length > 0) {
          const ema200Series = chart.addSeries(LineSeries, {
            color: '#a78bfa',
            lineWidth: 1,
            title: 'EMA 200',
          });
          ema200Series.setData(data.indicators.ema200 as any);
        }

        // Bollinger Bands
        if (data.indicators.bbUpper && data.indicators.bbUpper.length > 0) {
          const bbUpperSeries = chart.addSeries(LineSeries, {
            color: 'rgba(34, 211, 238, 0.4)',
            lineWidth: 1,
            lineStyle: 2, // dashed
            title: 'BB Upper',
          });
          bbUpperSeries.setData(data.indicators.bbUpper as any);

          if (data.indicators.bbLower) {
            const bbLowerSeries = chart.addSeries(LineSeries, {
              color: 'rgba(34, 211, 238, 0.4)',
              lineWidth: 1,
              lineStyle: 2,
              title: 'BB Lower',
            });
            bbLowerSeries.setData(data.indicators.bbLower as any);
          }

          if (data.indicators.bbMid) {
            const bbMidSeries = chart.addSeries(LineSeries, {
              color: 'rgba(34, 211, 238, 0.2)',
              lineWidth: 1,
              lineStyle: 1,
              title: 'BB Mid',
            });
            bbMidSeries.setData(data.indicators.bbMid as any);
          }
        }

        chart.timeScale().fitContent();
      } catch (e: any) {
        setError(e.response?.data?.detail || e.message || 'Failed to load chart data');
      } finally {
        setLoading(false);
      }
    };

    fetchAndRender();

    // Handle resize
    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
        });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  }, [symbol, timeframe]);

  return (
    <div>
      {/* Timeframe selector */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
        {TIMEFRAMES.map((tf) => (
          <button
            key={tf.value}
            onClick={() => setTimeframe(tf.value)}
            className={`btn ${timeframe === tf.value ? 'btn-primary' : 'btn-secondary'} btn-sm`}
            style={{ minWidth: '50px' }}
          >
            {tf.label}
          </button>
        ))}

        {/* Legend */}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: '1rem', alignItems: 'center', fontSize: '0.75rem' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <span style={{ width: 12, height: 2, background: '#fbbf24', display: 'inline-block' }}></span>
            <span style={{ color: '#fbbf24' }}>EMA 50</span>
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <span style={{ width: 12, height: 2, background: '#a78bfa', display: 'inline-block' }}></span>
            <span style={{ color: '#a78bfa' }}>EMA 200</span>
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <span style={{ width: 12, height: 2, background: 'rgba(34,211,238,0.5)', display: 'inline-block', borderTop: '1px dashed rgba(34,211,238,0.5)' }}></span>
            <span style={{ color: 'var(--cyan)' }}>BB</span>
          </span>
        </div>
      </div>

      {/* Chart container */}
      <div
        ref={chartContainerRef}
        style={{
          width: '100%',
          borderRadius: 'var(--radius-md)',
          overflow: 'hidden',
          border: '1px solid var(--border)',
          position: 'relative',
          minHeight: 500,
        }}
      >
        {loading && (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: 'rgba(15, 22, 41, 0.8)',
              zIndex: 10,
              gap: '1rem',
            }}
          >
            <div className="spinner"></div>
            <span style={{ color: 'var(--text-secondary)' }}>
              Loading {timeframe} chart...
            </span>
          </div>
        )}
        {error && (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: 'rgba(15, 22, 41, 0.9)',
              zIndex: 10,
              color: 'var(--red)',
              fontSize: '0.9rem',
            }}
          >
            ⚠ {error}
          </div>
        )}
      </div>
    </div>
  );
}
