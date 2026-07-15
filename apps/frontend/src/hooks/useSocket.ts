import { useEffect, useRef, useState, useCallback } from 'react';
import { io, Socket } from 'socket.io-client';
import { SOCKET_URL, getApiKey } from '../config';

export interface TradeAlert {
  id: number;
  stockId: number;
  symbol: string;
  strategyName: string;
  signalType: 'BUY' | 'SELL';
  entryPrice: number;
  stopLoss: number;
  target: number;
  timestamp: string;
  status: string;
}

export function useSocket() {
  const socketRef = useRef<Socket | null>(null);
  const [connected, setConnected] = useState(false);
  const [alerts, setAlerts] = useState<TradeAlert[]>([]);

  useEffect(() => {
    const socket = io(SOCKET_URL, {
      transports: ['websocket', 'polling'],
      reconnectionAttempts: 10,
      reconnectionDelay: 2000,
      auth: getApiKey() ? { apiKey: getApiKey() } : undefined,
    });

    socket.on('connect', () => {
      console.log('✅ Socket connected:', socket.id);
      setConnected(true);
    });

    socket.on('disconnect', () => {
      console.log('❌ Socket disconnected');
      setConnected(false);
    });

    // Ask once for notification permission so we can surface alerts even when
    // the tab is in the background (PWA-style local notifications).
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission().catch(() => {});
    }

    socket.on('NEW_TRADE_ALERT', (alert: TradeAlert) => {
      console.log('🚨 New alert:', alert);
      setAlerts(prev => [alert, ...prev]);
      if ('Notification' in window && Notification.permission === 'granted') {
        try {
          new Notification(`${alert.signalType} ${alert.symbol}`, {
            body: `${alert.strategyName} · Entry ₹${alert.entryPrice} · SL ₹${alert.stopLoss} · Target ₹${alert.target}`,
            icon: '/icon.svg',
            tag: `signal-${alert.id}`,
          });
        } catch {
          /* ignore */
        }
      }
    });

    socketRef.current = socket;

    return () => {
      socket.disconnect();
    };
  }, []);

  const clearAlerts = useCallback(() => setAlerts([]), []);

  return { connected, alerts, clearAlerts };
}
