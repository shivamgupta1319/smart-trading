import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { API } from '../config';

/**
 * "Is any of it more than luck?" for the Backtesting page.
 *
 * Many strategies are backtested together, so some look good by chance. The engine
 * works out, per strategy, how likely its result is with no real edge (corrected for
 * the number tested) and applies a stricter test against every try on record. This card
 * shows the stored result and lets the owner run it again.
 */

type Row = {
  strategy: string;
  bucket: string | null;
  cells: number;
  trades: number;
  avg_r: number | null;
  q_value: number | null;
  deflated_sharpe: number | null;
  stands_out: boolean;
};

type Run = {
  computedAt: string;
  engineVersion: string;
  stocks: number;
  trials: number;
  strategies: number;
  fdrQ: number;
  dsrThreshold: number;
  standOut: string[];
  rows: Row[];
};

const KIND: Record<string, string> = {
  INTRADAY: 'Intraday',
  SHORT_SWING: 'Swing, short',
  MID_SWING: 'Swing, medium',
  LONG_POSITIONAL: 'Swing, long',
};

const name = (s: string) => s.replace(/_/g, ' ');
const signed = (v: number) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(2)}R`;

function chance(q: number | null): string {
  if (q === null) return 'Too few trades';
  if (q < 0.001) return 'Under 0.1%';
  if (q >= 0.995) return 'About 100%';
  return `${(q * 100).toFixed(q < 0.1 ? 1 : 0)}%`;
}

function verdict(row: Row, run: Run): { text: string; tone: 'proven' | 'testing' | 'paused' } {
  if (row.stands_out) return { text: 'Stands out', tone: 'proven' };
  const first = (row.avg_r ?? 0) > 0 && row.q_value !== null && row.q_value <= run.fdrQ;
  if (first) return { text: 'Passes the first test only', tone: 'paused' };
  return { text: 'Could be luck', tone: 'testing' };
}

function message(e: unknown, fallback: string): string {
  if (axios.isAxiosError(e)) {
    const body = e.response?.data as { message?: string; detail?: string } | undefined;
    return body?.detail || body?.message || fallback;
  }
  return fallback;
}

export function LuckCheck() {
  const navigate = useNavigate();
  const [run, setRun] = useState<Run | null>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const [showAll, setShowAll] = useState(false);

  const load = useCallback(async () => {
    setState('loading');
    try {
      const res = await axios.get<{ run: Run | null }>(`${API}/api/engine/luck-check`);
      setRun(res.data.run);
      setError(null);
      setState('ready');
    } catch (e) {
      setError(message(e, 'The luck check could not be loaded.'));
      setState('error');
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const checkAgain = async () => {
    setChecking(true);
    setError(null);
    try {
      const res = await axios.post<{ run: Run }>(`${API}/api/engine/luck-check/run`, {}, { timeout: 600000 });
      setRun(res.data.run);
      setState('ready');
    } catch (e) {
      setError(message(e, 'The check did not finish. Try again.'));
    } finally {
      setChecking(false);
    }
  };

  const positive = run ? run.rows.filter((r) => (r.avg_r ?? 0) > 0) : [];
  const rows = run ? (showAll ? run.rows : positive) : [];

  return (
    <section className="card lc-card" aria-labelledby="lc-title">
      <div className="lc-head">
        <div>
          <h2 className="card-title lc-title" id="lc-title">Is any of it more than luck?</h2>
          <p className="lc-lead">
            When many strategies are tested together, some look good by chance. This check works out how
            likely each result is with no real edge, and holds the best one against every try on record.
          </p>
        </div>
        <button className="btn btn-secondary lc-btn" onClick={checkAgain} disabled={checking || state === 'loading'}>
          {checking ? 'Checking… about a minute' : run ? 'Check again' : 'Run the check'}
        </button>
      </div>

      <div aria-live="polite">
        {error && state !== 'error' && <p className="sc-error" role="alert">{error}</p>}
      </div>

      {state === 'loading' && (
        <div className="sc-skeleton" aria-hidden="true">
          {Array.from({ length: 4 }, (_, i) => (
            <div key={i} className="sc-skeleton-row">
              <span className="skeleton-loader" style={{ width: '26%' }} />
              <span className="skeleton-loader" style={{ width: '14%' }} />
              <span className="skeleton-loader" style={{ width: '18%' }} />
              <span className="skeleton-loader" style={{ width: '20%' }} />
            </div>
          ))}
        </div>
      )}

      {state === 'error' && (
        <div className="lc-empty" role="alert">
          <p>{error}</p>
          <button className="btn btn-secondary lc-btn" onClick={load}>Try again</button>
        </div>
      )}

      {state === 'ready' && !run && (
        <div className="lc-empty">
          <p>
            The check has not been run yet. It backtests every strategy on every stock, which takes about a
            minute. After that it refreshes by itself each trading day after the market closes.
          </p>
        </div>
      )}

      {state === 'ready' && run && (
        <>
          <p className={`lc-verdict ${run.standOut.length ? 'good' : ''}`}>
            {run.standOut.length
              ? `Stands out beyond luck: ${run.standOut.map(name).join(', ')}.`
              : 'No strategy stands out beyond luck yet.'}{' '}
            <span className="lc-verdict-note">
              {positive.length} of {run.strategies} have a positive average after costs. A backtest row that
              looks good is a reason to watch a strategy in paper trading, not proof.
            </span>
          </p>

          {rows.length > 0 && (
            <div className="table-wrapper sc-table">
              <table>
                <thead>
                  <tr>
                    <th>Strategy</th>
                    <th className="sc-num">Trades</th>
                    <th className="sc-num">Average per trade</th>
                    <th className="sc-num">Chance this is luck</th>
                    <th className="sc-num">Stricter test (needs {run.dsrThreshold})</th>
                    <th>Verdict</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => {
                    const v = verdict(r, run);
                    return (
                      <tr key={r.strategy}>
                        <td data-label="Strategy">
                          <button className="sc-linkbtn lc-strategy" onClick={() => navigate(`/backtesting/${r.strategy}`)}>
                            {name(r.strategy)}
                          </button>
                          <div className="sc-sub">
                            {KIND[r.bucket ?? ''] ?? 'Other'}, {r.cells} stocks
                          </div>
                        </td>
                        <td data-label="Trades" className="sc-num">
                          <span className="mono">{r.trades.toLocaleString('en-IN')}</span>
                        </td>
                        <td data-label="Average per trade" className="sc-num">
                          <span className={`mono ${(r.avg_r ?? 0) > 0 ? 'positive' : (r.avg_r ?? 0) < 0 ? 'negative' : ''}`}>
                            {r.avg_r === null ? '—' : signed(r.avg_r)}
                          </span>
                        </td>
                        <td data-label="Chance this is luck" className="sc-num">
                          <span className="mono">{chance(r.q_value)}</span>
                        </td>
                        <td data-label={`Stricter test (needs ${run.dsrThreshold})`} className="sc-num">
                          <span className="mono">{r.deflated_sharpe === null ? '—' : r.deflated_sharpe.toFixed(2)}</span>
                        </td>
                        <td data-label="Verdict">
                          <span className={`badge sc-status ${v.tone}`}>{v.text}</span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          <div className="lc-foot">
            <button className="sc-linkbtn" onClick={() => setShowAll((s) => !s)} aria-expanded={showAll}>
              {showAll
                ? 'Show only strategies with a positive average'
                : `Show all ${run.strategies} strategies (${run.strategies - positive.length} lose after costs)`}
            </button>
            <p className="lc-meta">
              Checked {new Date(run.computedAt).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })} on{' '}
              {run.stocks} stocks. {run.trials} tries on record. "Chance this is luck" is corrected for testing{' '}
              {run.strategies} strategies at once; under {Math.round(run.fdrQ * 100)}% passes the first test.
            </p>
          </div>
        </>
      )}
    </section>
  );
}
