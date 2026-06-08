import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { useSocket, TradeAlert } from "../hooks/useSocket";
import { ToastContainer } from "../components/ToastNotification";
import { API } from "../config";

interface BacktestSnapshot {
  winRate: number;
  totalTrades: number;
  netProfit: number;
  maxDrawdown: number;
  roiPercentage: number;
  createdAt: string;
}

interface Config {
  id: number;
  stockId: number;
  strategyName: string;
  timeframe: string;
  stock: { symbol: string; name: string };
  latestBacktest?: BacktestSnapshot | null;
}

interface Signal extends TradeAlert {
  stock?: { symbol: string };
  trade?: {
    trailingState?: string;
    originalStopLoss?: number;
    peakPrice?: number;
    remainingQty?: number;
    quantity?: number;
  };
}

// Audio chime using Web Audio API
function playChime() {
  try {
    const ctx = new (
      window.AudioContext || (window as any).webkitAudioContext
    )();
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
  } catch {
    /* noop if audio not supported */
  }
}

function isMarketOpen() {
  const now = new Date();
  const ist = new Date(
    now.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }),
  );
  const h = ist.getHours(),
    m = ist.getMinutes();
  const day = ist.getDay();
  const minutes = h * 60 + m;
  return day >= 1 && day <= 5 && minutes >= 555 && minutes <= 930;
}

export function LiveScanner() {
  const { connected, alerts } = useSocket();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<"SCANNER" | "MONITORED">("SCANNER");
  const [configs, setConfigs] = useState<Config[]>([]);
  const [activeSignals, setActiveSignals] = useState<Signal[]>([]);
  const [toasts, setToasts] = useState<Array<TradeAlert & { toastId: string }>>(
    [],
  );
  const [newSignalIds, setNewSignalIds] = useState<Set<number>>(new Set());
  const [rerunningId, setRerunningId] = useState<number | null>(null);
  const prevAlertsLen = useRef(0);

  const fetchConfigs = useCallback(() => {
    axios
      .get(`${API}/api/configs`)
      .then((r) => setConfigs(r.data))
      .catch(() => {});
  }, []);

  useEffect(() => {
    fetchConfigs();
    axios
      .get(`${API}/api/signals/active`)
      .then((r) => setActiveSignals(r.data))
      .catch(() => {});
  }, [fetchConfigs]);

  // Stop monitoring a stock×strategy whose edge has faded.
  const removeConfig = async (c: Config) => {
    if (
      !window.confirm(
        `Remove ${c.strategyName} on ${c.stock.symbol} from the live scanner? The scanner stops watching this pair next cycle.`,
      )
    )
      return;
    try {
      await axios.delete(`${API}/api/configs/${c.id}`);
      setConfigs((prev) => prev.filter((x) => x.id !== c.id));
    } catch {
      /* noop */
    }
  };

  // Re-run the backtest for a monitored pair. The engine persists a fresh BacktestReport,
  // so we just refetch the configs (which carry the latest snapshot) when it returns.
  const rerunBacktest = async (c: Config) => {
    setRerunningId(c.id);
    try {
      await axios.post(`${API}/api/engine/run-backtest`, {
        symbol: c.stock.symbol,
        strategy: c.strategyName,
        timeframe: c.timeframe,
      });
      fetchConfigs();
    } catch {
      /* noop */
    } finally {
      setRerunningId(null);
    }
  };

  // React to new alerts from socket
  useEffect(() => {
    if (alerts.length > prevAlertsLen.current) {
      const newAlerts = alerts.slice(0, alerts.length - prevAlertsLen.current);
      newAlerts.forEach((alert) => {
        // Show toast
        const toastId = `${alert.id}-${Date.now()}`;
        setToasts((prev) => [{ ...alert, toastId }, ...prev].slice(0, 5));
        // Play chime
        playChime();
        // Add to active signals table
        setActiveSignals((prev) => {
          const existing = prev.find((s) => s.id === alert.id);
          return existing ? prev : [alert, ...prev];
        });
        // Flash highlight
        setNewSignalIds((prev) => new Set([...prev, alert.id]));
        setTimeout(() => {
          setNewSignalIds((prev) => {
            const n = new Set(prev);
            n.delete(alert.id);
            return n;
          });
        }, 2000);
      });
    }
    prevAlertsLen.current = alerts.length;
  }, [alerts]);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.toastId !== id));
  }, []);

  const closeSignal = async (id: number, symbol: string) => {
    try {
      let payload = {};
      try {
        const liveRes = await axios.post(`${API}/api/engine/live-prices`, {
          symbols: [symbol],
        });
        const livePriceData = liveRes.data[symbol];
        const livePrice = livePriceData
          ? typeof livePriceData === "object"
            ? livePriceData.price
            : livePriceData
          : undefined;
        if (livePrice) {
          payload = { exitPrice: livePrice };
        }
      } catch (e) {
        console.error("Failed to fetch live price for closing", e);
      }

      await axios.patch(`${API}/api/signals/${id}/close`, payload);
      setActiveSignals((prev) =>
        prev.map((s) => (s.id === id ? { ...s, status: "CLOSED" } : s)),
      );
    } catch {
      /* noop */
    }
  };

  const marketOpen = isMarketOpen();

  return (
    <div className="page">
      <ToastContainer alerts={toasts} onDismiss={dismissToast} />

      <div className="page-header">
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "1rem",
            flexWrap: "wrap",
          }}
        >
          <div>
            <h1 className="page-title">
              Live <span>Scanner</span>
            </h1>
            <p className="page-subtitle">
              Real-time trade alerts via WebSocket
            </p>
          </div>
          <div
            style={{
              marginLeft: "auto",
              display: "flex",
              gap: "0.75rem",
              alignItems: "center",
            }}
          >
            <span
              className={`connection-badge ${connected ? "connected" : "disconnected"}`}
            >
              <span className="connection-dot"></span>
              {connected ? "Connected" : "Disconnected"}
            </span>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div
        style={{
          display: "flex",
          gap: "1rem",
          marginBottom: "1.5rem",
          borderBottom: "1px solid var(--border-light)",
        }}
      >
        {(["SCANNER", "MONITORED"] as const).map((t) => (
          <button
            key={t}
            style={{
              background: "transparent",
              border: "none",
              color: activeTab === t ? "var(--cyan)" : "var(--text-muted)",
              padding: "0.75rem 1rem",
              fontSize: "1rem",
              fontWeight: activeTab === t ? 600 : 400,
              borderBottom:
                activeTab === t
                  ? "2px solid var(--cyan)"
                  : "2px solid transparent",
              cursor: "pointer",
              transition: "all 0.2s ease",
            }}
            onClick={() => setActiveTab(t)}
          >
            {t === "SCANNER"
              ? "Live Scanner"
              : `Monitored Stocks (${configs.length})`}
          </button>
        ))}
      </div>

      {activeTab === "SCANNER" && (
        <>
      {!connected && (
        <div className="alert alert-warning" style={{ marginBottom: "1.5rem" }}>
          ⚠ Reconnecting to server... Check that NestJS API is running on port
          3000.
        </div>
      )}

      {!marketOpen && (
        <div className="alert alert-info" style={{ marginBottom: "1.5rem" }}>
          🕐 Market is currently <strong>CLOSED</strong>. Scanner pauses until
          09:15 IST (Mon–Fri).
        </div>
      )}

      {/* Active Signals */}
      <div className="card">
        <div className="card-title">
          🚨 Active Signals (
          {activeSignals.filter((s) => s.status === "ACTIVE").length})
        </div>

        {activeSignals.length === 0 ? (
          <div className="empty-state">
            <span className="empty-icon">🔍</span>
            <span className="empty-title">Waiting for signals...</span>
            <span className="empty-subtitle">
              Start the live scanner:{" "}
              <code
                style={{ fontFamily: "var(--font-mono)", color: "var(--cyan)" }}
              >
                python apps/engine/scanner/live_scanner.py
              </code>
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
                  <th>Hold</th>
                  <th>Qty</th>
                  <th>Entry ₹</th>
                  <th>Stop Loss ₹</th>
                  <th>Target ₹</th>
                  <th>R:R</th>
                  <th>Protection</th>
                  <th>Time</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {activeSignals.map((s) => {
                  const rr = Math.abs(
                    (s.target - s.entryPrice) / (s.entryPrice - s.stopLoss),
                  );
                  const isBuy = s.signalType === "BUY";
                  const symbol = s.symbol || s.stock?.symbol || `#${s.stockId}`;
                  const holdLabels: Record<
                    string,
                    { label: string; color: string; icon: string }
                  > = {
                    INTRADAY: {
                      label: "Intraday",
                      color: "#22d3ee",
                      icon: "⏱",
                    },
                    SHORT_SWING: {
                      label: "Short",
                      color: "#fbbf24",
                      icon: "📅",
                    },
                    MID_SWING: { label: "Mid", color: "#a78bfa", icon: "📆" },
                    LONG_POSITIONAL: {
                      label: "Long",
                      color: "#60a5fa",
                      icon: "🗓",
                    },
                  };
                  const hold = holdLabels[(s as any).holdDuration] || {
                    label: "—",
                    color: "#4b5563",
                    icon: "",
                  };

                  // Trailing state from trade data
                  const trailingState = s.trade?.trailingState || "INITIAL";
                  const originalSL = s.trade?.originalStopLoss;
                  const slChanged =
                    originalSL != null &&
                    Math.abs(originalSL - s.stopLoss) > 0.01;

                  const trailingBadges: Record<
                    string,
                    { label: string; color: string; icon: string; bg: string }
                  > = {
                    INITIAL: {
                      label: "Active",
                      color: "#64748b",
                      icon: "⏳",
                      bg: "#64748b15",
                    },
                    PHASE1: {
                      label: "Phase 1",
                      color: "#64748b",
                      icon: "⏳",
                      bg: "#64748b15",
                    },
                    PHASE2: {
                      label: "Phase 2 (BE)",
                      color: "#22c55e",
                      icon: "🔒",
                      bg: "#22c55e15",
                    },
                    PHASE3: {
                      label: "Phase 3 (Trail)",
                      color: "#f59e0b",
                      icon: "💰",
                      bg: "#f59e0b15",
                    },
                    REVERSAL_EXIT: {
                      label: "Reversal Exit",
                      color: "#ef4444",
                      icon: "⚠️",
                      bg: "#ef444415",
                    },
                    // legacy fallback
                    BREAKEVEN: {
                      label: "Breakeven",
                      color: "#22c55e",
                      icon: "🔒",
                      bg: "#22c55e15",
                    },
                    PROFIT_LOCK: {
                      label: "Profit Locked",
                      color: "#f59e0b",
                      icon: "💰",
                      bg: "#f59e0b15",
                    },
                  };
                  const trailInfo =
                    trailingBadges[trailingState] || trailingBadges.INITIAL;

                  return (
                    <tr
                      key={s.id}
                      className={newSignalIds.has(s.id) ? "signal-row-new" : ""}
                    >
                      <td>
                        <span
                          className={`badge ${isBuy ? "badge-buy" : "badge-sell"}`}
                        >
                          {isBuy ? "▲" : "▼"} {s.signalType}
                        </span>
                      </td>
                      <td>
                        <span
                          className="mono"
                          style={{ color: "var(--cyan)", fontWeight: 600 }}
                        >
                          {symbol}
                        </span>
                      </td>
                      <td>
                        <span
                          style={{
                            fontSize: "0.8rem",
                            color: "var(--text-secondary)",
                          }}
                        >
                          {s.strategyName}
                        </span>
                      </td>
                      <td>
                        <span
                          className="badge"
                          style={{
                            background: `${hold.color}20`,
                            color: hold.color,
                            border: `1px solid ${hold.color}40`,
                            fontSize: "0.65rem",
                          }}
                        >
                          {hold.icon} {hold.label}
                        </span>
                      </td>
                      <td>
                        <span className="mono" style={{ fontSize: "0.8rem" }}>
                          {s.trade && s.trade.remainingQty !== undefined && s.trade.quantity !== undefined &&
                          s.trade.remainingQty < s.trade.quantity
                            ? `${s.trade.remainingQty}/${s.trade.quantity}`
                            : s.trade?.quantity || 1}
                        </span>
                      </td>
                      <td
                        className="mono"
                        style={{
                          color: isBuy ? "var(--green)" : "var(--red)",
                          fontWeight: 600,
                        }}
                      >
                        ₹{s.entryPrice.toFixed(2)}
                      </td>
                      <td>
                        <div
                          style={{
                            display: "flex",
                            flexDirection: "column",
                            gap: "0.15rem",
                          }}
                        >
                          <span
                            className="mono"
                            style={{
                              color: slChanged ? "var(--green)" : "var(--red)",
                              fontWeight: 600,
                              fontSize: "0.85rem",
                            }}
                          >
                            ₹{s.stopLoss.toFixed(2)}
                          </span>
                          {slChanged && originalSL != null && (
                            <span
                              style={{
                                fontSize: "0.65rem",
                                color: "var(--text-muted)",
                                textDecoration: "line-through",
                              }}
                            >
                              ₹{originalSL.toFixed(2)}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="mono" style={{ color: "var(--green)" }}>
                        ₹{s.target.toFixed(2)}
                      </td>
                      <td
                        className="mono"
                        style={{
                          color: rr >= 2 ? "var(--green)" : "var(--yellow)",
                        }}
                      >
                        1:{rr.toFixed(1)}
                      </td>
                      <td>
                        <span
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "0.3rem",
                            padding: "0.2rem 0.5rem",
                            borderRadius: "4px",
                            fontSize: "0.7rem",
                            fontWeight: 600,
                            background: trailInfo.bg,
                            color: trailInfo.color,
                            border: `1px solid ${trailInfo.color}30`,
                          }}
                        >
                          {trailInfo.icon} {trailInfo.label}
                        </span>
                      </td>
                      <td
                        style={{
                          color: "var(--text-muted)",
                          fontSize: "0.78rem",
                        }}
                      >
                        {new Date(s.timestamp).toLocaleTimeString("en-IN", {
                          timeZone: "Asia/Kolkata",
                        })}
                      </td>
                      <td>
                        {s.status === "ACTIVE" && (
                          <button
                            className="btn btn-danger btn-sm"
                            onClick={() => closeSignal(s.id, symbol)}
                          >
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
        </>
      )}

      {activeTab === "MONITORED" && (
        <div className="card">
          <div className="card-title">
            📡 Monitored Stocks ({configs.length})
          </div>
          {configs.length === 0 ? (
            <div className="empty-state" style={{ padding: "2rem" }}>
              <span className="empty-icon">🔕</span>
              <span className="empty-title">No stocks being monitored</span>
              <span className="empty-subtitle">
                Go to Backtest Arena → run a backtest → Set Live
              </span>
            </div>
          ) : (
            <>
              <p
                className="page-subtitle"
                style={{ marginTop: 0, marginBottom: "1rem", fontSize: "0.8rem" }}
              >
                Each pair's latest backtest. Re-run to refresh, or remove a stock
                whose edge has faded.
              </p>
              <div className="table-wrapper">
                <table>
                  <thead>
                    <tr>
                      <th>Symbol</th>
                      <th>Strategy</th>
                      <th>Timeframe</th>
                      <th style={{ textAlign: "right" }}>Win Rate</th>
                      <th style={{ textAlign: "right" }}>Trades</th>
                      <th style={{ textAlign: "right" }}>Net Profit</th>
                      <th style={{ textAlign: "right" }}>ROI</th>
                      <th style={{ textAlign: "right" }}>Max DD</th>
                      <th>Last Tested</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {configs.map((c) => {
                      const bt = c.latestBacktest;
                      return (
                        <tr key={c.id}>
                          <td>
                            <span
                              className="mono"
                              style={{ color: "var(--cyan)", fontWeight: 700 }}
                            >
                              {c.stock.symbol}
                            </span>
                          </td>
                          <td>
                            <span
                              style={{
                                fontSize: "0.85rem",
                                color: "var(--text-secondary)",
                              }}
                            >
                              {c.strategyName}
                            </span>
                          </td>
                          <td>
                            <span className="badge badge-active">
                              {c.timeframe}
                            </span>
                          </td>
                          {bt ? (
                            <>
                              <td
                                style={{
                                  textAlign: "right",
                                  color:
                                    bt.winRate >= 50
                                      ? "var(--green)"
                                      : "var(--red)",
                                }}
                              >
                                {bt.winRate}%
                              </td>
                              <td style={{ textAlign: "right" }}>
                                {bt.totalTrades}
                              </td>
                              <td
                                className="mono"
                                style={{
                                  textAlign: "right",
                                  color:
                                    bt.netProfit >= 0
                                      ? "var(--green)"
                                      : "var(--red)",
                                }}
                              >
                                {bt.netProfit >= 0 ? "+" : ""}₹
                                {bt.netProfit.toLocaleString("en-IN")}
                              </td>
                              <td
                                className="mono"
                                style={{
                                  textAlign: "right",
                                  color:
                                    bt.roiPercentage >= 0
                                      ? "var(--green)"
                                      : "var(--red)",
                                }}
                              >
                                {bt.roiPercentage >= 0 ? "+" : ""}
                                {bt.roiPercentage}%
                              </td>
                              <td
                                className="mono"
                                style={{
                                  textAlign: "right",
                                  color: "var(--red)",
                                }}
                              >
                                -₹{bt.maxDrawdown.toLocaleString("en-IN")}
                              </td>
                              <td
                                style={{
                                  color: "var(--text-muted)",
                                  fontSize: "0.78rem",
                                }}
                              >
                                {new Date(bt.createdAt).toLocaleDateString(
                                  "en-IN",
                                )}
                              </td>
                            </>
                          ) : (
                            <td
                              colSpan={6}
                              style={{
                                color: "var(--text-muted)",
                                fontSize: "0.8rem",
                              }}
                            >
                              No backtest yet — Re-run to generate one.
                            </td>
                          )}
                          <td>
                            <div style={{ display: "flex", gap: "0.4rem" }}>
                              <button
                                className="btn btn-secondary btn-sm"
                                disabled={rerunningId === c.id}
                                onClick={() => rerunBacktest(c)}
                              >
                                {rerunningId === c.id ? "Running…" : "Re-run"}
                              </button>
                              <button
                                className="btn btn-secondary btn-sm"
                                onClick={() =>
                                  navigate(`/backtesting/${c.strategyName}`)
                                }
                              >
                                View
                              </button>
                              <button
                                className="btn btn-danger btn-sm"
                                onClick={() => removeConfig(c)}
                              >
                                Remove
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
