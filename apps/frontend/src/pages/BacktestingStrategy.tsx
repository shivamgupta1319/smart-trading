import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import axios from "axios";

const API = "http://localhost:3000";

interface BacktestStockResult {
  symbol: string;
  metrics: {
    winRate: number;
    totalTrades: number;
    maxDrawdown: number;
    netProfit: number;
    roiPercentage: number;
  };
}

export function BacktestingStrategy() {
  const { strategyName } = useParams<{ strategyName: string }>();
  const navigate = useNavigate();
  const [results, setResults] = useState<BacktestStockResult[]>([]);
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState<{ type: string; text: string } | null>(
    null,
  );

  const showMessage = (type: string, text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 4000);
  };

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
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => navigate(`/stock/${r.symbol}`)}
                      >
                        View Stock
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
