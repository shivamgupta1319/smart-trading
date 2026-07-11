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

// Portfolio "heat" = sum of money at risk if every open stop hits, as a % of total deployed
// base (₹10k × active cells). A soft risk-dashboard flag threshold, not a funding gate.
export const MAX_HEAT_PCT = Number(process.env.MAX_HEAT_PCT || 6); // 6% of deployed base

// A (stock × strategy) cell needs at least this many closed trades before its edge metrics
// are treated as trustworthy (guards against small-sample flukes like "100% on 3 trades").
export const MIN_TRADES_FOR_CONFIDENCE = Number(process.env.MIN_TRADES_FOR_CONFIDENCE || 20);

/** Buying-power multiple for a hold duration: INTRADAY 5×, everything else 1×. */
export const leverageFor = (holdDuration: string | null | undefined): number =>
  holdDuration === 'INTRADAY' ? LEVERAGE_INTRADAY : LEVERAGE_DELIVERY;
