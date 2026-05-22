import { useEffect, useRef, useState, useCallback } from 'react';
import { io, Socket } from 'socket.io-client';

const SOCKET_URL = 'http://localhost:3000';

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
    });

    socket.on('connect', () => {
      console.log('✅ Socket connected:', socket.id);
      setConnected(true);
    });

    socket.on('disconnect', () => {
      console.log('❌ Socket disconnected');
      setConnected(false);
    });

    socket.on('NEW_TRADE_ALERT', (alert: TradeAlert) => {
      console.log('🚨 New alert:', alert);
      setAlerts(prev => [alert, ...prev]);
    });

    socketRef.current = socket;

    return () => {
      socket.disconnect();
    };
  }, []);

  const clearAlerts = useCallback(() => setAlerts([]), []);

  return { connected, alerts, clearAlerts };
}
