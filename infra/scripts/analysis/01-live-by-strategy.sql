-- Live paper results by hold type, side and strategy. READ-ONLY.
--
-- Run (work-pc):
--   docker exec -i smart-trading-db    psql -U trader -d smart_trading -P pager=off < 01-live-by-strategy.sql   # v1
--   docker exec -i smart-trading-v2-db psql -U trader -d smart_trading -P pager=off < 01-live-by-strategy.sql   # v2
--
-- avg_r uses riskAmount, which is sized off originalStopLoss (never the trailed stopLoss).
-- v2 books pnl NET of costs. v1 books GROSS: use the last query for a cost estimate.

\echo ===== by hold type and side =====
SELECT "holdDuration" hd, "signalType" side, COUNT(*) n,
       ROUND(100.0 * AVG((pnl > 0)::int), 1) win_pct,
       ROUND(SUM(pnl)::numeric, 0) pnl,
       ROUND((SUM(pnl) FILTER (WHERE pnl > 0) / NULLIF(-SUM(pnl) FILTER (WHERE pnl < 0), 0))::numeric, 2) pf,
       ROUND(AVG(pnl) FILTER (WHERE pnl > 0)::numeric, 0) avg_win,
       ROUND(AVG(pnl) FILTER (WHERE pnl < 0)::numeric, 0) avg_loss,
       ROUND(AVG(pnl / NULLIF("riskAmount", 0))::numeric, 3) avg_r
FROM "Trade" WHERE status = 'CLOSED'
GROUP BY 1, 2 ORDER BY 1, 2;

\echo ===== by strategy =====
SELECT "strategyName" s, MIN("holdDuration") hd, COUNT(*) n, COUNT(DISTINCT symbol) stocks,
       ROUND(100.0 * AVG((pnl > 0)::int), 1) win_pct,
       ROUND(SUM(pnl)::numeric, 0) pnl,
       ROUND((SUM(pnl) FILTER (WHERE pnl > 0) / NULLIF(-SUM(pnl) FILTER (WHERE pnl < 0), 0))::numeric, 2) pf,
       ROUND(AVG(pnl / NULLIF("riskAmount", 0))::numeric, 3) avg_r
FROM "Trade" WHERE status = 'CLOSED'
GROUP BY 1 ORDER BY pnl;

\echo ===== churn: intraday trades per cell per day =====
SELECT "strategyName", COUNT(*) n,
       ROUND(COUNT(*)::numeric / COUNT(DISTINCT (symbol, "entryTime"::date)), 2) trades_per_cell_day,
       ROUND(AVG(EXTRACT(epoch FROM "exitTime" - "entryTime") / 60)::numeric, 0) avg_hold_min
FROM "Trade" WHERE status = 'CLOSED' AND "holdDuration" = 'INTRADAY'
GROUP BY 1 ORDER BY 3 DESC;

\echo ===== v1 ONLY: intraday cost estimate (v1 books no costs; v2 pnl is already net) =====
-- charges = brokerage min(0.03%, Rs 20) per side + 18% GST, STT 0.025% on sell,
-- exchange 0.00307% + GST, stamp 0.003% on buy. Slippage shown at 2 and 5 bps per side.
WITH t AS (
  SELECT *, ("entryPrice" + "exitPrice") * quantity AS turnover,
         CASE WHEN "signalType" = 'BUY' THEN "exitPrice" * quantity ELSE "entryPrice" * quantity END AS sellval,
         CASE WHEN "signalType" = 'BUY' THEN "entryPrice" * quantity ELSE "exitPrice" * quantity END AS buyval
  FROM "Trade"
  WHERE status = 'CLOSED' AND "exitPrice" IS NOT NULL AND "holdDuration" = 'INTRADAY'),
c AS (
  SELECT *, (LEAST(0.0003 * buyval, 20) + LEAST(0.0003 * sellval, 20)) * 1.18
            + 0.00025 * sellval + 0.0000307 * turnover * 1.18 + 0.00003 * buyval AS charges
  FROM t)
SELECT COALESCE("strategyName", '== ALL INTRADAY ==') s, COUNT(*) n,
       ROUND(SUM(pnl)::numeric, 0) gross,
       ROUND(AVG(charges)::numeric, 0) charges_per_trade,
       ROUND(SUM(pnl - charges)::numeric, 0) net_charges_only,
       ROUND(SUM(pnl - charges - 0.0002 * turnover)::numeric, 0) net_2bps,
       ROUND(SUM(pnl - charges - 0.0005 * turnover)::numeric, 0) net_5bps
FROM c GROUP BY ROLLUP("strategyName") ORDER BY net_2bps;
