/** Shared portfolio/risk constants (single source of truth). */
export const INITIAL_CAPITAL = Number(process.env.INITIAL_CAPITAL || 100000); // ₹1,00,000
export const RISK_PER_TRADE_PCT = Number(process.env.RISK_PER_TRADE_PCT || 2); // 2% per trade
export const MAX_RISK_PER_TRADE = INITIAL_CAPITAL * (RISK_PER_TRADE_PCT / 100); // ₹2,000
