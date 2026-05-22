import { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import { useSocket, TradeAlert } from '../hooks/useSocket';
import { ToastContainer } from '../components/ToastNotification';

const API = 'http://localhost:3000';

interface Config {
  id: number;
  stockId: number;
  strategyName: string;
  timeframe: string;
  stock: { symbol: string; name: string };
}

interface Signal extends TradeAlert { stock?: { symbol: string }; }

// Audio chime using Web Audio API
function playChime() {
  try {
    const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.frequency.setValueAtTime(880, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(440, ctx.currentTime + 0.3);
    gain.gain.setValueAtTime(0.3, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.5);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.5);
  } catch { /* noop if audio not supported */ }
}

function isMarketOpen() {
  const now = new Date();
  const ist = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Kolkata' }));
  const h = ist.getHours(), m = ist.getMinutes();
  const day = ist.getDay();
  const minutes = h * 60 + m;
  return day >= 1 && day <= 5 && minutes >= 555 && minutes <= 930;
}

export function LiveScanner() {
  const { connected, alerts } = useSocket();
  const [configs, setConfigs] = useState<Config[]>([]);
  const [activeSignals, setActiveSignals] = useState<Signal[]>([]);
  const [toasts, setToasts] = useState<Array<TradeAlert & { toastId: string }>>([]);
  const [newSignalIds, setNewSignalIds] = useState<Set<number>>(new Set());
  const prevAlertsLen = useRef(0);

  useEffect(() => {
    axios.get(`${API}/api/configs`).then(r => setConfigs(r.data)).catch(() => {});
    axios.get(`${API}/api/signals/active`).then(r => setActiveSignals(r.data)).catch(() => {});
  }, []);

  // React to new alerts from socket
  useEffect(() => {
    if (alerts.length > prevAlertsLen.current) {
      const newAlerts = alerts.slice(0, alerts.length - prevAlertsLen.current);
      newAlerts.forEach(alert => {
        // Show toast
        const toastId = `${alert.id}-${Date.now()}`;
        setToasts(prev => [{ ...alert, toastId }, ...prev].slice(0, 5));
        // Play chime
        playChime();
        // Add to active signals table
        setActiveSignals(prev => {
          const existing = prev.find(s => s.id === alert.id);
          return existing ? prev : [alert, ...prev];
        });
        // Flash highlight
        setNewSignalIds(prev => new Set([...prev, alert.id]));
        setTimeout(() => {
          setNewSignalIds(prev => { const n = new Set(prev); n.delete(alert.id); return n; });
        }, 2000);
      });
    }
    prevAlertsLen.current = alerts.length;
  }, [alerts]);

  const dismissToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.toastId !== id));
  }, []);

  const closeSignal = async (id: number) => {
    try {
      await axios.patch(`${API}/api/signals/${id}/close`);
      setActiveSignals(prev => prev.map(s => s.id === id ? { ...s, status: 'CLOSED' } : s));
    } catch { /* noop */ }
  };

  const marketOpen = isMarketOpen();

  return (
    <div className="page">
      <ToastContainer alerts={toasts} onDismiss={dismissToast} />

      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
          <div>
            <h1 className="page-title">Live <span>Scanner</span></h1>
            <p className="page-subtitle">Real-time trade alerts via WebSocket</p>
          </div>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
            <span className={`connection-badge ${connected ? 'connected' : 'disconnected'}`}>
              <span className="connection-dot"></span>
              {connected ? 'Connected' : 'Disconnected'}
            </span>
          </div>
        </div>
      </div>

      {!connected && (
        <div className="alert alert-warning" style={{ marginBottom: '1.5rem' }}>
          ⚠ Reconnecting to server... Check that NestJS API is running on port 3000.
        </div>
      )}

      {!marketOpen && (
        <div className="alert alert-info" style={{ marginBottom: '1.5rem' }}>
          🕐 Market is currently <strong>CLOSED</strong>. Scanner pauses until 09:15 IST (Mon–Fri).
        </div>
      )}

      {/* Active Configurations */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div className="card-title">📡 Monitored Stocks ({configs.length})</div>
        {configs.length === 0 ? (
          <div className="empty-state" style={{ padding: '2rem' }}>
            <span className="empty-icon">🔕</span>
            <span className="empty-title">No stocks being monitored</span>
            <span className="empty-subtitle">Go to Backtest Arena → run a backtest → Set Active Strategy</span>
          </div>
        ) : (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem' }}>
            {configs.map(c => (
              <div key={c.id} style={{
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border-light)',
                borderRadius: 'var(--radius-sm)',
                padding: '0.5rem 1rem',
                display: 'flex',
                alignItems: 'center',
                gap: '0.75rem',
                fontSize: '0.85rem',
              }}>
                <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--cyan)', fontWeight: 600 }}>
                  {c.stock.symbol}
                </span>
                <span style={{ color: 'var(--text-muted)' }}>→</span>
                <span style={{ color: 'var(--text-secondary)' }}>{c.strategyName}</span>
                <span className="badge badge-active">{c.timeframe}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Active Signals */}
      <div className="card">
        <div className="card-title">🚨 Active Signals ({activeSignals.filter(s => s.status === 'ACTIVE').length})</div>

        {activeSignals.length === 0 ? (
          <div className="empty-state">
            <span className="empty-icon">🔍</span>
            <span className="empty-title">Waiting for signals...</span>
            <span className="empty-subtitle">
              Start the live scanner: <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--cyan)' }}>python apps/engine/scanner/live_scanner.py</code>
            </span>
          </div>
        ) : (
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Stock</th>
                  <th>Strategy</th>
                  <th>Entry ₹</th>
                  <th>Stop Loss ₹</th>
                  <th>Target ₹</th>
                  <th>R:R</th>
                  <th>Time</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {activeSignals.map(s => {
                  const rr = Math.abs((s.target - s.entryPrice) / (s.entryPrice - s.stopLoss));
                  const isBuy = s.signalType === 'BUY';
                  const symbol = s.symbol || s.stock?.symbol || `#${s.stockId}`;
                  return (
                    <tr key={s.id} className={newSignalIds.has(s.id) ? 'signal-row-new' : ''}>
                      <td>
                        <span className={`badge ${isBuy ? 'badge-buy' : 'badge-sell'}`}>
                          {isBuy ? '▲' : '▼'} {s.signalType}
                        </span>
                      </td>
                      <td>
                        <span className="mono" style={{ color: 'var(--cyan)', fontWeight: 600 }}>{symbol}</span>
                      </td>
                      <td>
                        <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>{s.strategyName}</span>
                      </td>
                      <td className="mono" style={{ color: isBuy ? 'var(--green)' : 'var(--red)', fontWeight: 600 }}>
                        ₹{s.entryPrice.toFixed(2)}
                      </td>
                      <td className="mono" style={{ color: 'var(--red)' }}>₹{s.stopLoss.toFixed(2)}</td>
                      <td className="mono" style={{ color: 'var(--green)' }}>₹{s.target.toFixed(2)}</td>
                      <td className="mono" style={{ color: rr >= 2 ? 'var(--green)' : 'var(--yellow)' }}>
                        1:{rr.toFixed(1)}
                      </td>
                      <td style={{ color: 'var(--text-muted)', fontSize: '0.78rem' }}>
                        {new Date(s.timestamp).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata' })}
                      </td>
                      <td>
                        <span className={`badge ${s.status === 'ACTIVE' ? 'badge-active' : 'badge-closed'}`}>
                          {s.status}
                        </span>
                      </td>
                      <td>
                        {s.status === 'ACTIVE' && (
                          <button className="btn btn-danger btn-sm" onClick={() => closeSignal(s.id)}>
                            Close
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
