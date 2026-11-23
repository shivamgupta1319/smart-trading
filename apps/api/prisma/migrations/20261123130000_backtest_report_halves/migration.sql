-- BacktestReport: average R of each half of the trades, for the live rule. Safe to run twice.
ALTER TABLE "BacktestReport" ADD COLUMN IF NOT EXISTS "rFirstHalf" DOUBLE PRECISION;
ALTER TABLE "BacktestReport" ADD COLUMN IF NOT EXISTS "rSecondHalf" DOUBLE PRECISION;
