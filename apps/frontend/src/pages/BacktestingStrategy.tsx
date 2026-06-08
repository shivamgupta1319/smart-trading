import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import axios from "axios";
import { API } from "../config";

interface BacktestStockResult {
  symbol: string;
  metrics: {
    winRate: number;
    totalTrades: number;
    maxDrawdown: number;
    netProfit: number;
    roiPercentage: number;
    grossProfit?: number;
    totalCosts?: number;
    profitFactor?: number;
  };
}

interface WalkForward {
  folds: { fold: number; trades: number; roiPercentage: number; winRate: number }[];
  aggregate: {
    foldsWithTrades: number;
    pctProfitableFolds: number;
    meanOosRoi: number;
    stdOosRoi: number;
    consistent: boolean;
  };
  disclaimer: string;
}
interface MonteCarlo {
  tradesSampled: number;
  iterations: number;
  roi: { p5: number; p50: number; p95: number; mean: number };
  maxDrawdownPct: { p5: number; p50: number; p95: number; worst: number };
  probabilityOfProfit: number;
  disclaimer: string;
}

export function BacktestingStrategy() {
  const { strategyName } = useParams<{ strategyName: string }>();
  const navigate = useNavigate();
  const [results, setResults] = useState<BacktestStockResult[]>([]);
  const [running, setRunning] = useState(false);
  const [activeConfigs, setActiveConfigs] = useState<{ symbol: string; strategyName: string }[]>([]);
  const [strategyTimeframe, setStrategyTimeframe] = useState<string>("1D");
  const [message, setMessage] = useState<{ type: string; text: string } | null>(null);

  // Out-of-sample validation modal state
  const [validateSymbol, setValidateSymbol] = useState<string | null>(null);
  const [validating, setValidating] = useState(false);
  const [wf, setWf] = useState<WalkForward | null>(null);
  const [mc, setMc] = useState<MonteCarlo | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  const showMessage = (type: string, text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 4000);
  };

  const fetchActiveConfigs = async () => {
    try {
      const res = await axios.get(`${API}/api/configs`);
      setActiveConfigs(res.data.map((c: any) => ({ symbol: c.stock.symbol, strategyName: c.strategyName })));
    } catch (e) {
      console.error(e);
    }
  };

  const fetchStrategyDetails = async () => {
    try {
      const res = await axios.get(`${API}/api/engine/strategies`);
      const strat = res.data.find((s: any) => s.name === strategyName);
      if (strat) {
        setStrategyTimeframe(strat.timeframe);
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchActiveConfigs();
    fetchStrategyDetails();
  }, [strategyName]);

  const runAllStocks = async () => {
    if (!strategyName) return;
    setRunning(true);
    try {
      showMessage(
        "success",
        `Running ${strategyName} on all stocks... This may take a few seconds.`,
      );
      const r = await axios.post(`${API}/api/engine/run-strategy-all-stocks`, {
        strategy: strategyName,
      });
      setResults(r.data.results || []);
      showMessage("success", `✓ Backtest complete.`);
    } catch (e: any) {
      showMessage("error", e.response?.data?.message || "Backtest failed.");
    } finally {
      setRunning(false);
    }
  };

  const handleSetLive = async (symbol: string) => {
    try {
      const res = await axios.post(`${API}/api/configs/toggle`, { symbol, strategyName, timeframe: strategyTimeframe });
      if (res.data.status === 'added') {
        setActiveConfigs(prev => [...prev, { symbol, strategyName: strategyName! }]);
        // No snapshot write needed here: running the backtest (run-strategy-all-stocks)
        // already persisted a BacktestReport per stock×strategy on the engine side, so the
        // Monitored Stocks tab will pick up this pair's latest result automatically.
        showMessage('success', `${strategyName} is now set for Live Signals on ${symbol}!`);
      } else {
        setActiveConfigs(prev => prev.filter(c => !(c.symbol === symbol && c.strategyName === strategyName)));
        showMessage('success', `${strategyName} is removed from Live Signals on ${symbol}!`);
      }
    } catch (e: any) {
      showMessage('error', e.response?.data?.message || 'Failed to toggle live strategy.');
    }
  };

  const isLive = (symbol: string) => {
    return activeConfigs.some(c => c.symbol === symbol && c.strategyName === strategyName);
  };

  const runValidation = async (symbol: string) => {
    if (!strategyName) return;
    setValidateSymbol(symbol);
    setValidating(true);
    setWf(null);
    setMc(null);
    setValidationError(null);
    const body = { symbol, strategy: strategyName, timeframe: strategyTimeframe };
    // Run the two checks independently — Monte-Carlo needs >=5 trades, so it can
    // legitimately fail for a thin stock while walk-forward still has folds to show.
    const [wfRes, mcRes] = await Promise.allSettled([
      axios.post(`${API}/api/engine/run-walk-forward`, { ...body, folds: 5 }),
      axios.post(`${API}/api/engine/run-monte-carlo`, { ...body, iterations: 2000 }),
    ]);

    const describe = (r: PromiseRejectedResult): string => {
      const err = r.reason;
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail || err?.response?.data?.message;
      if (status === 400 || status === 404) return detail || "Not enough data for this stock.";
      if (status >= 500) return `Server error${detail ? `: ${detail}` : ""}. This is a bug — please report it.`;
      return detail || "Validation failed.";
    };

    if (wfRes.status === "fulfilled") setWf(wfRes.value.data);
    if (mcRes.status === "fulfilled") setMc(mcRes.value.data);

    // Only show a blocking error if BOTH failed; otherwise render what we got.
    if (wfRes.status === "rejected" && mcRes.status === "rejected") {
      setValidationError(describe(wfRes));
    } else {
      if (wfRes.status === "rejected") setValidationError(`Walk-forward: ${describe(wfRes)}`);
      else if (mcRes.status === "rejected") setValidationError(`Monte-Carlo: ${describe(mcRes)}`);
    }
    setValidating(false);
  };

  return (
    <div className="page animate-fade-in">
      {message && (
        <div className="toast-container">
          <div className={`toast ${message.type}`}>
            <div className="toast-header">
              <span className="toast-title">{message.text}</span>
            </div>
          </div>
        </div>
      )}

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "1rem",
          marginBottom: "2rem",
        }}
      >
        <button
          onClick={() => navigate("/backtesting")}
          className="btn btn-secondary"
          style={{ padding: "0.5rem", borderRadius: "var(--radius-md)" }}
        >
          <svg
            width="24"
            height="24"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M10 19l-7-7m0 0l7-7m-7 7h18"
            />
          </svg>
        </button>
        <div>
          <h1 className="page-title">{strategyName?.replace(/_/g, " ")}</h1>
          <p className="page-subtitle">Strategy Backtest Performance</p>
        </div>
      </div>

      <div
        className="card"
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: "1.5rem",
          padding: "3rem 2rem",
          textAlign: "center",
          marginBottom: "2rem",
        }}
      >
        <div style={{ maxWidth: "600px" }}>
          <h2
            className="page-title"
            style={{ fontSize: "1.5rem", marginBottom: "0.5rem" }}
          >
            Run on All Stocks
          </h2>
          <p className="page-subtitle" style={{ marginBottom: "1.5rem" }}>
            Evaluate this strategy against all available stocks in the database
            to find the best performing assets.
          </p>
          <button
            onClick={runAllStocks}
            disabled={running}
            className="btn btn-primary"
            style={{
              padding: "1rem 2rem",
              fontSize: "1.1rem",
              borderRadius: "var(--radius-md)",
            }}
          >
            {running ? (
              <>
                <div className="spinner"></div>
                <span>Processing All Stocks...</span>
              </>
            ) : (
              <>
                <svg
                  width="24"
                  height="24"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"
                  />
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <span>Execute Backtest</span>
              </>
            )}
          </button>
        </div>
      </div>

      {results.length > 0 && (
        <div className="animate-fade-in-up">
          <h2
            className="page-title"
            style={{ fontSize: "1.5rem", marginBottom: "1.5rem" }}
          >
            Results (Sorted by ROI)
          </h2>
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th style={{ textAlign: "right" }}>Win Rate</th>
                  <th style={{ textAlign: "right" }}>Total Trades</th>
                  <th style={{ textAlign: "right" }}>Net Profit</th>
                  <th style={{ textAlign: "right" }}>ROI</th>
                  <th style={{ textAlign: "right" }}>Max Drawdown</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r, i) => (
                  <tr key={i}>
                    <td>
                      <span
                        className="stock-symbol"
                        style={{ fontWeight: 600 }}
                      >
                        {r.symbol}
                      </span>
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <span
                        className={
                          r.metrics.winRate >= 50 ? "positive" : "negative"
                        }
                      >
                        {r.metrics.winRate}%
                      </span>
                    </td>
                    <td style={{ textAlign: "right" }}>
                      {r.metrics.totalTrades}
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <span
                        className={
                          r.metrics.netProfit >= 0 ? "positive" : "negative"
                        }
                      >
                        {r.metrics.netProfit >= 0 ? "+" : ""}₹
                        {r.metrics.netProfit.toLocaleString("en-IN")}
                      </span>
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <span
                        className={
                          r.metrics.roiPercentage >= 0 ? "positive" : "negative"
                        }
                      >
                        {r.metrics.roiPercentage >= 0 ? "+" : ""}
                        {r.metrics.roiPercentage}%
                      </span>
                    </td>
                    <td style={{ textAlign: "right", color: "var(--danger)" }}>
                      -₹{r.metrics.maxDrawdown.toLocaleString("en-IN")}
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: "0.5rem" }}>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => runValidation(r.symbol)}
                          title="Out-of-sample walk-forward + Monte-Carlo validation"
                        >
                          🔬 Validate
                        </button>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => navigate(`/stock/${r.symbol}`)}
                        >
                          View Stock
                        </button>
                        <button
                          className={`btn btn-sm ${isLive(r.symbol) ? "btn-primary" : "btn-secondary"}`}
                          onClick={() => handleSetLive(r.symbol)}
                        >
                          {isLive(r.symbol) ? "Live (Remove)" : "Set Live"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {validateSymbol && (
        <div
          onClick={() => setValidateSymbol(null)}
          style={{
            position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", zIndex: 1000,
            display: "flex", alignItems: "flex-start", justifyContent: "center",
            padding: "3rem 1rem", overflowY: "auto",
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="card animate-fade-in-up"
            style={{ width: "100%", maxWidth: "720px", padding: "1.75rem" }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
              <h2 className="card-title" style={{ margin: 0 }}>
                🔬 Out-of-sample validation — <span style={{ color: "var(--cyan)" }}>{validateSymbol}</span>
              </h2>
              <button className="btn btn-secondary btn-sm" onClick={() => setValidateSymbol(null)}>✕</button>
            </div>

            {validating ? (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "1rem", padding: "3rem" }}>
                <div className="spinner"></div>
                <p className="page-subtitle">Running rolling folds + 2,000 Monte-Carlo paths…</p>
              </div>
            ) : validationError && !wf && !mc ? (
              <div style={{ color: "var(--red)", padding: "1rem" }}>⚠️ {validationError}</div>
            ) : (
              <>
                {validationError && (
                  <div style={{ color: "var(--amber, var(--red))", padding: "0.5rem 1rem", marginBottom: "1rem", fontSize: "0.85rem" }}>
                    ⚠️ {validationError}
                  </div>
                )}
                {/* Walk-forward */}
                {wf && (
                  <div style={{ marginBottom: "1.5rem" }}>
                    <h3 style={{ marginBottom: "0.75rem" }}>
                      Walk-forward{" "}
                      <span className={`badge ${wf.aggregate.consistent ? "badge-active" : ""}`} style={!wf.aggregate.consistent ? { background: "var(--red-glow)", color: "var(--red)" } : {}}>
                        {wf.aggregate.consistent ? "CONSISTENT" : "INCONSISTENT"}
                      </span>
                    </h3>
                    <div className="grid-2" style={{ gap: "0.4rem 2rem", marginBottom: "0.75rem" }}>
                      <Stat label="Profitable folds" value={`${wf.aggregate.pctProfitableFolds}%`} good={wf.aggregate.pctProfitableFolds >= 60} />
                      <Stat label="Mean OOS ROI" value={`${wf.aggregate.meanOosRoi}% ± ${wf.aggregate.stdOosRoi}`} good={wf.aggregate.meanOosRoi > 0} />
                    </div>
                    <div className="table-container">
                      <table className="data-table">
                        <thead><tr><th>Fold</th><th style={{ textAlign: "right" }}>Trades</th><th style={{ textAlign: "right" }}>ROI</th><th style={{ textAlign: "right" }}>Win%</th></tr></thead>
                        <tbody>
                          {wf.folds.map((f) => (
                            <tr key={f.fold}>
                              <td>#{f.fold}</td>
                              <td style={{ textAlign: "right" }}>{f.trades}</td>
                              <td style={{ textAlign: "right" }} className={f.roiPercentage >= 0 ? "positive" : "negative"}>{f.roiPercentage}%</td>
                              <td style={{ textAlign: "right" }}>{f.winRate}%</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Monte-Carlo */}
                {mc && (
                  <div style={{ marginBottom: "1rem" }}>
                    <h3 style={{ marginBottom: "0.75rem" }}>
                      Monte-Carlo{" "}
                      <span className="page-subtitle" style={{ fontSize: "0.8rem" }}>({mc.iterations.toLocaleString()} paths · {mc.tradesSampled} trades)</span>
                    </h3>
                    <div className="grid-2" style={{ gap: "0.4rem 2rem" }}>
                      <Stat label="Probability of profit" value={`${mc.probabilityOfProfit}%`} good={mc.probabilityOfProfit >= 50} />
                      <Stat label="Median ROI (p50)" value={`${mc.roi.p50}%`} good={mc.roi.p50 > 0} />
                      <Stat label="Bad-case ROI (p5)" value={`${mc.roi.p5}%`} good={mc.roi.p5 > 0} />
                      <Stat label="Best-case ROI (p95)" value={`${mc.roi.p95}%`} good={mc.roi.p95 > 0} />
                      <Stat label="Median max drawdown" value={`${mc.maxDrawdownPct.p50}%`} good={false} />
                      <Stat label="Worst drawdown" value={`${mc.maxDrawdownPct.worst}%`} good={false} />
                    </div>
                  </div>
                )}

                {wf && (
                  <p className="page-subtitle" style={{ fontSize: "0.8rem", lineHeight: 1.5, marginBottom: 0 }}>
                    ℹ️ {wf.disclaimer}
                  </p>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, good }: { label: string; value: string; good: boolean }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "0.35rem 0", borderBottom: "1px solid var(--border)" }}>
      <span style={{ color: "var(--text-secondary)" }}>{label}</span>
      <span className={good ? "positive" : "negative"} style={{ fontWeight: 600 }}>{value}</span>
    </div>
  );
}
