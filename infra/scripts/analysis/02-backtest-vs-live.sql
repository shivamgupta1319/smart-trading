-- Does the backtest predict live? And does live predict live? READ-ONLY.
--
-- Run (work-pc), either database:
--   docker exec -i smart-trading-v2-db psql -U trader -d smart_trading -P pager=off < 02-backtest-vs-live.sql
--
-- 2026-11-19 result: backtest rank had no predictive power (v1 corr -0.06);
-- a cell's first-half live result predicted its second half (corr 0.84, 22 cells).

\echo ===== live result of cells, bucketed by their backtest ROI =====
WITH bt AS (
  SELECT DISTINCT ON ("stockId", "strategyName") "stockId", "strategyName",
         "roiPercentage" roi, "winRate" bwin, "totalTrades" btrades
  FROM "BacktestReport" ORDER BY "stockId", "strategyName", "createdAt" DESC),
lv AS (
  SELECT "stockId", "strategyName", COUNT(*) n, SUM(pnl) net, 100.0 * AVG((pnl > 0)::int) lwin
  FROM "Trade" WHERE status = 'CLOSED' GROUP BY 1, 2)
SELECT CASE WHEN roi IS NULL THEN '0 no backtest' WHEN roi <= 0 THEN '1 bt roi<=0'
            WHEN roi < 20 THEN '2 bt 0-20%' WHEN roi < 50 THEN '3 bt 20-50%'
            WHEN roi < 100 THEN '4 bt 50-100%' ELSE '5 bt >100%' END bucket,
       COUNT(*) cells, SUM(n) live_trades,
       ROUND(100.0 * AVG((net > 0)::int), 0) pct_cells_live_profitable,
       ROUND(SUM(net)::numeric, 0) live_pnl,
       ROUND(AVG(bwin)::numeric, 1) backtest_win,
       ROUND((SUM(lwin * n) / SUM(n))::numeric, 1) live_win,
       ROUND(AVG(btrades)::numeric, 0) avg_backtest_trades
FROM lv LEFT JOIN bt USING ("stockId", "strategyName")
GROUP BY 1 ORDER BY 1;

\echo ===== correlation: backtest vs live, cells with >= 10 live trades =====
WITH bt AS (
  SELECT DISTINCT ON ("stockId", "strategyName") "stockId", "strategyName",
         "roiPercentage" roi, "winRate" bwin
  FROM "BacktestReport" ORDER BY "stockId", "strategyName", "createdAt" DESC),
lv AS (
  SELECT "stockId", "strategyName", SUM(pnl)::float net, 100.0 * AVG((pnl > 0)::int)::float lwin,
         AVG(pnl / NULLIF("riskAmount", 0))::float r
  FROM "Trade" WHERE status = 'CLOSED' GROUP BY 1, 2 HAVING COUNT(*) >= 10)
SELECT COUNT(*) cells,
       ROUND(corr(roi, net)::numeric, 3) corr_roi_vs_live_pnl,
       ROUND(corr(roi, r)::numeric, 3) corr_roi_vs_live_avg_r,
       ROUND(corr(bwin, lwin)::numeric, 3) corr_win_rate
FROM lv JOIN bt USING ("stockId", "strategyName");

\echo ===== live predicts live: cell avgR, first half vs second half (set the split date) =====
\set split '''2026-09-15'''
WITH x AS (
  SELECT symbol, "strategyName",
         AVG(pnl / NULLIF("riskAmount", 0)) FILTER (WHERE "entryTime" <  :split)::float r1,
         COUNT(*)                           FILTER (WHERE "entryTime" <  :split) n1,
         AVG(pnl / NULLIF("riskAmount", 0)) FILTER (WHERE "entryTime" >= :split)::float r2,
         COUNT(*)                           FILTER (WHERE "entryTime" >= :split) n2
  FROM "Trade" WHERE status = 'CLOSED' AND "holdDuration" = 'INTRADAY' GROUP BY 1, 2)
SELECT COUNT(*) cells_20plus_each_half, ROUND(corr(r1, r2)::numeric, 3) corr_first_vs_second,
       COUNT(*) FILTER (WHERE r1 > 0) positive_first,
       COUNT(*) FILTER (WHERE r1 > 0 AND r2 > 0) positive_both,
       COUNT(*) FILTER (WHERE r1 <= 0) negative_first,
       COUNT(*) FILTER (WHERE r1 <= 0 AND r2 > 0) negative_then_positive
FROM x WHERE n1 >= 20 AND n2 >= 20;
