/**
 * Indian NSE transaction-cost model for booking live P&L NET of costs — mirrors
 * apps/engine/backtest_config.py (CostModel) field-for-field, including the same
 * env-var names, so a live close and its backtest use an identical cost schedule.
 * Defaults approximate a discount broker (Zerodha-style) on NSE equity.
 *
 * Note: slippage is NOT modelled here. The backtest applies slippage to fill
 * PRICES; live P&L already uses the real observed entry/exit prices, so only the
 * transaction costs (brokerage/STT/exchange/SEBI/stamp/GST) are subtracted.
 */

import { shared } from './shared-config';

interface CostProfile {
  brokeragePct: number; // % of turnover per side
  brokerageFlatCap: number; // ₹ cap per side
  sttBuyPct: number;
  sttSellPct: number;
  exchangeTxnPct: number; // both sides
  sebiPct: number; // both sides
  stampBuyPct: number; // buy side only
  gstPct: number; // on (brokerage + exchange txn)
  dpChargePerSell: number; // flat ₹ per delivery (CNC) sell, incl. GST
}

// MIS-style: STT on sell only, higher intraday stamp. Matches INTRADAY_PROFILE.
const INTRADAY_PROFILE: CostProfile = {
  brokeragePct: shared('BT_INTRADAY_BROKERAGE_PCT'),
  brokerageFlatCap: shared('BT_BROKERAGE_FLAT_CAP'),
  sttBuyPct: shared('BT_INTRADAY_STT_BUY_PCT'),
  sttSellPct: shared('BT_INTRADAY_STT_SELL_PCT'),
  exchangeTxnPct: shared('BT_EXCHANGE_TXN_PCT'),
  sebiPct: shared('BT_SEBI_PCT'),
  stampBuyPct: shared('BT_INTRADAY_STAMP_BUY_PCT'),
  gstPct: shared('BT_GST_PCT'),
  dpChargePerSell: 0.0, // no delivery leg for intraday (MIS) — no DP charge
};

// CNC-style: STT both sides, brokerage often free, higher stamp. Matches DELIVERY_PROFILE.
const DELIVERY_PROFILE: CostProfile = {
  brokeragePct: shared('BT_DELIVERY_BROKERAGE_PCT'),
  brokerageFlatCap: shared('BT_BROKERAGE_FLAT_CAP'),
  sttBuyPct: shared('BT_DELIVERY_STT_BUY_PCT'),
  sttSellPct: shared('BT_DELIVERY_STT_SELL_PCT'),
  exchangeTxnPct: shared('BT_EXCHANGE_TXN_PCT'),
  sebiPct: shared('BT_SEBI_PCT'),
  stampBuyPct: shared('BT_DELIVERY_STAMP_BUY_PCT'),
  gstPct: shared('BT_GST_PCT'),
  // Dhan: ₹12.50 + 18% GST ≈ ₹14.75 per ISIN per day on every CNC sell (flat, not turnover-based).
  dpChargePerSell: shared('BT_DP_CHARGE_PER_DELIVERY_SELL'),
};

/** Master switch to book live P&L net of costs (env LIVE_COSTS_ENABLED, default on). */
export const LIVE_COSTS_ENABLED =
  (process.env.LIVE_COSTS_ENABLED ?? 'true').toLowerCase() !== 'false';

const brokerage = (p: CostProfile, turnover: number): number =>
  Math.min((turnover * p.brokeragePct) / 100.0, p.brokerageFlatCap);

/**
 * Total round-trip transaction cost (₹) to buy `buyValue` and sell `sellValue` of
 * stock. INTRADAY hold uses the MIS profile; everything else (daily swing/positional)
 * uses the CNC/delivery profile — matching CostModel(timeframe) in the engine.
 */
export function roundTripCost(
  buyValue: number,
  sellValue: number,
  holdDuration: string | null | undefined,
): number {
  const p = holdDuration === 'INTRADAY' ? INTRADAY_PROFILE : DELIVERY_PROFILE;
  const brok = brokerage(p, buyValue) + brokerage(p, sellValue);
  const stt = (buyValue * p.sttBuyPct) / 100.0 + (sellValue * p.sttSellPct) / 100.0;
  const exch = ((buyValue + sellValue) * p.exchangeTxnPct) / 100.0;
  const sebi = ((buyValue + sellValue) * p.sebiPct) / 100.0;
  const stamp = (buyValue * p.stampBuyPct) / 100.0;
  const gst = ((brok + exch) * p.gstPct) / 100.0;
  // Flat DP charge, once per delivery sell (already GST-inclusive; 0 for intraday).
  const dp = p.dpChargePerSell;
  return brok + stt + exch + sebi + stamp + gst + dp;
}

/** Slippage assumed per side, as a fraction of price (shared with the engine). */
export const SLIPPAGE_FRACTION = shared('BT_SLIPPAGE_BPS') / 10_000;
/** Smallest price step on NSE cash equities, in rupees (shared with the engine). */
export const TICK_SIZE = shared('TICK_SIZE');

/**
 * Rupees of slippage per share on one side of a trade: the larger of one price tick and
 * the configured basis points of the price. MUST match `slippage_per_share` in
 * apps/engine/backtest_config.py.
 */
export const slippagePerShare = (price: number): number => Math.max(TICK_SIZE, price * SLIPPAGE_FRACTION);

/**
 * A trade is rejected when its round-trip cost is more than this share of the rupees
 * it risks (0 = rule off). Shared with the engine, which skips the same signals.
 */
export const MAX_COST_TO_RISK = shared('MAX_COST_TO_RISK');

/**
 * Round-trip cost of a position (charges + slippage on both sides) divided by the
 * rupees it risks. MUST match `cost_to_risk` in apps/engine/backtest_config.py.
 */
export function costToRisk(
  quantity: number,
  entryPrice: number,
  riskPerShare: number,
  holdDuration: string | null | undefined,
): number {
  const value = quantity * entryPrice;
  const friction = roundTripCost(value, value, holdDuration) + 2 * quantity * slippagePerShare(entryPrice);
  return friction / (quantity * riskPerShare);
}
