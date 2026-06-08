import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { API } from '../config';

interface Strategy {
  name: string;
  timeframe: string;
  holdDuration: string;
}

interface LeaderRow {
  strategy: string;
  reports: number;
  avgWinRate: number;
  avgRoi: number;
  avgMaxDrawdownPct: number;
  avgTrades: number;
  totalNetProfit: number;
  riskAdjustedScore: number;
}

const HOLD_LABELS: Record<string, { label: string; color: string }> = {
  INTRADAY: { label: 'Intraday', color: 'var(--cyan)' },
  SHORT_SWING: { label: 'Short Swing', color: 'var(--yellow)' },
  MID_SWING: { label: 'Mid Swing', color: 'var(--purple)' },
  LONG_POSITIONAL: { label: 'Long Positional', color: '#60a5fa' },
};

export function Backtesting() {
  const navigate = useNavigate();
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [leaders, setLeaders] = useState<LeaderRow[]>([]);
  const [showBoard, setShowBoard] = useState(true);
  const [autoRunning, setAutoRunning] = useState(false);
  const [autoResult, setAutoResult] = useState<any | null>(null);
  const [autoError, setAutoError] = useState<string | null>(null);

  useEffect(() => {
    fetchStrategies();
    axios
      .get(`${API}/api/engine/leaderboard`)
      .then((r) => setLeaders(r.data.leaderboard || []))
      .catch(() => setLeaders([]));
  }, []);

  const fetchStrategies = async () => {
    try {
      setLoading(true);
      const res = await axios.get(`${API}/api/engine/strategies`);
      setStrategies(res.data || []);
      setError(null);
    } catch (e: any) {
      setError(e.response?.data?.message || e.message || 'Failed to fetch strategies');
    } finally {
      setLoading(false);
    }
  };

  const runAutoSelect = async () => {
    const ok = window.confirm(
      'Auto-select backtests every strategy against every stock with data, runs walk-forward + ' +
        'Monte-Carlo on survivors, and REPLACES your active (stock × strategy) configs with the ' +
        'top picks. This can take several minutes. Continue?',
    );
    if (!ok) return;
    setAutoRunning(true);
    setAutoError(null);
    setAutoResult(null);
    try {
      const res = await axios.post(`${API}/api/engine/auto-select`, { clearExisting: true });
      setAutoResult(res.data);
    } catch (e: any) {
      setAutoError(e.response?.data?.message || e.response?.data?.detail || e.message || 'Auto-select failed.');
    } finally {
      setAutoRunning(false);
    }
  };

  return (
    <div className="page animate-fade-in">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '2rem' }}>
        <div>
          <h1 className="page-title">Backtesting Hub</h1>
          <p className="page-subtitle">Test predefined strategies against the entire stock database</p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button className="btn btn-primary" onClick={runAutoSelect} disabled={autoRunning}>
            {autoRunning ? '⏳ Selecting…' : '✨ Auto-select stocks'}
          </button>
          {leaders.length > 0 && (
            <button className="btn btn-secondary" onClick={() => setShowBoard((s) => !s)}>
              {showBoard ? 'Hide' : 'Show'} 🏆 Leaderboard
            </button>
          )}
        </div>
      </div>

      {(autoRunning || autoResult || autoError) && (
        <div className="card animate-fade-in-up" style={{ padding: '1.5rem', marginBottom: '2rem', borderTop: '4px solid var(--cyan)' }}>
          <h2 className="card-title" style={{ marginTop: 0 }}>✨ Auto-select (strict, quality-first)</h2>
          {autoRunning && (
            <p className="page-subtitle" style={{ marginTop: 0 }}>
              Backtesting every strategy × stock, then walk-forward + Monte-Carlo on survivors. This can take a few minutes…
            </p>
          )}
          {autoError && <div style={{ color: 'var(--red)' }}>⚠️ {autoError}</div>}
          {autoResult && (
            <>
              <p className="page-subtitle" style={{ marginTop: 0 }}>
                Promoted <strong>{autoResult.totalPicks}</strong> (stock × strategy) cells across{' '}
                <strong>{autoResult.strategiesEvaluated}</strong> strategies. Gates: ≥{autoResult.gates?.minTrades} trades,
                ROI&gt;{autoResult.gates?.minRoiPct}%, PF≥{autoResult.gates?.minProfitFactor}, DD≤{autoResult.gates?.maxDrawdownPct}%,
                walk-forward consistent, positive Monte-Carlo p5.
              </p>
              <div className="table-container">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Strategy</th>
                      <th>Picks (top by risk-adj score)</th>
                      <th style={{ textAlign: 'right' }}>Passed gates</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(autoResult.summary || [])
                      .filter((s: any) => s.picked?.length)
                      .map((s: any) => (
                        <tr key={s.strategy}>
                          <td><span style={{ fontWeight: 600, color: 'var(--cyan)' }}>{s.strategy.replace(/_/g, ' ')}</span></td>
                          <td>
                            {s.picked.map((p: any) => (
                              <span key={p.symbol} className="badge" style={{ marginRight: '0.4rem' }}>
                                {p.symbol} · {p.roiPercentage}% · DD {p.maxDrawdownPct}% · R/DD {p.returnDdRatio}×
                              </span>
                            ))}
                          </td>
                          <td style={{ textAlign: 'right' }}>{s.passedGates}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
              {(autoResult.summary || []).every((s: any) => !s.picked?.length) && (
                <p style={{ color: 'var(--text-secondary)' }}>
                  No (stock × strategy) cell passed the strict gates. Ensure history is fetched for your stocks, or loosen the gates.
                </p>
              )}
            </>
          )}
        </div>
      )}

      {showBoard && leaders.length > 0 && (
        <div className="card animate-fade-in-up" style={{ padding: '1.5rem', marginBottom: '2rem' }}>
          <h2 className="card-title" style={{ marginTop: 0 }}>🏆 Risk-Adjusted Leaderboard</h2>
          <p className="page-subtitle" style={{ marginTop: 0 }}>
            Ranked by <strong>ROI ÷ max-drawdown</strong> (× sample confidence) across stored backtests — not raw ROI.
          </p>
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Strategy</th>
                  <th style={{ textAlign: 'right' }}>Score</th>
                  <th style={{ textAlign: 'right' }}>Avg ROI</th>
                  <th style={{ textAlign: 'right' }}>Avg DD%</th>
                  <th style={{ textAlign: 'right' }}>Win%</th>
                  <th style={{ textAlign: 'right' }}>Reports</th>
                </tr>
              </thead>
              <tbody>
                {leaders.slice(0, 10).map((l, i) => (
                  <tr key={l.strategy} style={{ cursor: 'pointer' }} onClick={() => navigate(`/backtesting/${l.strategy}`)}>
                    <td>{i + 1}</td>
                    <td><span style={{ fontWeight: 600, color: 'var(--cyan)' }}>{l.strategy.replace(/_/g, ' ')}</span></td>
                    <td style={{ textAlign: 'right' }} className={l.riskAdjustedScore >= 0 ? 'positive' : 'negative'}>{l.riskAdjustedScore}</td>
                    <td style={{ textAlign: 'right' }} className={l.avgRoi >= 0 ? 'positive' : 'negative'}>{l.avgRoi}%</td>
                    <td style={{ textAlign: 'right' }}>{l.avgMaxDrawdownPct}%</td>
                    <td style={{ textAlign: 'right' }}>{l.avgWinRate}%</td>
                    <td style={{ textAlign: 'right' }}>{l.reports}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '4rem' }}>
          <div className="spinner"></div>
        </div>
      ) : error ? (
        <div className="card" style={{ padding: '2rem', textAlign: 'center' }}>
          <p style={{ color: 'var(--danger)' }}>{error}</p>
          <button className="btn btn-secondary mt-1" onClick={fetchStrategies}>Retry</button>
        </div>
      ) : (
        <div className="grid-3">
          {strategies.map((str, idx) => {
            const hold = HOLD_LABELS[str.holdDuration] || { label: str.holdDuration, color: 'var(--text-muted)' };
            return (
              <div
                key={idx}
                className="card"
                role="button"
                tabIndex={0}
                aria-label={`Backtest ${str.name.replace(/_/g, ' ')}`}
                style={{ cursor: 'pointer', transition: 'transform 0.2s', display: 'flex', flexDirection: 'column', gap: '1rem' }}
                onClick={() => navigate(`/backtesting/${str.name}`)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(`/backtesting/${str.name}`); } }}
                onMouseEnter={(e) => e.currentTarget.style.transform = 'translateY(-4px)'}
                onMouseLeave={(e) => e.currentTarget.style.transform = 'translateY(0)'}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <h3 className="card-title" style={{ margin: 0, fontSize: '1.25rem', color: 'var(--cyan)' }}>
                    {str.name.replace(/_/g, ' ')}
                  </h3>
                  <span className="badge badge-active">{str.timeframe}</span>
                </div>
                
                <div>
                  <span className="badge" style={{ background: `${hold.color}20`, color: hold.color, border: `1px solid ${hold.color}40`, marginBottom: '1rem', display: 'inline-block' }}>
                    {hold.label}
                  </span>
                  <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', margin: 0 }}>
                    Click to run this strategy against all available stocks and identify top performers.
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
