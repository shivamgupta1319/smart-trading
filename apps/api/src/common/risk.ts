/** Shared portfolio/risk constants (single source of truth). */
export const INITIAL_CAPITAL = Number(process.env.INITIAL_CAPITAL || 100000); // ₹1,00,000
export const RISK_PER_TRADE_PCT = Number(process.env.RISK_PER_TRADE_PCT || 2); // 2% per trade
export const MAX_RISK_PER_TRADE = INITIAL_CAPITAL * (RISK_PER_TRADE_PCT / 100); // ₹2,000

// Intraday (MIS) gives ~5× buying power; delivery (CNC) needs full cash (1×). Leverage only
// changes how much *margin* a position locks up (notional ÷ leverage), never the loss if the
// stop hits — that stays RISK_PER_TRADE_PCT, set by quantity × stop-distance.
export const LEVERAGE_INTRADAY = Number(process.env.LEVERAGE_INTRADAY || 5);
export const LEVERAGE_DELIVERY = Number(process.env.LEVERAGE_DELIVERY || 1);

// Portfolio "heat" = sum of money at risk if every open stop hits. Cap at 3× the per-trade
// rule so at most ~3 concurrent full-risk positions can be funded.
export const MAX_HEAT_PCT = Number(process.env.MAX_HEAT_PCT || 6); // 6% of capital
export const MAX_HEAT = INITIAL_CAPITAL * (MAX_HEAT_PCT / 100); // ₹6,000

// A (stock × strategy) cell needs at least this many closed trades before its edge metrics
// are treated as trustworthy (guards against small-sample flukes like "100% on 3 trades").
export const MIN_TRADES_FOR_CONFIDENCE = Number(process.env.MIN_TRADES_FOR_CONFIDENCE || 20);

/** Buying-power multiple for a hold duration: INTRADAY 5×, everything else 1×. */
export const leverageFor = (holdDuration: string | null | undefined): number =>
  holdDuration === 'INTRADAY' ? LEVERAGE_INTRADAY : LEVERAGE_DELIVERY;
