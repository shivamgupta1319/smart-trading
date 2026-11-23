-- Stock: the intraday list flag and three measured figures (apps/engine/universe.py).
-- Safe to run twice. When the flag is first added, every existing stock keeps intraday
-- on, because until now every stock was fetched and tested for intraday.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'Stock' AND column_name = 'intraday') THEN
    ALTER TABLE "Stock" ADD COLUMN "intraday" BOOLEAN NOT NULL DEFAULT false;
    UPDATE "Stock" SET "intraday" = true;
  END IF;
END $$;
ALTER TABLE "Stock" ADD COLUMN IF NOT EXISTS "tradedValueCr" DOUBLE PRECISION;
ALTER TABLE "Stock" ADD COLUMN IF NOT EXISTS "dayRangePct" DOUBLE PRECISION;
ALTER TABLE "Stock" ADD COLUMN IF NOT EXISTS "lastClose" DOUBLE PRECISION;
