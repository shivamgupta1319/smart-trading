import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { API } from '../config';

/**
 * "Where each strategy works" for the Backtesting page.
 *
 * For every strategy: on how many stocks it was tested, on how many it was profitable,
 * and which stocks meet the live rule. That answers two questions: which strategies
 * work across most stocks, and which only suit particular ones. Turned round with the
 * search box it answers a third: what suits this stock.
 */

type Meets = { symbol: string; avgR: number | null; trades: number; roiPct: number };
type Row = {
  strategy: string;
  bucket: string | null;
  tested: number;
  profitable: number;
  medianAvgR: number | null;
  passesLuck: boolean | null;
  meets: Meets[];
  verdict: 'Works broadly' | 'Works on some stocks' | 'No stock meets the rule';
};
type MapData = { stocks: number; intradayStocks: number; updatedAt: string | null; broadShare: number; strategies: Row[] };

const TONE: Record<Row['verdict'], string> = {
  'Works broadly': 'proven',
  'Works on some stocks': 'paused',
  'No stock meets the rule': 'testing',
};
const name = (s: string) => s.replace(/_/g, ' ');
const kind = (bucket: string | null) => (bucket === 'INTRADAY' ? 'Intraday' : 'Swing');

export function StrategyMap() {
  const navigate = useNavigate();
  const [map, setMap] = useState<MapData | null>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [open, setOpen] = useState<string | null>(null);
  const [query, setQuery] = useState('');

  const load = () => {
    setState('loading');
    axios
      .get<MapData>(`${API}/api/engine/strategy-map`)
      .then((r) => {
        setMap(r.data);
        setState('ready');
      })
      .catch(() => setState('error'));
  };
  useEffect(load, []);

  // What suits one stock: the strategies whose backtest on it meets the live rule.
  const q = query.trim().toUpperCase();
  const forStock = useMemo(() => {
    if (!map || q.length < 2) return null;
    const hits = new Map<string, { strategy: string; m: Meets }[]>();
    for (const s of map.strategies) {
      for (const m of s.meets) {
        if (!m.symbol.includes(q)) continue;
        hits.set(m.symbol, [...(hits.get(m.symbol) ?? []), { strategy: s.strategy, m }]);
      }
    }
    return [...hits.entries()].sort((a, b) => a[0].localeCompare(b[0])).slice(0, 12);
  }, [map, q]);

  const counts = useMemo(() => {
    const c = { broad: 0, some: 0, none: 0, pairs: 0 };
    for (const s of map?.strategies ?? []) {
      if (s.verdict === 'Works broadly') c.broad += 1;
      else if (s.verdict === 'Works on some stocks') c.some += 1;
      else c.none += 1;
      c.pairs += s.meets.length;
    }
    return c;
  }, [map]);

  return (
    <section className="card lc-card" aria-labelledby="sm-title">
      <div className="lc-head">
        <div>
          <h2 className="card-title lc-title" id="sm-title">Where each strategy works</h2>
          <p className="lc-lead">
            Every strategy is backtested on every stock on its list. A strategy that is profitable on most
            of them has a general edge; one that only passes on a few stocks may just have been lucky there.
          </p>
        </div>
        <label className="sc-field">
          <span className="sc-field-label">What suits a stock?</span>
          <input
            className="form-input"
            style={{ minHeight: 44, fontSize: '1rem', minWidth: '12rem' }}
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. RELIANCE"
          />
        </label>
      </div>

      {state === 'loading' && (
        <div className="sc-skeleton" aria-hidden="true">
          {Array.from({ length: 4 }, (_, i) => (
            <div key={i} className="sc-skeleton-row">
              <span className="skeleton-loader" style={{ width: '24%' }} />
              <span className="skeleton-loader" style={{ width: '14%' }} />
              <span className="skeleton-loader" style={{ width: '14%' }} />
              <span className="skeleton-loader" style={{ width: '22%' }} />
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

      {state === 'ready' && map && (
        <>
          <p className="lc-verdict">
            {counts.broad} {counts.broad === 1 ? 'strategy works' : 'strategies work'} broadly, {counts.some} on some
            stocks only, {counts.none} nowhere.{' '}
            <span className="lc-verdict-note">
              {counts.pairs} stock and strategy pairs meet the live rule, from {map.stocks} stocks ({map.intradayStocks}{' '}
              on the intraday list).
            </span>
          </p>

          {forStock && (
            <div className="sm-stock" aria-live="polite">
              {forStock.length === 0 ? (
                <p className="lc-meta">No stock matching "{query}" has a strategy that meets the live rule.</p>
              ) : (
                forStock.map(([symbol, hits]) => (
                  <p key={symbol} className="sm-stock-row">
                    <button className="sc-linkbtn lc-strategy" onClick={() => navigate(`/stock/${symbol}`)}>{symbol}</button>
                    <span className="lc-meta">
                      {hits.map((h) => `${name(h.strategy)} (${h.m.trades} trades, ${h.m.roiPct >= 0 ? '+' : ''}${h.m.roiPct}%)`).join(', ')}
                    </span>
                  </p>
                ))
              )}
            </div>
          )}

          <div className="table-wrapper sc-table">
            <table>
              <thead>
                <tr>
                  <th>Strategy</th>
                  <th className="sc-num">Stocks tested</th>
                  <th className="sc-num">Profitable on</th>
                  <th className="sc-num">Meet the live rule</th>
                  <th>Verdict</th>
                </tr>
              </thead>
              <tbody>
                {map.strategies.map((s) => {
                  const share = s.tested ? Math.round((100 * s.profitable) / s.tested) : 0;
                  const isOpen = open === s.strategy;
                  return (
                    <tr key={s.strategy}>
                      <td data-label="Strategy">
                        <button className="sc-linkbtn lc-strategy" onClick={() => navigate(`/backtesting/${s.strategy}`)}>
                          {name(s.strategy)}
                        </button>
                        <div className="sc-sub">
                          {kind(s.bucket)}
                          {s.bucket !== 'INTRADAY' && s.passesLuck === false && ', fails the luck check'}
                        </div>
                      </td>
                      <td data-label="Stocks tested" className="sc-num"><span className="mono">{s.tested}</span></td>
                      <td data-label="Profitable on" className="sc-num">
                        <span className="mono">{s.tested ? `${s.profitable} (${share}%)` : '—'}</span>
                      </td>
                      <td data-label="Meet the live rule" className="sc-num">
                        {s.meets.length === 0 ? (
                          <span className="mono">0</span>
                        ) : (
                          <button className="sc-linkbtn" aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : s.strategy)}>
                            {s.meets.length} {s.meets.length === 1 ? 'stock' : 'stocks'}: {isOpen ? 'hide' : 'show'}
                          </button>
                        )}
                        {isOpen && (
                          <div className="sm-chips">
                            {s.meets.map((m) => (
                              <button key={m.symbol} className="sm-chip" onClick={() => navigate(`/stock/${m.symbol}`)} title={`${m.trades} trades, ${m.roiPct}% total`}>
                                {m.symbol}
                              </button>
                            ))}
                          </div>
                        )}
                      </td>
                      <td data-label="Verdict"><span className={`badge sc-status ${TONE[s.verdict]}`}>{s.verdict}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <p className="lc-meta" style={{ marginTop: '1rem' }}>
            "Works broadly" means profitable on at least {Math.round(map.broadShare * 100)}% of the stocks it was
            tested on, with at least one stock meeting the live rule. Figures are backtests after costs
            {map.updatedAt && `, last refreshed ${new Date(map.updatedAt).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })}`}.
            A pair that meets the rule still has to prove itself in paper trading.
          </p>
        </>
      )}
    </section>
  );
}
