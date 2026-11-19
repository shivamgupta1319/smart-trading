/**
 * Cell lifecycle: when one stock × strategy cell is paused, resumed or marked proven.
 *
 * Judged only on the cell's own CLOSED paper trades, after costs, in R (a trade's
 * profit or loss divided by the rupees it risked). The live data is why this exists:
 * a cell's past live result predicted its later live result (correlation 0.84 across
 * 22 cells), while its backtest predicted nothing. Thresholds are in
 * config/trading.json under "lifecycle".
 *
 * Pause and resume both look at the most recent WINDOW trades, so a cell cannot be
 * resumed and re-paused by the same old losses:
 *   PAUSE   the last WINDOW trades average below PAUSE_AVG_R, or lost more than
 *           PAUSE_LOSS_PCT of the cell's starting fund between them.
 *   RESUME  a PAUSED cell has taken a full WINDOW of new (test-book) trades since it
 *           was paused and they average above RESUME_AVG_R.
 *   PROVEN  at least PROVEN_MIN_TRADES trades, average above PROVEN_AVG_R, profit
 *           factor at least PROVEN_PROFIT_FACTOR, and positive in BOTH halves.
 */
import { shared } from './shared-config';

export type CellStatus = 'TESTING' | 'PROVEN' | 'PAUSED';

export interface ClosedTrade {
  pnl: number; // net of costs
  riskAmount: number; // rupees risked at entry
}

export interface CellStats {
  trades: number;
  wins: number;
  winRate: number | null; // %
  netPnl: number;
  avgR: number | null;
  profitFactor: number | null;
  firstHalfR: number | null;
  secondHalfR: number | null;
  windowTrades: number; // how many trades the recent window actually holds
  windowAvgR: number | null;
  windowPnl: number;
}

export interface LifecycleRules {
  windowTrades: number;
  pauseAvgR: number;
  pauseLossPct: number;
  resumeAvgR: number;
  provenMinTrades: number;
  provenAvgR: number;
  provenProfitFactor: number;
}

export const lifecycleRules = (): LifecycleRules => ({
  windowTrades: shared('LIFECYCLE_WINDOW_TRADES'),
  pauseAvgR: shared('LIFECYCLE_PAUSE_AVG_R'),
  pauseLossPct: shared('LIFECYCLE_PAUSE_LOSS_PCT'),
  resumeAvgR: shared('LIFECYCLE_RESUME_AVG_R'),
  provenMinTrades: shared('LIFECYCLE_PROVEN_MIN_TRADES'),
  provenAvgR: shared('LIFECYCLE_PROVEN_AVG_R'),
  provenProfitFactor: shared('LIFECYCLE_PROVEN_PROFIT_FACTOR'),
});

const rOf = (t: ClosedTrade): number | null => (t.riskAmount > 0 ? t.pnl / t.riskAmount : null);

const mean = (xs: number[]): number | null =>
  xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null;

const avgR = (trades: ClosedTrade[]): number | null =>
  mean(trades.map(rOf).filter((r): r is number => r !== null));

/** Stats for one cell. `trades` must be ordered oldest → newest. */
export function cellStats(trades: ClosedTrade[], windowTrades: number): CellStats {
  const wins = trades.filter((t) => t.pnl > 0);
  const grossWin = wins.reduce((s, t) => s + t.pnl, 0);
  const grossLoss = trades.filter((t) => t.pnl < 0).reduce((s, t) => s - t.pnl, 0);
  const half = Math.floor(trades.length / 2);
  const window = trades.slice(-windowTrades);
  return {
    trades: trades.length,
    wins: wins.length,
    winRate: trades.length ? (100 * wins.length) / trades.length : null,
    netPnl: trades.reduce((s, t) => s + t.pnl, 0),
    avgR: avgR(trades),
    profitFactor: grossWin > 0 && grossLoss > 0 ? grossWin / grossLoss : null,
    firstHalfR: half ? avgR(trades.slice(0, half)) : null,
    secondHalfR: half ? avgR(trades.slice(half)) : null,
    windowTrades: window.length,
    windowAvgR: avgR(window),
    windowPnl: window.reduce((s, t) => s + t.pnl, 0),
  };
}

const f = (n: number, digits = 2): string => n.toFixed(digits);

/**
 * The status a cell should have now.
 * @param tradesSinceChange closed trades taken since the status last changed
 * @param baseCapital what the cell's loss limit is a share of: its starting fund times its
 *   leverage (₹50,000 intraday, ₹10,000 swing), the same base the per-trade risk uses, so
 *   the limit is worth the same number of full stop-outs for every kind of cell
 */
export function evaluateCell(
  current: CellStatus,
  stats: CellStats,
  tradesSinceChange: number,
  baseCapital: number,
  rules: LifecycleRules,
): { status: CellStatus; reason: string } {
  const fullWindow = stats.windowTrades >= rules.windowTrades;
  const lossLimit = -rules.pauseLossPct * baseCapital;

  if (current === 'PAUSED') {
    if (fullWindow && tradesSinceChange >= rules.windowTrades && (stats.windowAvgR ?? -1) > rules.resumeAvgR) {
      return {
        status: 'TESTING',
        reason: `Resumed: last ${stats.windowTrades} trades average ${f(stats.windowAvgR ?? 0)}R`,
      };
    }
    return { status: 'PAUSED', reason: '' }; // unchanged: the caller keeps the stored reason
  }

  if (fullWindow && stats.windowAvgR !== null && stats.windowAvgR < rules.pauseAvgR) {
    return {
      status: 'PAUSED',
      reason: `Paused: last ${stats.windowTrades} trades average ${f(stats.windowAvgR)}R (limit ${f(rules.pauseAvgR)}R)`,
    };
  }
  if (fullWindow && stats.windowPnl < lossLimit) {
    return {
      status: 'PAUSED',
      reason: `Paused: last ${stats.windowTrades} trades lost ₹${f(-stats.windowPnl, 0)} (limit ₹${f(-lossLimit, 0)})`,
    };
  }

  const proven =
    stats.trades >= rules.provenMinTrades &&
    (stats.avgR ?? 0) > rules.provenAvgR &&
    (stats.profitFactor ?? 0) >= rules.provenProfitFactor &&
    (stats.firstHalfR ?? 0) > 0 &&
    (stats.secondHalfR ?? 0) > 0;
  if (proven) {
    return {
      status: 'PROVEN',
      reason: `Proven: ${stats.trades} trades, average ${f(stats.avgR ?? 0)}R, profit factor ${f(stats.profitFactor ?? 0)}, positive in both halves`,
    };
  }
  return {
    status: 'TESTING',
    reason: current === 'PROVEN' ? 'No longer meets the proven rules' : '',
  };
}
