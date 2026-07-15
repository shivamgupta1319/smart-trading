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
  // Nullable: rows written before the 2026-07-15 fix never stored these — they fill
  // in on the next re-run. Render "—" rather than 0, which would read as "no edge".
  avgRMultiple: number | null;
  spanYears: number | null;
  createdAt: string;
}

/** Mirrors AUTOSELECT_MIN_TRADES (auto_select.py, default 10) — the sample size below
 *  which auto-select refuses to promote a cell. Under it, avgR is noise, not edge:
 *  Golden_Cross showed avgR 4.722 off ONE trade in five years. The UI must not present
 *  that as a cell's best number just because it sorts highest. */
const MIN_TRADES_FOR_EDGE = 10;

/** Net profit per rupee risked. Unlike ROI it's independent of position size, holding
 *  period and compounding, so it's the only column comparable across buckets — a 1D
 *  cell's ROI covers ~5y while a 15m cell's covers ~4.7mo. */
const edgeColor = (r: number, trades: number) =>
  trades < MIN_TRADES_FOR_EDGE
    ? "var(--text-muted)" // too few trades to mean anything — don't dress it up
    : r >= 0.3
      ? "var(--green)"
      : r > 0.05
        ? "var(--text)"
        : "var(--red)";

/** Raw ROI is cumulative over whatever history is stored, so it is NOT comparable
 *  between a 5-year swing cell and a 4.7-month intraday one. Divide by the measured
 *  span. Returns null when the span is unknown (old rows) — never guess. */
const roiPerYear = (bt: BacktestSnapshot) =>
  bt.spanYears && bt.spanYears > 0 ? bt.roiPercentage / bt.spanYears : null;

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
  const [rerunAll, setRerunAll] = useState<{ done: number; total: number } | null>(null);
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

  // Re-run the backtest for EVERY monitored pair. Runs with limited concurrency so the
  // engine isn't hammered, tracks progress, and refetches once at the end. Individual
  // failures are skipped so one bad pair doesn't abort the batch.
  const rerunAllBacktests = async () => {
    if (rerunAll) return;
    const list = [...configs];
    if (list.length === 0) return;
    setRerunAll({ done: 0, total: list.length });
    let idx = 0;
    let done = 0;
    const CONCURRENCY = 4;
    const worker = async () => {
      while (idx < list.length) {
        const c = list[idx++];
        try {
          await axios.post(`${API}/api/engine/run-backtest`, {
            symbol: c.stock.symbol,
            strategy: c.strategyName,
            timeframe: c.timeframe,
          });
        } catch {
          /* skip this pair, keep going */
        }
        done++;
        setRerunAll({ done, total: list.length });
      }
    };
    await Promise.all(
      Array.from({ length: Math.min(CONCURRENCY, list.length) }, () => worker()),
    );
    fetchConfigs();
    setRerunAll(null);
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
          <div
            className="card-title"
            style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap" }}
          >
            <span>📡 Monitored Stocks ({configs.length})</span>
            {configs.length > 0 && (
              <button
                className="btn btn-primary"
                onClick={rerunAllBacktests}
                disabled={rerunAll !== null || rerunningId !== null}
                style={{ fontSize: "0.85rem", padding: "0.4rem 0.9rem" }}
                title="Re-run the backtest for every monitored pair"
              >
                {rerunAll
                  ? `Re-running… ${rerunAll.done}/${rerunAll.total}`
                  : "🔄 Re-run All"}
              </button>
            )}
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
                      <th
                        style={{ textAlign: "right" }}
                        title="Average R-multiple: net profit per ₹1 risked. The honest edge metric — independent of position size, holding period and compounding, so it's comparable across strategies and timeframes (ROI is not). Above 0.05 = real edge."
                      >
                        Edge (avgR)
                      </th>
                      <th style={{ textAlign: "right" }}>Net Profit</th>
                      <th
                        style={{ textAlign: "right" }}
                        title="Cumulative ROI over the cell's whole stored history, with the per-year rate beneath. 1D cells cover ~5 years and 15m/5m cells ~4.7 months, so only the per-year figure is comparable between them."
                      >
                        ROI
                      </th>
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
                                    bt.avgRMultiple === null
                                      ? "var(--text-muted)"
                                      : edgeColor(bt.avgRMultiple, bt.totalTrades),
                                }}
                                title={
                                  bt.avgRMultiple === null
                                    ? "Not stored yet — re-run this backtest to compute it."
                                    : bt.totalTrades < MIN_TRADES_FOR_EDGE
                                      ? `Only ${bt.totalTrades} trade(s) — too few to mean anything, however good the number looks. Auto-select ignores cells under ${MIN_TRADES_FOR_EDGE}.`
                                      : `${bt.avgRMultiple >= 0 ? "Gains" : "Loses"} ₹${Math.abs(bt.avgRMultiple).toFixed(3)} per ₹1 risked, per trade.`
                                }
                              >
                                {bt.avgRMultiple === null
                                  ? "—"
                                  : `${bt.avgRMultiple >= 0 ? "+" : ""}${bt.avgRMultiple.toFixed(3)}R`}
                                {bt.avgRMultiple !== null &&
                                  bt.totalTrades < MIN_TRADES_FOR_EDGE && (
                                    <div style={{ fontSize: "0.7em", opacity: 0.8 }}>
                                      low sample
                                    </div>
                                  )}
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
                                {roiPerYear(bt) !== null && (
                                  <div
                                    style={{
                                      fontSize: "0.75em",
                                      opacity: 0.7,
                                      color: "var(--text)",
                                    }}
                                  >
                                    {roiPerYear(bt)!.toFixed(1)}%/yr
                                  </div>
                                )}
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
                              colSpan={7}
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
                                disabled={rerunningId === c.id || rerunAll !== null}
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
