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

  return (
    <div className="page animate-fade-in">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '2rem' }}>
        <div>
          <h1 className="page-title">Backtesting Hub</h1>
          <p className="page-subtitle">Test predefined strategies against the entire stock database</p>
        </div>
        {leaders.length > 0 && (
          <button className="btn btn-secondary" onClick={() => setShowBoard((s) => !s)}>
            {showBoard ? 'Hide' : 'Show'} 🏆 Leaderboard
          </button>
        )}
      </div>

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
