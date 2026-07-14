/** Shared capital/risk constants (single source of truth). */

// Per-cell fund model (strategy-testing lab): every (stock × strategy) cell owns its own
// ₹10,000 fund that COMPOUNDS with that cell's realized P&L, so each cell's growth is a
// clean, comparable measure of "which stock+strategy earns". A new trade is sized to
// cellCapital × leverage worth of notional. There is no shared bankroll and no funding
// gate — every selected-strategy signal is a real mock-money trade. MUST match the
// engine's per-cell slot in backtest_config.py (BT slot = ₹10,000, compounding).
export const BASE_CELL_CAPITAL = Number(process.env.BASE_CELL_CAPITAL || 10000); // ₹10,000 seed per cell
export const MIN_CELL_CAPITAL = Number(process.env.MIN_CELL_CAPITAL || 500); // floor so a blown-up cell can still size ≥1 share

// Intraday (MIS) gives ~5× buying power; delivery/swing (CNC) uses full cash (1×). Here
// leverage multiplies the deployed NOTIONAL (cellCapital × leverage), so an intraday cell
// deploys ~₹50k while a swing cell deploys ~₹10k off the same ₹10k fund.
export const LEVERAGE_INTRADAY = Number(process.env.LEVERAGE_INTRADAY || 5);
export const LEVERAGE_DELIVERY = Number(process.env.LEVERAGE_DELIVERY || 1);

// Per-trade risk cap (FEAT-005). Notional sizing alone lets a wide-stop trade risk multiples
// of a tight-stop one on the same fund — the payoff-ratio leak (avg ₹-loss > avg ₹-win) from
// docs/agent-reports/2026-07-14-avg-loss-gt-avg-win-audit.md (F1). We bound each trade to at
// most `cellCapital × RISK_PER_TRADE_PCT` rupees of risk:
//   qty = max(1, min(floor(notionalBudget/entry), floor(riskBudget/riskPerShare)))
// MUST match the engine's RISK_PER_TRADE_PCT in apps/engine/backtest_config.py, or the
// backtest stops predicting live (same parity invariant as leverage/costs).
export const RISK_PER_TRADE_PCT = Number(process.env.RISK_PER_TRADE_PCT || 0.02); // 2% of the cell fund

/** Rupees a single trade may risk = cell fund × RISK_PER_TRADE_PCT. */
export const riskBudgetFor = (cellCapital: number): number => cellCapital * RISK_PER_TRADE_PCT;

// Portfolio "heat" = sum of money at risk if every open stop hits, as a % of total deployed
// base (₹10k × active cells). A soft risk-dashboard flag threshold, not a funding gate.
export const MAX_HEAT_PCT = Number(process.env.MAX_HEAT_PCT || 6); // 6% of deployed base

// A (stock × strategy) cell needs at least this many closed trades before its edge metrics
// are treated as trustworthy (guards against small-sample flukes like "100% on 3 trades").
export const MIN_TRADES_FOR_CONFIDENCE = Number(process.env.MIN_TRADES_FOR_CONFIDENCE || 20);

/** Buying-power multiple for a hold duration: INTRADAY 5×, everything else 1×. */
export const leverageFor = (holdDuration: string | null | undefined): number =>
  holdDuration === 'INTRADAY' ? LEVERAGE_INTRADAY : LEVERAGE_DELIVERY;

// A trade whose |P&L| is within this fraction of the rupees it risked is a scratch,
// not a real win/loss — booking it WIN/LOSS distorts win-rate and profit factor.
export const BREAKEVEN_R = Number(process.env.BREAKEVEN_R || 0.1); // 0.1R scratch band

/**
 * Classify a closed trade as WIN / LOSS / BREAKEVEN using a small R-based scratch
 * band, so a +₹1.88 (≈0.03R) close is not booked as a WIN. Falls back to the sign
 * of P&L when riskAmount is unknown (0).
 */
export const classifyOutcome = (pnl: number, riskAmount: number): 'WIN' | 'LOSS' | 'BREAKEVEN' => {
  if (riskAmount > 0 && Math.abs(pnl) <= BREAKEVEN_R * riskAmount) return 'BREAKEVEN';
  return pnl > 0 ? 'WIN' : pnl < 0 ? 'LOSS' : 'BREAKEVEN';
};

/**
 * Actual cash (margin) deployed for a position = leveraged notional ÷ leverage.
 * `capitalUsed` stores the leveraged notional (qty × entry), so per-trade return %
 * must divide P&L by this margin — not the notional — to be comparable to the
 * cell's ROI on its ₹10k fund.
 */
export const marginOf = (capitalUsed: number, holdDuration: string | null | undefined): number =>
  capitalUsed / leverageFor(holdDuration);
