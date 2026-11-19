-- Starting roster for the merged product (2026-11-19).
--
-- Every strategy runs in paper; the automatic pause (cell lifecycle) sorts them out.
-- The roster is NOT picked from backtest winners: the live data showed a cell's backtest
-- rank does not predict its live result. It is every strategy on a fixed stock list:
--   * the 11 intraday strategies on 12 volatile, liquid stocks. Costs are a smaller share
--     of the risk there; these were the least-bad stocks for intraday in the 2026-11
--     backtest (docs/strategies.md).
--   * the 17 swing strategies on 15 large, liquid stocks.
-- 132 + 255 = 387 cells. Safe to re-run: existing cells are left as they are.
-- Requires the Stock rows to exist.

INSERT INTO "ActiveConfiguration" ("stockId", "strategyName", timeframe, "updatedAt")
SELECT s.id, x.name, x.tf, now()
FROM "Stock" s
CROSS JOIN (VALUES
    ('15m_ORB', '15m'),
    ('VWAP_MACD_RSI', '15m'),
    ('EMA_RSI', '5m'),
    ('MACD_Zero', '15m'),
    ('Inside_Bar', '15m'),
    ('Gap_And_Go', '5m'),
    ('CPR_Breakout', '5m'),
    ('PDH_PDL_Breakout', '5m'),
    ('BB_Mean_Reversion_Intraday', '15m'),
    ('SMC_FVG', '15m'),
    ('RVOL_ORB', '15m')
) AS x(name, tf)
WHERE s.symbol IN ('MCX', 'OLAELEC', 'IFCI', 'KAYNES', 'NATIONALUM', 'BHEL', 'VEDL',
                   'ADANIENT', 'ATGL', 'APOLLO', 'BSE', 'SUZLON')
ON CONFLICT ("stockId", "strategyName") DO NOTHING;

INSERT INTO "ActiveConfiguration" ("stockId", "strategyName", timeframe, "updatedAt")
SELECT s.id, x.name, x.tf, now()
FROM "Stock" s
CROSS JOIN (VALUES
    ('SMA44_Pullback', '1D'),
    ('EMA200_MACD', '1D'),
    ('BB_Squeeze', '1D'),
    ('RSI_Divergence', '1D'),
    ('Golden_Cross', '1D'),
    ('SuperTrend_EMA', '1D'),
    ('Bollinger_Mean_Reversion', '1D'),
    ('MACD_Stoch_Confluence', '1D'),
    ('VCP', '1D'),
    ('Episodic_Pivot', '1D'),
    ('Break_And_Retest', '1D'),
    ('EMA_10_50_Cross', '1D'),
    ('DMA20_Pullback', '1D'),
    ('Fibonacci_Golden_Zone', '1D'),
    ('MTF_Alignment', '1D'),
    ('Channel_Oscillation', '1D'),
    ('Volume_Climax', '1D')
) AS x(name, tf)
WHERE s.symbol IN ('HDFCBANK', 'ICICIBANK', 'RELIANCE', 'SBIN', 'INFY', 'TCS', 'LT', 'ITC',
                   'BHARTIARTL', 'M&M', 'NTPC', 'COALINDIA', 'TATASTEEL', 'HINDALCO', 'BEL')
ON CONFLICT ("stockId", "strategyName") DO NOTHING;

SELECT status, COUNT(*) AS cells FROM "ActiveConfiguration" GROUP BY status;
