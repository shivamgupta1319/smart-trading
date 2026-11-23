import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { API } from '../config';
import { LuckCheck } from '../components/LuckCheck';

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
  const [autoStage, setAutoStage] = useState<string | null>(null);
  const autoChecked = useRef(false);

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
      'Auto-select gets the latest prices, backtests every strategy on every stock, and ADDS every pair ' +
        'that meets the live rule to the roster. Pairs already on the roster are left as they are; ' +
        'nothing is removed. It takes a few minutes and runs in the background. Continue?',
    );

    if (!ok) return;
    setAutoRunning(true);
    setAutoError(null);
    setAutoResult(null);
    setAutoStage(null);
    try {
      // The run takes several minutes, so this only starts it; followAutoSelect polls.
      const res = await axios.post(`${API}/api/engine/auto-select`, { clearExisting: false });
      applyAutoJob(res.data);
    } catch (e: any) {
      setAutoError(e.response?.data?.message || e.response?.data?.detail || e.message || 'Auto-select could not be started.');
      setAutoRunning(false);
    }
  };

  /** Show what a job says and report whether it is still running. */
  const applyAutoJob = (job: any): boolean => {
    if (job?.status === 'running') {
      setAutoRunning(true);
      setAutoStage(job.total > 0 ? `${job.stage}: ${job.done} of ${job.total}` : job.stage || 'Starting');
      return true;
    }
    setAutoRunning(false);
    setAutoStage(null);
    if (job?.status === 'done') setAutoResult(job.result);
    if (job?.status === 'failed') setAutoError(`Auto-select stopped: ${job.error || 'unknown reason'}`);
    return false;
  };

  // While a run is in progress, ask the engine how far it is every few seconds. This
  // also picks a run back up after the page is reloaded.
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let misses = 0;
    const poll = async (first: boolean) => {
      try {
        const res = await axios.get(`${API}/api/engine/auto-select/status`);
        if (!alive) return;
        misses = 0;
        const job = res.data;
        // On first load only a run in progress is shown; an old finished run is not.
        const running = first && job?.status !== 'running' ? false : applyAutoJob(job);
        if (running) timer = setTimeout(() => poll(false), 3000);
      } catch {
        if (!alive) return;
        misses += 1;
        if (misses < 5) timer = setTimeout(() => poll(false), 5000);
        else if (!first) {
          setAutoRunning(false);
          setAutoError('Lost contact with the server while auto-select was running. Reload the page to see where it stands.');
        }
      }
    };
    if (autoRunning || !autoChecked.current) {
      const first = !autoChecked.current;
      autoChecked.current = true;
      poll(first);
    }
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- restart polling only when a run starts or stops
  }, [autoRunning]);

  return (
    <div className="page animate-fade-in">
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '2rem' }}>
        <div style={{ minWidth: 0 }}>
          <h1 className="page-title">Backtesting Hub</h1>
          <p className="page-subtitle">Test predefined strategies against the entire stock database</p>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem' }}>
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

      <LuckCheck />

      {(autoRunning || autoResult || autoError) && (
        <div className="card animate-fade-in-up" style={{ padding: '1.5rem', marginBottom: '2rem', borderTop: '4px solid var(--cyan)' }}>
          <h2 className="card-title" style={{ marginTop: 0 }}>Auto-select: every pair that meets the live rule</h2>
          {autoRunning && (
            <p className="page-subtitle" style={{ marginTop: 0 }} role="status">
              <strong style={{ color: 'var(--text-primary)' }}>{autoStage || 'Starting'}.</strong>{' '}
              It gets the latest prices, tests every strategy on every stock, then checks the survivors again. This
              takes several minutes and keeps running if you leave the page.
            </p>
          )}
          {autoError && <div style={{ color: 'var(--red)' }}>⚠️ {autoError}</div>}
          {autoResult && (
            <>
              <p className="page-subtitle" style={{ marginTop: 0 }}>
                {typeof autoResult.stocksRefreshed === 'number' && (
                  <>Refreshed data for <strong>{autoResult.stocksRefreshed}</strong> stocks. </>
                )}
                Promoted <strong>{autoResult.totalPicks}</strong> (stock × strategy) cells across{' '}
                <strong>{autoResult.strategiesEvaluated}</strong> strategies — added{' '}
                <strong>{autoResult.written}</strong> new, kept existing
                {typeof autoResult.skipped === 'number' && autoResult.skipped > 0 && (
                  <> (skipped <strong>{autoResult.skipped}</strong> already active)</>
                )}
                . Every pick meets the live rule: average per trade above +{autoResult.rule?.minAvgR}R, positive in
                both halves, at least {autoResult.rule?.minTradesSwing} trades ({autoResult.rule?.minTradesIntraday}{' '}
                for intraday), profit factor {autoResult.rule?.minProfitFactor}, profit at least{' '}
                {autoResult.rule?.minProfitToDrawdown} times the worst drawdown and a total return of{' '}
                {autoResult.rule?.minRoiPct}%.
              </p>
              <div className="table-container">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Strategy</th>
                      <th>Stocks that meet the rule</th>
                      <th style={{ textAlign: 'right' }}>Count</th>
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
                  No stock and strategy pair meets the live rule right now.
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
