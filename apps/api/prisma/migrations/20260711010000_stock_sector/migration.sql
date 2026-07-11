-- Sector tag on the tradeable Stock universe so the portfolio risk engine can bucket
-- open positions by sector (previously every trade fell into "Unknown" because only
-- NseStock carried a sector). Backfilled by apps/engine/populate_sectors.py.

ALTER TABLE "Stock"
  ADD COLUMN IF NOT EXISTS "sector" TEXT;
