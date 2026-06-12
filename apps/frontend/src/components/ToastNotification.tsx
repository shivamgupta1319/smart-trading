import { useEffect, useRef } from 'react';
import type { TradeAlert } from '../hooks/useSocket';

interface ToastProps {
  alert: TradeAlert;
  onDismiss: () => void;
}

export function Toast({ alert, onDismiss }: ToastProps) {
  const timerRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    timerRef.current = window.setTimeout(onDismiss, 8000);
    return () => clearTimeout(timerRef.current);
  }, [onDismiss]);

  const isBuy = alert.signalType === 'BUY';

  // Money fields may arrive as strings if the API serializes Prisma Decimals;
  // coerce defensively so .toFixed() never blows up the whole app.
  const entryPrice = Number(alert.entryPrice);
  const stopLoss = Number(alert.stopLoss);
  const target = Number(alert.target);
  const rr = Math.abs((target - entryPrice) / (entryPrice - stopLoss));

  return (
    <div className={`toast ${isBuy ? 'buy' : 'sell'}`}>
      <div className="toast-header">
        <span className="toast-title">🔔 New Trade Alert</span>
        <button className="toast-close" onClick={onDismiss}>✕</button>
      </div>
      <div className={`toast-symbol ${isBuy ? 'buy' : 'sell'}`}>
        <span>{isBuy ? '▲' : '▼'}</span>
        <span>{alert.signalType}</span>
        <span>{alert.symbol || `Stock #${alert.stockId}`}</span>
      </div>
      <div className="toast-details">
        <span className="toast-detail-label">Entry</span>
        <span className="toast-detail-value">₹{entryPrice.toFixed(2)}</span>
        <span className="toast-detail-label">Stop Loss</span>
        <span className="toast-detail-value">₹{stopLoss.toFixed(2)}</span>
        <span className="toast-detail-label">Target</span>
        <span className="toast-detail-value">₹{target.toFixed(2)}</span>
        <span className="toast-detail-label">R:R</span>
        <span className="toast-detail-value">1 : {Number.isFinite(rr) ? rr.toFixed(1) : '—'}</span>
      </div>
      <div className="toast-strategy">📊 {alert.strategyName}</div>
    </div>
  );
}

export function ToastContainer({ alerts, onDismiss }: {
  alerts: Array<TradeAlert & { toastId: string }>;
  onDismiss: (id: string) => void;
}) {
  return (
    <div className="toast-container">
      {alerts.map(a => (
        <Toast key={a.toastId} alert={a} onDismiss={() => onDismiss(a.toastId)} />
      ))}
    </div>
  );
}
