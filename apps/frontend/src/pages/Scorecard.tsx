import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';
import { API_URL } from '../config';

type Status = 'TESTING' | 'PROVEN' | 'PAUSED';

interface LiveStats {
  trades: number;
  wins: number;
  winRate: number | null;
  netPnl: number;
  avgR: number | null;
  profitFactor: number | null;
  firstHalfR: number | null;
  secondHalfR: number | null;
}

interface Cell {
  id: number;
  symbol: string;
  dataFlag: string | null;
  dataFlagDetail: string | null;
  strategyName: string;
  timeframe: string;
  status: Status;
  statusReason: string | null;
  statusChangedAt: string | null;
  openTrades: number;
  live: LiveStats;
  mainBook: { trades: number; netPnl: number };
  testBook: { trades: number; netPnl: number };
  backtest: { trades: number; winRate: number; avgR: number | null; profitFactor: number | null } | null;
}

type Filter = 'ALL' | Status;
type SortKey = 'evidence' | 'liveR' | 'trades' | 'pnl' | 'gap' | 'name';

// Proven first, paused last; inside a status, the cell with the most trades leads.
const STATUS_RANK: Record<Status, number> = { PROVEN: 0, TESTING: 1, PAUSED: 2 };

const STATUS_LABEL: Record<Status, string> = { TESTING: 'Testing', PROVEN: 'Proven', PAUSED: 'Paused' };
const STATUS_HELP: Record<Status, string> = {
  TESTING: 'Still collecting paper trades',
  PROVEN: '40+ trades, profitable after costs in both halves',
  PAUSED: 'Kept losing. Still paper-trades, but only in the test book',
};

const rupees = (n: number) =>
  `${n < 0 ? '−' : ''}₹${Math.abs(Math.round(n)).toLocaleString('en-IN')}`;
const signedR = (r: number | null) => (r === null ? '–' : `${r > 0 ? '+' : r < 0 ? '−' : ''}${Math.abs(r).toFixed(2)}R`);
const tone = (n: number | null) => (n === null || n === 0 ? 'flat' : n > 0 ? 'up' : 'down');

/**
 * Live result against the backtest's promise, on one −1R…+1R scale.
 * Filled dot = live paper trades (after costs). Hollow marker = backtest.
 */
function PromiseGauge({ live, backtest }: { live: number | null; backtest: number | null }) {
  const pos = (r: number) => `${((Math.max(-1, Math.min(1, r)) + 1) / 2) * 100}%`;
  const both = live !== null && backtest !== null;
  const label =
    live === null
      ? `No live trades yet. Backtest ${signedR(backtest)}`
      : `Live ${signedR(live)}, backtest ${signedR(backtest)}`;
  return (
    <div className="sc-gauge" role="img" aria-label={label}>
      <div className="sc-gauge-track">
        <span className="sc-gauge-zero" />
        {both && (
          <span
            className={`sc-gauge-link ${live! >= backtest! ? 'up' : 'down'}`}
            style={{
              left: pos(Math.min(live!, backtest!)),
              right: `calc(100% - ${pos(Math.max(live!, backtest!))})`,
            }}
          />
        )}
        {backtest !== null && <span className="sc-gauge-bt" style={{ left: pos(backtest) }} />}
        {live !== null && <span className={`sc-gauge-live ${tone(live)}`} style={{ left: pos(live) }} />}
      </div>
      <div className="sc-gauge-figures mono">
        <span className={`sc-fig ${tone(live)}`}>{live === null ? 'no trades' : signedR(live)}</span>
        <span className="sc-fig-bt">backtest {signedR(backtest)}</span>
      </div>
    </div>
  );
}

function SkeletonRows() {
  return (
    <div className="sc-skeleton" aria-hidden="true">
      {Array.from({ length: 6 }, (_, i) => (
        <div key={i} className="sc-skeleton-row">
          <span className="skeleton-loader" style={{ width: '22%' }} />
          <span className="skeleton-loader" style={{ width: '12%' }} />
          <span className="skeleton-loader" style={{ width: '30%' }} />
          <span className="skeleton-loader" style={{ width: '14%' }} />
        </div>
      ))}
    </div>
  );
}

export function Scorecard() {
  const [cells, setCells] = useState<Cell[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>('ALL');
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<SortKey>('evidence');
  const [checking, setChecking] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await axios.get<Cell[]>(`${API_URL}/configs/scorecard`);
      setCells(res.data);
      setError(null);
    } catch {
      setError('The scorecard could not be loaded. Check that the API is running, then try again.');
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const recheck = async () => {
    setChecking(true);
    setNotice(null);
    try {
      const res = await axios.post<{ cells: number; changed: number }>(`${API_URL}/configs/evaluate`);
      await load();
      setNotice(
        res.data.changed === 0
          ? `Checked ${res.data.cells} cells. No status changed.`
          : `Checked ${res.data.cells} cells. ${res.data.changed} changed status.`,
      );
    } catch {
      setNotice('The check did not run. Try again.');
    } finally {
      setChecking(false);
    }
  };

  const counts = useMemo(() => {
    const c: Record<Filter, number> = { ALL: 0, TESTING: 0, PROVEN: 0, PAUSED: 0 };
    for (const cell of cells ?? []) {
      c.ALL += 1;
      c[cell.status] += 1;
    }
    return c;
  }, [cells]);

  const books = useMemo(() => {
    const all = cells ?? [];
    return {
      main: { trades: all.reduce((s, c) => s + c.mainBook.trades, 0), pnl: all.reduce((s, c) => s + c.mainBook.netPnl, 0) },
      test: { trades: all.reduce((s, c) => s + c.testBook.trades, 0), pnl: all.reduce((s, c) => s + c.testBook.netPnl, 0) },
    };
  }, [cells]);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = (cells ?? []).filter(
      (c) =>
        (filter === 'ALL' || c.status === filter) &&
        (!q || c.symbol.toLowerCase().includes(q) || c.strategyName.toLowerCase().includes(q)),
    );
    const gap = (c: Cell) =>
      c.live.avgR !== null && c.backtest?.avgR != null ? c.live.avgR - c.backtest.avgR : Infinity;
    // Cells with no live trades always sink to the bottom: there is nothing to rank yet.
    const untested = (c: Cell) => (c.live.trades === 0 ? 1 : 0);
    const by: Record<SortKey, (a: Cell, b: Cell) => number> = {
      evidence: (a, b) => STATUS_RANK[a.status] - STATUS_RANK[b.status] || b.live.trades - a.live.trades,
      liveR: (a, b) => (b.live.avgR ?? -Infinity) - (a.live.avgR ?? -Infinity),
      trades: (a, b) => b.live.trades - a.live.trades,
      pnl: (a, b) => b.live.netPnl - a.live.netPnl,
      gap: (a, b) => gap(a) - gap(b),
      name: (a, b) => a.symbol.localeCompare(b.symbol) || a.strategyName.localeCompare(b.strategyName),
    };
    return [...list].sort((a, b) => untested(a) - untested(b) || by[sort](a, b));
  }, [cells, filter, query, sort]);

  return (
    <main className="page">
      <div className="page-header sc-header">
        <div>
          <h1 className="page-title">Scorecard</h1>
          <p className="page-subtitle">
            Every stock and strategy pair, judged on its own paper trades after costs.
          </p>
        </div>
        <button className="btn btn-secondary" onClick={recheck} disabled={checking || cells === null}>
          {checking ? 'Checking…' : 'Re-check all cells'}
        </button>
      </div>

      <div aria-live="polite" className="sc-live-region">
        {notice && <div className="alert alert-info">{notice}</div>}
      </div>

      {error && (
        <div className="alert alert-error sc-error" role="alert">
          <span>{error}</span>
          <button className="btn btn-sm btn-secondary" onClick={load}>
            Try again
          </button>
        </div>
      )}

      {cells === null && !error && <SkeletonRows />}

      {cells !== null && cells.length === 0 && (
        <div className="card empty-state">
          <div className="empty-title">No cells are being tracked yet</div>
          <div className="empty-subtitle">
            Add a strategy to a stock from Backtesting and it will appear here with its first paper trade.
          </div>
          <Link to="/backtesting" className="btn btn-primary">
            Open Backtesting
          </Link>
        </div>
      )}

      {cells !== null && cells.length > 0 && (
        <>
          <div className="sc-books">
            <div className="sc-book">
              <span className="sc-book-name">Main book</span>
              <span className={`sc-book-pnl mono ${tone(books.main.pnl)}`}>{rupees(books.main.pnl)}</span>
              <span className="sc-book-note">{books.main.trades} closed trades</span>
            </div>
            <div className="sc-book">
              <span className="sc-book-name">Test book</span>
              <span className={`sc-book-pnl mono ${tone(books.test.pnl)}`}>{rupees(books.test.pnl)}</span>
              <span className="sc-book-note">
                {books.test.trades} trades taken while a cell was paused. Not counted in the main book.
              </span>
            </div>
          </div>

          <div className="sc-toolbar">
            <div className="sc-filters" role="group" aria-label="Filter by status">
              {(['ALL', 'PROVEN', 'TESTING', 'PAUSED'] as Filter[]).map((f) => (
                <button
                  key={f}
                  className={`sc-chip ${f.toLowerCase()} ${filter === f ? 'on' : ''}`}
                  aria-pressed={filter === f}
                  onClick={() => setFilter(f)}
                  title={f === 'ALL' ? 'Every cell' : STATUS_HELP[f]}
                >
                  {f === 'ALL' ? 'All' : STATUS_LABEL[f]}
                  <span className="sc-chip-count mono">{counts[f]}</span>
                </button>
              ))}
            </div>
            <div className="sc-controls">
              <label className="sc-field">
                <span className="sc-field-label">Find</span>
                <input
                  className="form-select"
                  type="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Stock or strategy"
                />
              </label>
              <label className="sc-field">
                <span className="sc-field-label">Sort by</span>
                <select className="form-select" value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
                  <option value="evidence">Status, then most trades</option>
                  <option value="liveR">Best live result</option>
                  <option value="gap">Furthest below its backtest</option>
                  <option value="pnl">Net profit</option>
                  <option value="trades">Most trades</option>
                  <option value="name">Stock name</option>
                </select>
              </label>
            </div>
          </div>

          {rows.length === 0 ? (
            <div className="card empty-state">
              <div className="empty-title">Nothing matches</div>
              <div className="empty-subtitle">No cell fits this filter and search.</div>
              <button
                className="btn btn-secondary"
                onClick={() => {
                  setFilter('ALL');
                  setQuery('');
                }}
              >
                Show all cells
              </button>
            </div>
          ) : (
            <div className="table-wrapper sc-table">
              <table>
                <thead>
                  <tr>
                    <th>Cell</th>
                    <th>Status</th>
                    <th>Live against backtest (avg per trade)</th>
                    <th>Trades</th>
                    <th>First half, second half</th>
                    <th className="sc-num">Net after costs</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((c) => (
                    <tr key={c.id}>
                      <td data-label="Cell">
                        <Link to={`/stock/${c.symbol}`} className="sc-symbol">
                          {c.symbol}
                        </Link>
                        <div className="sc-strategy">
                          {c.strategyName.replace(/_/g, ' ')} <span className="sc-tf mono">{c.timeframe}</span>
                        </div>
                        {c.dataFlag && (
                          <div className="sc-flag">
                            Price history needs review{c.dataFlagDetail ? `: ${c.dataFlagDetail}` : ''}
                          </div>
                        )}
                      </td>
                      <td data-label="Status">
                        <span className={`badge sc-status ${c.status.toLowerCase()}`}>{STATUS_LABEL[c.status]}</span>
                        <div className="sc-reason">{c.statusReason || STATUS_HELP[c.status]}</div>
                      </td>
                      <td data-label="Live against backtest">
                        <PromiseGauge live={c.live.avgR} backtest={c.backtest?.avgR ?? null} />
                      </td>
                      <td data-label="Trades">
                        <span className="mono">{c.live.trades}</span>
                        <div className="sc-sub">
                          {c.live.winRate === null ? 'none closed' : `${c.live.winRate.toFixed(0)}% won`}
                          {c.openTrades > 0 && `, ${c.openTrades} open`}
                        </div>
                      </td>
                      <td data-label="First half, second half">
                        {c.live.firstHalfR === null ? (
                          <span className="sc-sub">needs 2+ trades</span>
                        ) : (
                          <span className="mono sc-halves">
                            <span className={tone(c.live.firstHalfR)}>{signedR(c.live.firstHalfR)}</span>
                            <span className="sc-then">then</span>
                            <span className={tone(c.live.secondHalfR)}>{signedR(c.live.secondHalfR)}</span>
                          </span>
                        )}
                      </td>
                      <td data-label="Net after costs" className="sc-num">
                        <span className={`mono sc-pnl ${tone(c.live.netPnl)}`}>{rupees(c.live.netPnl)}</span>
                        {c.testBook.trades > 0 && (
                          <div className="sc-sub">{rupees(c.testBook.netPnl)} of it in the test book</div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <p className="sc-legend">
            <span className="sc-legend-live" /> live paper trades, after costs
            <span className="sc-legend-bt" /> what the backtest showed. R is the result of a trade divided by the
            rupees it risked: +1R made what it risked, −1R lost it.
          </p>
        </>
      )}
    </main>
  );
}
