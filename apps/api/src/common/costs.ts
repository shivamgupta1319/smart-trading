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

const num = (name: string, def: number): number => {
  const v = Number(process.env[name]);
  return Number.isFinite(v) ? v : def;
};

interface CostProfile {
  brokeragePct: number; // % of turnover per side
  brokerageFlatCap: number; // ₹ cap per side
  sttBuyPct: number;
  sttSellPct: number;
  exchangeTxnPct: number; // both sides
  sebiPct: number; // both sides
  stampBuyPct: number; // buy side only
  gstPct: number; // on (brokerage + exchange txn)
}

// MIS-style: STT on sell only, higher intraday stamp. Matches INTRADAY_PROFILE.
const INTRADAY_PROFILE: CostProfile = {
  brokeragePct: num('BT_INTRADAY_BROKERAGE_PCT', 0.03),
  brokerageFlatCap: num('BT_BROKERAGE_FLAT_CAP', 20.0),
  sttBuyPct: num('BT_INTRADAY_STT_BUY_PCT', 0.0),
  sttSellPct: num('BT_INTRADAY_STT_SELL_PCT', 0.025),
  exchangeTxnPct: num('BT_EXCHANGE_TXN_PCT', 0.00297),
  sebiPct: num('BT_SEBI_PCT', 0.0001),
  stampBuyPct: num('BT_INTRADAY_STAMP_BUY_PCT', 0.003),
  gstPct: num('BT_GST_PCT', 18.0),
};

// CNC-style: STT both sides, brokerage often free, higher stamp. Matches DELIVERY_PROFILE.
const DELIVERY_PROFILE: CostProfile = {
  brokeragePct: num('BT_DELIVERY_BROKERAGE_PCT', 0.0),
  brokerageFlatCap: num('BT_BROKERAGE_FLAT_CAP', 20.0),
  sttBuyPct: num('BT_DELIVERY_STT_BUY_PCT', 0.1),
  sttSellPct: num('BT_DELIVERY_STT_SELL_PCT', 0.1),
  exchangeTxnPct: num('BT_EXCHANGE_TXN_PCT', 0.00297),
  sebiPct: num('BT_SEBI_PCT', 0.0001),
  stampBuyPct: num('BT_DELIVERY_STAMP_BUY_PCT', 0.015),
  gstPct: num('BT_GST_PCT', 18.0),
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
  return brok + stt + exch + sebi + stamp + gst;
}
