import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { API } from '../config';

/**
 * "Which market suits each strategy" for the Backtesting page.
 *
 * From the backtest: how each strategy's trades did in each of the four market
 * conditions (the NIFTY's regime the day before the trade). A strategy is switched off
 * in a condition where it has enough trades and still loses. Nothing is blocked by
 * this: the Portfolio shows the "switch-approved" book beside all trades, and the
 * switch only earns control if that book does better in paper trading.
 */

type Cell = { trades: number; avgR: number | null; approved: boolean | null };
type Row = { strategy: string; bucket: string | null; onRoster: boolean; regimes: Record<string, Cell> };
type Data = { regimes: string[]; minTrades: number; updatedAt: string | null; strategies: Row[] };

const LABEL: Record<string, string> = {
  TRENDING_UP: 'Trending up',
  TRENDING_DOWN: 'Trending down',
  RANGING: 'Flat',
  VOLATILE: 'Volatile',
};
const name = (s: string) => s.replace(/_/g, ' ');
const signed = (v: number) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(2)}R`;

export function SwitchRules() {
  const navigate = useNavigate();
  const [data, setData] = useState<Data | null>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [now, setNow] = useState<string | null>(null);
  const [all, setAll] = useState(false);

  const load = () => {
    setState('loading');
    axios
      .get<Data>(`${API}/api/engine/switch-rules`)
      .then((r) => {
        setData(r.data);
        setState('ready');
      })
      .catch(() => setState('error'));
  };
  useEffect(() => {
    load();
    axios.get(`${API}/api/engine/regime`).then((r) => setNow(r.data?.regime ?? null)).catch(() => setNow(null));
  }, []);

  const rows = data ? (all ? data.strategies : data.strategies.filter((s) => s.onRoster)) : [];
  const offNow = data && now ? data.strategies.filter((s) => s.onRoster && s.regimes[now]?.approved === false) : [];

  return (
    <section className="card lc-card" aria-labelledby="sw-title">
      <div className="lc-head">
        <div>
          <h2 className="card-title lc-title" id="sw-title">Which market suits each strategy</h2>
          <p className="lc-lead">
            Each backtest trade is sorted by what the market was doing the day before it was taken. Where a
            strategy has plenty of trades in one kind of market and still loses there, it is marked off for
            that market.
          </p>
        </div>
      </div>

      {state === 'loading' && (
        <div className="sc-skeleton" aria-hidden="true">
          {Array.from({ length: 4 }, (_, i) => (
            <div key={i} className="sc-skeleton-row">
              <span className="skeleton-loader" style={{ width: '24%' }} />
              <span className="skeleton-loader" style={{ width: '14%' }} />
              <span className="skeleton-loader" style={{ width: '14%' }} />
              <span className="skeleton-loader" style={{ width: '14%' }} />
            </div>
          ))}
        </div>
      )}

      {state === 'error' && (
        <div className="lc-empty" role="alert">
          <p>This could not be loaded.</p>
          <button className="btn btn-secondary lc-btn" onClick={load}>Try again</button>
        </div>
      )}

      {state === 'ready' && data && data.strategies.length === 0 && (
        <div className="lc-empty">
          <p>No rules yet. They are worked out after the market closes each trading day, with the luck check.</p>
        </div>
      )}

      {state === 'ready' && data && data.strategies.length > 0 && (
        <>
          <p className="lc-verdict">
            {now ? `The market is ${LABEL[now]?.toLowerCase() ?? now} today. ` : ''}
            {now &&
              (offNow.length
                ? `Marked off in this market: ${offNow.map((s) => name(s.strategy)).join(', ')}.`
                : 'No strategy on the roster is marked off in this market.')}{' '}
            <span className="lc-verdict-note">
              Nothing is blocked. The Portfolio shows the switch-approved trades beside all trades; the switch
              only gets control if its book does better.
            </span>
          </p>

          <div className="table-wrapper sc-table">
            <table>
              <thead>
                <tr>
                  <th>Strategy</th>
                  {data.regimes.map((g) => (
                    <th key={g} className="sc-num">{LABEL[g] ?? g}{g === now ? ' (now)' : ''}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((s) => (
                  <tr key={s.strategy}>
                    <td data-label="Strategy">
                      <button className="sc-linkbtn lc-strategy" onClick={() => navigate(`/backtesting/${s.strategy}`)}>
                        {name(s.strategy)}
                      </button>
                      <div className="sc-sub">{s.bucket === 'INTRADAY' ? 'Intraday' : 'Swing'}{s.onRoster ? '' : ', not on the roster'}</div>
                    </td>
                    {data.regimes.map((g) => {
                      const c = s.regimes[g];
                      const tone = c.approved === false ? 'paused' : c.approved === true ? 'proven' : 'testing';
                      const text = c.approved === false ? 'Off' : c.approved === true ? 'On' : 'Too few trades';
                      return (
                        <td key={g} data-label={`${LABEL[g] ?? g}${g === now ? ' (now)' : ''}`} className="sc-num">
                          <span className={`badge sc-status ${tone}`}>{text}</span>
                          <div className="sc-sub mono">
                            {c.avgR === null ? 'no trades' : `${signed(c.avgR)} · ${c.trades.toLocaleString('en-IN')} trades`}
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="lc-foot">
            <button className="sc-linkbtn" onClick={() => setAll((v) => !v)} aria-expanded={all}>
              {all ? 'Show only strategies on the roster' : `Show all ${data.strategies.length} strategies`}
            </button>
            <p className="lc-meta">
              "Off" needs at least {data.minTrades} backtest trades in that market with an average at or below
              zero. These rules come from the same history they are judged on, so they flatter themselves;
              that is why they are tested in paper before they are trusted
              {data.updatedAt && `. Last worked out ${new Date(data.updatedAt).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })}`}.
            </p>
          </div>
        </>
      )}
    </section>
  );
}
