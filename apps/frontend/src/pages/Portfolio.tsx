import { useEffect, useState, useRef, useCallback } from 'react';
import axios from 'axios';
import { createChart, ColorType, type IChartApi, AreaSeries } from 'lightweight-charts';
import { API } from '../config';

const HOLD_LABELS: Record<string, { label: string; color: string; icon: string }> = {
  INTRADAY: { label: 'Intraday', color: '#22d3ee', icon: '⏱' },
  SHORT_SWING: { label: 'Short Swing', color: '#fbbf24', icon: '📅' },
  MID_SWING: { label: 'Mid Swing', color: '#a78bfa', icon: '📆' },
  LONG_POSITIONAL: { label: 'Long Term', color: '#60a5fa', icon: '🗓' },
  UNKNOWN: { label: 'Unknown', color: '#4b5563', icon: '❓' },
};

interface Trade {
  id: number;
  signalId: number;
  stockId: number;
  symbol: string;
  strategyName: string;
  signalType: string;
  holdDuration: string;
  entryPrice: number;
  exitPrice: number | null;
  stopLoss: number;
  target: number;
  quantity: number;
  capitalUsed: number;
  riskAmount: number;
  pnl: number | null;
  realizedPnl: number | null;
  pnlPercent: number | null;
  outcome: string | null;
  entryTime: string;
  exitTime: string | null;
  status: string;
  notes: string | null;
  originalStopLoss: number | null;
  trailingState: string;
  remainingQty: number | null;
  peakPrice: number | null;
}

interface PortfolioStats {
  totalTrades: number;
  openTrades: number;
  closedTrades: number;
  totalPnl: number;
  winRate: number;
  wins: number;
  losses: number;
  avgWin: number;
  avgLoss: number;
  profitFactor: number;
  bestStrategy: string;
  strategyBreakdown: {
    strategy: string;
    totalPnl: number;
    trades: number;
    wins: number;
    winRate: number;
  }[];
  stockWiseStrategyBreakdown: {
    symbol: string;
    strategy: string;
    totalPnl: number;
    trades: number;
    wins: number;
    winRate: number;
  }[];
  equityCurve: { time: number; value: number }[];
  holdDurationStats: Record<string, { trades: number; pnl: number }>;
  initialCapital: number;
  currentCapital: number;
}

export function Portfolio() {
  const [stats, setStats] = useState<PortfolioStats | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'ALL' | 'OPEN' | 'CLOSED'>('ALL');
  const [holdFilter, setHoldFilter] = useState<string>('ALL');
  const [livePrices, setLivePrices] = useState<Record<string, number | null>>({});
  const [activeTab, setActiveTab] = useState<'PORTFOLIO' | 'ANALYSIS' | 'RISK'>('PORTFOLIO');
  const [risk, setRisk] = useState<any | null>(null);
  const [riskLoading, setRiskLoading] = useState(false);

  useEffect(() => {
    if (activeTab !== 'RISK') return;
    setRiskLoading(true);
    axios
      .get(`${API}/api/trades/risk`)
      .then((r) => setRisk(r.data))
      .catch(() => setRisk(null))
      .finally(() => setRiskLoading(false));
  }, [activeTab]);
  const equityRef = useRef<HTMLDivElement>(null);
  const chartInstanceRef = useRef<IChartApi | null>(null);

  const fetchLivePrices = async (tradeList: Trade[]) => {
    const openTrades = tradeList.filter(t => t.status === 'OPEN');
    if (openTrades.length === 0) return;
    try {
      const symbols = Array.from(new Set(openTrades.map(t => t.symbol)));
      const r = await axios.post(`${API}/api/engine/live-prices`, { symbols });
      setLivePrices(r.data);
    } catch (e) {
      console.error('Failed to fetch live prices', e);
    }
  };

  const closeTrade = async (signalId: number, symbol: string) => {
    try {
      let payload = {};
      try {
        const liveRes = await axios.post(`${API}/api/engine/live-prices`, { symbols: [symbol] });
        const livePriceData = liveRes.data[symbol];
        const livePrice = livePriceData ? (typeof livePriceData === 'object' ? livePriceData.price : livePriceData) : undefined;
        if (livePrice) {
          payload = { exitPrice: livePrice };
        }
      } catch (e) {
        console.error('Failed to fetch live price for closing', e);
      }
      
      await axios.patch(`${API}/api/signals/${signalId}/close`, payload);
      // Refresh portfolio after closing
      fetchData();
    } catch (e) {
      console.error('Failed to close trade', e);
    }
  };

  const removeTrade = async (tradeId: number) => {
    if (!window.confirm('Are you sure you want to completely delete this trade from your journal?')) return;
    try {
      await axios.delete(`${API}/api/trades/${tradeId}`);
      fetchData();
    } catch (e) {
      console.error('Failed to remove trade', e);
    }
  };

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [statsRes, tradesRes] = await Promise.all([
        axios.get(`${API}/api/trades/stats`),
        axios.get(`${API}/api/trades`),
      ]);
      setStats(statsRes.data);
      setTrades(tradesRes.data);
      fetchLivePrices(tradesRes.data);
    } catch (e) {
      console.error('Failed to fetch portfolio data', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    const intervalId = setInterval(() => {
      fetchLivePrices(trades);
    }, 10000);
    return () => clearInterval(intervalId);
  }, [trades]);

  // Render equity curve chart
  useEffect(() => {
    if (!equityRef.current || !stats?.equityCurve?.length) return;

    if (chartInstanceRef.current) {
      chartInstanceRef.current.remove();
      chartInstanceRef.current = null;
    }

    const chart = createChart(equityRef.current, {
      width: equityRef.current.clientWidth,
      height: 250,
      layout: {
        background: { type: ColorType.Solid, color: '#0f1629' },
        textColor: '#94a3b8',
        fontSize: 11,
        fontFamily: "'Inter', sans-serif",
      },
      grid: {
        vertLines: { color: 'rgba(30, 45, 71, 0.3)' },
        horzLines: { color: 'rgba(30, 45, 71, 0.3)' },
      },
      rightPriceScale: { borderColor: '#1e2d47' },
      timeScale: { borderColor: '#1e2d47' },
    });
    chartInstanceRef.current = chart;

    const areaSeries = chart.addSeries(AreaSeries, {
      topColor: stats.totalPnl >= 0 ? 'rgba(16, 185, 129, 0.4)' : 'rgba(248, 113, 113, 0.4)',
      bottomColor: stats.totalPnl >= 0 ? 'rgba(16, 185, 129, 0.02)' : 'rgba(248, 113, 113, 0.02)',
      lineColor: stats.totalPnl >= 0 ? '#10b981' : '#f87171',
      lineWidth: 2,
    });
    areaSeries.setData(stats.equityCurve as any);
    chart.timeScale().fitContent();

    const handleResize = () => {
      if (equityRef.current && chartInstanceRef.current) {
        chartInstanceRef.current.applyOptions({ width: equityRef.current.clientWidth });
      }
    };
    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
      if (chartInstanceRef.current) {
        chartInstanceRef.current.remove();
        chartInstanceRef.current = null;
      }
    };
  }, [stats, activeTab]);

  const filteredTrades = trades.filter((t) => {
    if (filter !== 'ALL' && t.status !== filter) return false;
    if (holdFilter !== 'ALL' && t.holdDuration !== holdFilter) return false;
    return true;
  });

  if (loading) {
    return (
      <div className="page" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1rem' }}>
          <div className="spinner" style={{ width: '32px', height: '32px' }}></div>
          <p className="page-subtitle">Loading portfolio data...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page animate-fade-in">
      <div className="page-header">
        <h1 className="page-title">💼 <span>Portfolio</span> Tracker</h1>
        <p className="page-subtitle">
          Track trades from live signals • ₹1,00,000 capital • 2% risk per trade
        </p>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '1rem', marginBottom: '2rem', borderBottom: '1px solid var(--border-light)' }}>
        <button
          className={`tab-btn ${activeTab === 'PORTFOLIO' ? 'active' : ''}`}
          style={{
            background: 'transparent',
            border: 'none',
            color: activeTab === 'PORTFOLIO' ? 'var(--cyan)' : 'var(--text-muted)',
            padding: '0.75rem 1rem',
            fontSize: '1rem',
            fontWeight: activeTab === 'PORTFOLIO' ? 600 : 400,
            borderBottom: activeTab === 'PORTFOLIO' ? '2px solid var(--cyan)' : '2px solid transparent',
            cursor: 'pointer',
            transition: 'all 0.2s ease'
          }}
          onClick={() => setActiveTab('PORTFOLIO')}
        >
          Actual Portfolio
        </button>
        <button
          className={`tab-btn ${activeTab === 'ANALYSIS' ? 'active' : ''}`}
          style={{
            background: 'transparent',
            border: 'none',
            color: activeTab === 'ANALYSIS' ? 'var(--cyan)' : 'var(--text-muted)',
            padding: '0.75rem 1rem',
            fontSize: '1rem',
            fontWeight: activeTab === 'ANALYSIS' ? 600 : 400,
            borderBottom: activeTab === 'ANALYSIS' ? '2px solid var(--cyan)' : '2px solid transparent',
            cursor: 'pointer',
            transition: 'all 0.2s ease'
          }}
          onClick={() => setActiveTab('ANALYSIS')}
        >
          Strategy Performance Analysis
        </button>
        <button
          className={`tab-btn ${activeTab === 'RISK' ? 'active' : ''}`}
          style={{
            background: 'transparent',
            border: 'none',
            color: activeTab === 'RISK' ? 'var(--cyan)' : 'var(--text-muted)',
            padding: '0.75rem 1rem',
            fontSize: '1rem',
            fontWeight: activeTab === 'RISK' ? 600 : 400,
            borderBottom: activeTab === 'RISK' ? '2px solid var(--cyan)' : '2px solid transparent',
            cursor: 'pointer',
            transition: 'all 0.2s ease'
          }}
          onClick={() => setActiveTab('RISK')}
        >
          Risk Engine
        </button>
      </div>

      {activeTab === 'RISK' && (
        <div className="animate-fade-in">
          {riskLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: '4rem' }}><div className="spinner"></div></div>
          ) : !risk ? (
            <div className="card" style={{ padding: '2rem', textAlign: 'center' }}>
              <p className="page-subtitle">No risk data.</p>
            </div>
          ) : (
            <>
              {/* Flags */}
              {risk.flags?.length > 0 && (
                <div className="card" style={{ padding: '1rem 1.25rem', marginBottom: '1.5rem', borderLeft: '4px solid var(--red)' }}>
                  {risk.flags.map((f: string, i: number) => (
                    <p key={i} style={{ margin: '0.25rem 0', color: 'var(--red)' }}>⚠️ {f}</p>
                  ))}
                </div>
              )}
              {risk.openPositions === 0 && (!risk.flags || risk.flags.length === 0) && (
                <div className="card" style={{ padding: '1rem 1.25rem', marginBottom: '1.5rem' }}>
                  <p className="page-subtitle" style={{ margin: 0 }}>No open positions — book is flat (zero risk deployed).</p>
                </div>
              )}

              {/* Top metrics */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '2rem' }}>
                <div className="metric-card">
                  <p className="metric-label">Open Positions</p>
                  <p className="metric-value">{risk.openPositions}</p>
                </div>
                <div className="metric-card">
                  <p className="metric-label">Deployed Capital</p>
                  <p className="metric-value">₹{Number(risk.deployedCapital).toLocaleString('en-IN')}</p>
                  <p className="metric-label">{risk.deployedPct}% of capital</p>
                </div>
                <div className="metric-card">
                  <p className="metric-label">Total Heat (risk-at-stop)</p>
                  <p className="metric-value" style={{ color: risk.heatPct > 6 ? 'var(--red)' : 'var(--text-primary)' }}>₹{Number(risk.totalHeat).toLocaleString('en-IN')}</p>
                  <p className="metric-label">{risk.heatPct}% of capital</p>
                </div>
                <div className="metric-card">
                  <p className="metric-label">Available Capital</p>
                  <p className="metric-value">₹{Number(risk.availableCapital).toLocaleString('en-IN')}</p>
                </div>
              </div>

              {/* Sector concentration */}
              {risk.sectorConcentration?.length > 0 && (
                <div style={{ marginBottom: '2rem' }}>
                  <h3 style={{ marginBottom: '1rem' }}>Sector Concentration</h3>
                  <div className="table-container">
                    <table className="data-table">
                      <thead><tr><th>Sector</th><th style={{ textAlign: 'right' }}>Exposure</th><th style={{ textAlign: 'right' }}>% of Book</th></tr></thead>
                      <tbody>
                        {risk.sectorConcentration.map((s: any, i: number) => (
                          <tr key={i}>
                            <td>{s.sector}</td>
                            <td style={{ textAlign: 'right' }}>₹{Number(s.exposure).toLocaleString('en-IN')}</td>
                            <td style={{ textAlign: 'right' }} className={s.pctOfBook > 40 ? 'negative' : ''}>{s.pctOfBook}%</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Per-position */}
              {risk.positions?.length > 0 && (
                <div>
                  <h3 style={{ marginBottom: '1rem' }}>Open Positions</h3>
                  <div className="table-container">
                    <table className="data-table">
                      <thead><tr><th>Symbol</th><th>Strategy</th><th>Sector</th><th style={{ textAlign: 'right' }}>Qty</th><th style={{ textAlign: 'right' }}>Exposure</th><th style={{ textAlign: 'right' }}>Risk @ Stop</th></tr></thead>
                      <tbody>
                        {risk.positions.map((p: any, i: number) => (
                          <tr key={i}>
                            <td><span className="stock-symbol" style={{ fontWeight: 600 }}>{p.symbol}</span></td>
                            <td>{p.strategy}</td>
                            <td>{p.sector}</td>
                            <td style={{ textAlign: 'right' }}>{p.qty}</td>
                            <td style={{ textAlign: 'right' }}>₹{Number(p.exposure).toLocaleString('en-IN')}</td>
                            <td style={{ textAlign: 'right', color: 'var(--red)' }}>₹{Number(p.riskAtStop).toLocaleString('en-IN')}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Summary cards */}
      {stats && activeTab === 'PORTFOLIO' && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '1rem', marginBottom: '2rem' }}>
            <div className="metric-card">
              <p className="metric-label">Current Capital</p>
              <p className={`metric-value ${stats.currentCapital >= stats.initialCapital ? 'positive' : 'negative'}`} style={{ fontSize: '1.3rem' }}>
                ₹{stats.currentCapital.toLocaleString('en-IN')}
              </p>
            </div>
            <div className="metric-card">
              <p className="metric-label">Total P&L</p>
              <p className={`metric-value ${stats.totalPnl >= 0 ? 'positive' : 'negative'}`} style={{ fontSize: '1.3rem' }}>
                {stats.totalPnl >= 0 ? '+' : ''}₹{stats.totalPnl.toLocaleString('en-IN')}
              </p>
            </div>
            <div className="metric-card">
              <p className="metric-label">Win Rate</p>
              <p className="metric-value highlight" style={{ fontSize: '1.3rem' }}>
                {stats.winRate}%
              </p>
            </div>
            <div className="metric-card">
              <p className="metric-label">Profit Factor</p>
              <p className={`metric-value ${stats.profitFactor >= 1 ? 'positive' : 'negative'}`} style={{ fontSize: '1.3rem' }}>
                {stats.profitFactor}
              </p>
            </div>
            <div className="metric-card">
              <p className="metric-label">Active / Total</p>
              <p className="metric-value" style={{ fontSize: '1.3rem' }}>
                <span style={{ color: 'var(--cyan)' }}>{stats.openTrades}</span>
                <span style={{ color: 'var(--text-muted)' }}> / </span>
                {stats.totalTrades}
              </p>
            </div>
          </div>

          {/* Secondary stats row */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '1rem', marginBottom: '2rem' }}>
            <div className="metric-card" style={{ background: 'var(--bg-input)' }}>
              <p className="metric-label">W / L</p>
              <p className="metric-value" style={{ fontSize: '1.1rem' }}>
                <span style={{ color: 'var(--green)' }}>{stats.wins}</span>
                <span style={{ color: 'var(--text-muted)' }}> / </span>
                <span style={{ color: 'var(--red)' }}>{stats.losses}</span>
              </p>
            </div>
            <div className="metric-card" style={{ background: 'var(--bg-input)' }}>
              <p className="metric-label">Avg Win</p>
              <p className="metric-value positive" style={{ fontSize: '1.1rem' }}>+₹{stats.avgWin}</p>
            </div>
            <div className="metric-card" style={{ background: 'var(--bg-input)' }}>
              <p className="metric-label">Avg Loss</p>
              <p className="metric-value negative" style={{ fontSize: '1.1rem' }}>-₹{stats.avgLoss}</p>
            </div>
            <div className="metric-card" style={{ background: 'var(--bg-input)' }}>
              <p className="metric-label">Best Strategy</p>
              <p className="metric-value highlight" style={{ fontSize: '0.9rem' }}>{stats.bestStrategy}</p>
            </div>
            <div className="metric-card" style={{ background: 'var(--bg-input)', border: '1px solid rgba(34, 197, 94, 0.2)' }}>
              <p className="metric-label">🔒 Saved by Trailing</p>
              <p className="metric-value" style={{ fontSize: '1.1rem' }}>
                {(() => {
                  const saved = trades.filter(t => {
                    if (t.status !== 'CLOSED' || !t.trailingState || t.trailingState === 'INITIAL') return false;
                    if (t.outcome !== 'WIN' && t.outcome !== 'BREAKEVEN') return false;
                    
                    if (t.exitPrice !== null && t.target !== null) {
                      const hitTarget = t.signalType === 'BUY' ? t.exitPrice >= t.target : t.exitPrice <= t.target;
                      if (hitTarget) return false;
                    }
                    return true;
                  }).length;
                  return (
                    <span style={{ color: saved > 0 ? 'var(--green)' : 'var(--text-muted)' }}>
                      {saved} trade{saved !== 1 ? 's' : ''}
                    </span>
                  );
                })()}
              </p>
            </div>
          </div>
        </>
      )}

      {stats && activeTab === 'ANALYSIS' && (
        <>
          {/* Equity Curve + Hold Duration Breakdown */}
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '1.5rem', marginBottom: '2rem' }}>
            <div className="card">
              <h3 className="card-title" style={{ marginBottom: '1rem' }}>Equity Curve</h3>
              {stats.equityCurve.length > 0 ? (
                <div ref={equityRef} style={{ borderRadius: 'var(--radius-sm)', overflow: 'hidden' }}></div>
              ) : (
                <div className="empty-state" style={{ padding: '2rem' }}>
                  <p className="empty-subtitle">No closed trades yet — equity curve will appear after your first trade closes.</p>
                </div>
              )}
            </div>

            <div className="card">
              <h3 className="card-title" style={{ marginBottom: '1rem' }}>Hold Duration Breakdown</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                {Object.entries(stats.holdDurationStats).map(([key, val]) => {
                  const info = HOLD_LABELS[key] || HOLD_LABELS.UNKNOWN;
                  return (
                    <div key={key} style={{
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                      padding: '0.75rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-sm)',
                      border: `1px solid ${info.color}30`,
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <span>{info.icon}</span>
                        <span style={{ color: info.color, fontWeight: 600, fontSize: '0.85rem' }}>{info.label}</span>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <p style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)' }}>{val.trades} trades</p>
                        <p style={{ fontSize: '0.8rem', color: val.pnl >= 0 ? 'var(--green)' : 'var(--red)', fontFamily: 'var(--font-mono)' }}>
                          {val.pnl >= 0 ? '+' : ''}₹{val.pnl.toFixed(0)}
                        </p>
                      </div>
                    </div>
                  );
                })}
                {Object.keys(stats.holdDurationStats).length === 0 && (
                  <p className="page-subtitle" style={{ textAlign: 'center', padding: '1rem' }}>No data yet</p>
                )}
              </div>
            </div>
          </div>

          {/* Strategy Performance */}
          {stats.strategyBreakdown.length > 0 && (
            <div className="card" style={{ marginBottom: '2rem' }}>
              <h3 className="card-title" style={{ marginBottom: '1rem' }}>Strategy Performance</h3>
              <div className="table-wrapper">
                <table>
                  <thead>
                    <tr>
                      <th>Strategy</th>
                      <th>Trades</th>
                      <th>Wins</th>
                      <th>Win Rate</th>
                      <th>Total P&L</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.strategyBreakdown.map((s) => (
                      <tr key={s.strategy}>
                        <td><span style={{ fontFamily: 'var(--font-mono)', color: 'var(--cyan)', fontWeight: 600 }}>{s.strategy}</span></td>
                        <td>{s.trades}</td>
                        <td>{s.wins}</td>
                        <td>
                          <span style={{ color: s.winRate >= 50 ? 'var(--green)' : 'var(--red)' }}>
                            {s.winRate}%
                          </span>
                        </td>
                        <td>
                          <span style={{ color: s.totalPnl >= 0 ? 'var(--green)' : 'var(--red)', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                            {s.totalPnl >= 0 ? '+' : ''}₹{s.totalPnl.toLocaleString('en-IN')}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Stock-wise Strategy Performance */}
          {stats.stockWiseStrategyBreakdown && stats.stockWiseStrategyBreakdown.length > 0 && (
            <div className="card" style={{ marginBottom: '2rem' }}>
              <h3 className="card-title" style={{ marginBottom: '1rem' }}>Stock-wise Strategy Performance</h3>
              <div className="table-wrapper">
                <table>
                  <thead>
                    <tr>
                      <th>Symbol</th>
                      <th>Strategy</th>
                      <th>Trades</th>
                      <th>Wins</th>
                      <th>Win Rate</th>
                      <th>Total P&L</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.stockWiseStrategyBreakdown.map((s) => (
                      <tr key={`${s.symbol}-${s.strategy}`}>
                        <td><span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--text-primary)' }}>{s.symbol}</span></td>
                        <td><span style={{ fontFamily: 'var(--font-mono)', color: 'var(--cyan)', fontWeight: 600 }}>{s.strategy}</span></td>
                        <td>{s.trades}</td>
                        <td>{s.wins}</td>
                        <td>
                          <span style={{ color: s.winRate >= 50 ? 'var(--green)' : 'var(--red)' }}>
                            {s.winRate}%
                          </span>
                        </td>
                        <td>
                          <span style={{ color: s.totalPnl >= 0 ? 'var(--green)' : 'var(--red)', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                            {s.totalPnl >= 0 ? '+' : ''}₹{s.totalPnl.toLocaleString('en-IN')}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {/* Trade History */}
      {activeTab === 'PORTFOLIO' && (
        <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.75rem' }}>
          <h3 className="card-title" style={{ margin: 0 }}>Trade Journal</h3>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            {(['ALL', 'OPEN', 'CLOSED'] as const).map((f) => (
              <button
                key={f}
                className={`btn btn-sm ${filter === f ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setFilter(f)}
              >
                {f === 'ALL' ? 'All' : f === 'OPEN' ? '🟢 Open' : '⬜ Closed'}
              </button>
            ))}
            <select
              className="form-select"
              style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem', width: 'auto' }}
              value={holdFilter}
              onChange={(e) => setHoldFilter(e.target.value)}
            >
              <option value="ALL">All Durations</option>
              <option value="INTRADAY">⏱ Intraday</option>
              <option value="SHORT_SWING">📅 Short Swing</option>
              <option value="MID_SWING">📆 Mid Swing</option>
              <option value="LONG_POSITIONAL">🗓 Long Term</option>
            </select>
          </div>
        </div>

        {filteredTrades.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📋</div>
            <p className="empty-title">No trades yet</p>
            <p className="empty-subtitle">
              Trades will appear here when the live scanner generates signals.
            </p>
          </div>
        ) : (
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Status</th>
                  <th>Type</th>
                  <th>Symbol</th>
                  <th>Strategy</th>
                  <th>Duration</th>
                  <th>Qty</th>
                  <th>Entry ₹</th>
                  <th>Target ₹</th>
                  <th>Stop Loss ₹</th>
                  <th>Exit ₹</th>
                  <th>P&L</th>
                  <th>Outcome</th>
                  <th>Time</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {filteredTrades.map((t) => {
                  const hold = HOLD_LABELS[t.holdDuration] || HOLD_LABELS.UNKNOWN;
                  return (
                    <tr key={t.id}>
                      <td>
                        <span className={`badge ${t.status === 'OPEN' ? 'badge-active' : 'badge-closed'}`}>
                          {t.status}
                        </span>
                      </td>
                      <td>
                        <span className={`badge ${t.signalType === 'BUY' ? 'badge-buy' : 'badge-sell'}`}>
                          {t.signalType}
                        </span>
                      </td>
                      <td>
                        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--text-primary)' }}>
                          {t.symbol}
                        </span>
                      </td>
                      <td>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: 'var(--cyan)' }}>
                          {t.strategyName}
                        </span>
                      </td>
                      <td>
                        <span className="badge" style={{
                          background: `${hold.color}20`,
                          color: hold.color,
                          border: `1px solid ${hold.color}40`,
                          fontSize: '0.65rem',
                        }}>
                          {hold.icon} {hold.label}
                        </span>
                      </td>
                      <td>
                        <span className="mono" style={{ fontSize: '0.85rem' }}>
                          {t.remainingQty !== null && t.remainingQty < t.quantity ? `${t.remainingQty}/${t.quantity}` : t.quantity}
                        </span>
                      </td>
                      <td>
                        <span className="mono" style={{ fontSize: '0.85rem' }}>₹{t.entryPrice.toFixed(2)}</span>
                      </td>
                      <td>
                        <span className="mono" style={{ fontSize: '0.85rem', color: 'var(--green)' }}>₹{t.target.toFixed(2)}</span>
                      </td>
                      <td>
                        <span className="mono" style={{ fontSize: '0.85rem', color: 'var(--red)' }}>₹{t.stopLoss.toFixed(2)}</span>
                      </td>
                      <td>
                        {(() => {
                          let exitPriceToDisplay = t.exitPrice;
                          let isLivePrice = false;
                          if (t.status === 'OPEN') {
                             const priceData = livePrices[t.symbol];
                             const livePrice = priceData ? (typeof priceData === 'object' ? (priceData as any).price : priceData) : null;
                             if (livePrice) {
                               exitPriceToDisplay = livePrice;
                               isLivePrice = true;
                             }
                          }
                          
                          return exitPriceToDisplay ? (
                            <div style={{ display: 'flex', flexDirection: 'column' }}>
                              <span className="mono" style={{ fontSize: '0.85rem' }}>₹{exitPriceToDisplay.toFixed(2)}</span>
                              {isLivePrice && <span style={{ fontSize: '0.65rem', color: 'var(--cyan)' }}>Live</span>}
                            </div>
                          ) : (
                            <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>—</span>
                          );
                        })()}
                      </td>
                      <td>
                        {(() => {
                          let pnlToDisplay = t.pnl;
                          let pnlPercentToDisplay = t.pnlPercent;
                          let isLivePnl = false;
                          
                          if (t.status === 'OPEN') {
                             const priceData = livePrices[t.symbol];
                             const livePrice = priceData ? (typeof priceData === 'object' ? (priceData as any).price : priceData) : null;
                             if (livePrice) {
                               const remQty = t.remainingQty !== null ? t.remainingQty : t.quantity;
                               const realized = t.realizedPnl || 0;
                               const unrealized = t.signalType === 'BUY' 
                                 ? (livePrice - t.entryPrice) * remQty 
                                 : (t.entryPrice - livePrice) * remQty;
                               
                               pnlToDisplay = unrealized + realized;
                               pnlPercentToDisplay = (pnlToDisplay / (t.quantity * t.entryPrice)) * 100;
                               isLivePnl = true;
                             }
                          }

                          return pnlToDisplay !== null ? (
                            <div>
                              <span style={{
                                fontFamily: 'var(--font-mono)',
                                fontWeight: 700,
                                color: pnlToDisplay >= 0 ? 'var(--green)' : 'var(--red)',
                                fontSize: '0.85rem',
                              }}>
                                {pnlToDisplay >= 0 ? '+' : ''}₹{pnlToDisplay.toFixed(0)}
                              </span>
                              <br />
                              <span style={{
                                fontSize: '0.7rem',
                                color: (pnlPercentToDisplay || 0) >= 0 ? 'var(--green)' : 'var(--red)',
                              }}>
                                {(pnlPercentToDisplay || 0) >= 0 ? '+' : ''}{(pnlPercentToDisplay || 0).toFixed(2)}%
                              </span>
                              {isLivePnl && <span style={{ fontSize: '0.65rem', color: 'var(--cyan)' }}>Live</span>}
                            </div>
                          ) : (
                            <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>—</span>
                          );
                        })()}
                      </td>
                      <td>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
                          <span className={`badge ${t.outcome === 'WIN' ? 'badge-buy' : t.outcome === 'LOSS' ? 'badge-sell' : t.status === 'OPEN' ? 'badge-active' : ''}`}>
                            {t.outcome || (t.status === 'OPEN' ? '⏳ Open' : 'BREAKEVEN')}
                          </span>
                          {t.status === 'CLOSED' && t.trailingState && t.trailingState !== 'INITIAL' && (
                            <span style={{
                              fontSize: '0.6rem',
                              padding: '0.1rem 0.35rem',
                              borderRadius: '3px',
                              fontWeight: 600,
                              ...(t.trailingState === 'BREAKEVEN' ? { color: '#22c55e', background: '#22c55e15' } :
                                 t.trailingState === 'PROFIT_LOCK' ? { color: '#f59e0b', background: '#f59e0b15' } :
                                 t.trailingState === 'REVERSAL_EXIT' ? { color: '#ef4444', background: '#ef444415' } :
                                 { color: '#64748b', background: '#64748b15' })
                            }}>
                              {t.trailingState === 'BREAKEVEN' ? '🔒 BE Exit' :
                               t.trailingState === 'PROFIT_LOCK' ? '💰 Lock Exit' :
                               t.trailingState === 'REVERSAL_EXIT' ? '⚠️ Reversal' :
                               t.trailingState}
                            </span>
                          )}
                        </div>
                      </td>
                      <td style={{ color: 'var(--text-muted)', fontSize: '0.78rem' }}>
                        {new Date(t.entryTime).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit' }).toLowerCase()}
                        <br/>
                        <span style={{ fontSize: '0.65rem' }}>
                          {new Date(t.entryTime).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })}
                        </span>
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                          {t.status === 'OPEN' && (
                            <button 
                              className="btn btn-danger btn-sm" 
                              style={{ padding: '0.25rem 0.5rem', fontSize: '0.7rem' }}
                              onClick={() => closeTrade(t.signalId, t.symbol)}
                            >
                              Close
                            </button>
                          )}
                          <button
                            className="btn btn-sm"
                            style={{ 
                              padding: '0.25rem 0.5rem', 
                              fontSize: '0.7rem', 
                              background: 'transparent',
                              border: '1px solid var(--border-light)',
                              color: 'var(--text-muted)'
                            }}
                            onClick={() => removeTrade(t.id)}
                            title="Remove Trade"
                          >
                            🗑
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
      )}
    </div>
  );
}
