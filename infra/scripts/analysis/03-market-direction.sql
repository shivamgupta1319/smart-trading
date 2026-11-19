-- Market direction and live results. READ-ONLY.
--
-- Run (work-pc), either database:
--   docker exec -i smart-trading-db psql -U trader -d smart_trading -P pager=off < 03-market-direction.sql
--
-- Timestamps: "Trade"."entryTime" is UTC; "HistoricalData".timestamp is IST with no zone.
-- The second query joins every trade to 15m candles and can take a few minutes.

\echo ===== monthly market direction: median stock return across the universe =====
WITH d AS (
  SELECT "stockId", to_char(timestamp, 'YYYY-MM') m,
         FIRST_VALUE(close) OVER w f,
         LAST_VALUE(close)  OVER (w ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) l
  FROM "HistoricalData" WHERE timeframe = '1D' AND timestamp >= now() - interval '8 months'
  WINDOW w AS (PARTITION BY "stockId", to_char(timestamp, 'YYYY-MM') ORDER BY timestamp)),
s AS (SELECT DISTINCT "stockId", m, 100 * (l / f - 1) ret FROM d)
SELECT m, COUNT(*) stocks,
       ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY ret))::numeric, 1) median_return_pct,
       ROUND(100.0 * AVG((ret > 0)::int), 0) pct_stocks_up
FROM s GROUP BY 1 ORDER BY 1;

\echo ===== intraday trades WITH vs AGAINST the market at entry time =====
-- Market at entry = median, across stocks, of (last completed 15m close / day open - 1).
-- WITH = BUY when above +0.15%, SELL when below -0.15%.
WITH days AS (
  SELECT "stockId", timestamp::date d, timestamp, close,
         FIRST_VALUE(open) OVER (PARTITION BY "stockId", timestamp::date ORDER BY timestamp) day_open
  FROM "HistoricalData" WHERE timeframe = '15m'),
m AS (
  SELECT d, timestamp ts,
         percentile_cont(0.5) WITHIN GROUP (ORDER BY 100 * (close / day_open - 1)) med
  FROM days GROUP BY 1, 2 HAVING COUNT(*) >= 8),
tr AS (
  SELECT id, "signalType" side, pnl, "riskAmount", "strategyName",
         ("entryTime" + interval '5 hours 30 minutes') ist
  FROM "Trade" WHERE status = 'CLOSED' AND "holdDuration" = 'INTRADAY'),
j AS (
  SELECT tr.*, (SELECT med FROM m
                WHERE m.d = tr.ist::date AND m.ts + interval '15 minutes' <= tr.ist
                ORDER BY m.ts DESC LIMIT 1) med
  FROM tr)
SELECT CASE WHEN med IS NULL THEN 'unknown (no 15m data)'
            WHEN (side = 'BUY' AND med > 0.15) OR (side = 'SELL' AND med < -0.15) THEN 'WITH market'
            WHEN (side = 'BUY' AND med < -0.15) OR (side = 'SELL' AND med > 0.15) THEN 'AGAINST market'
            ELSE 'flat market' END alignment,
       COUNT(*) n, ROUND(100.0 * AVG((pnl > 0)::int), 1) win_pct,
       ROUND(AVG(pnl / NULLIF("riskAmount", 0))::numeric, 3) avg_r,
       ROUND(SUM(pnl)::numeric, 0) pnl
FROM j GROUP BY 1 ORDER BY 1;
