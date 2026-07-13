-- BacktestReport trust (FEAT-001 Phase 1): make the report table hold exactly ONE
-- row per (stock × strategy × timeframe), version-stamped, so the stored leaderboard
-- stops mixing engine versions and append-only duplicates that won't reproduce.
--
-- Applied by hand to the live DB (docker exec psql), matching the operational
-- pattern of the two prior migrations (drop_trade_funding_status, stock_sector) —
-- NOT via `prisma migrate deploy`. Idempotent so a re-run is harmless.

-- 1. New columns. engineVersion defaults to 'unversioned' so pre-existing rows are
--    clearly marked as produced by an unknown (pre-C3) engine.
ALTER TABLE "BacktestReport"
  ADD COLUMN IF NOT EXISTS "engineVersion" TEXT NOT NULL DEFAULT 'unversioned';

ALTER TABLE "BacktestReport"
  ADD COLUMN IF NOT EXISTS "updatedAt" TIMESTAMP(3);
-- Backfill updatedAt = createdAt for existing rows (honest "last computed" time),
-- then lock in the default + NOT NULL for future writers.
UPDATE "BacktestReport" SET "updatedAt" = "createdAt" WHERE "updatedAt" IS NULL;
ALTER TABLE "BacktestReport" ALTER COLUMN "updatedAt" SET DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE "BacktestReport" ALTER COLUMN "updatedAt" SET NOT NULL;

-- 2. Collapse duplicates to the NEWEST row per cell (max createdAt, tiebreak max id).
DELETE FROM "BacktestReport" a
USING "BacktestReport" b
WHERE a."stockId" = b."stockId"
  AND a."strategyName" = b."strategyName"
  AND a."timeframe" = b."timeframe"
  AND (a."createdAt" < b."createdAt"
       OR (a."createdAt" = b."createdAt" AND a."id" < b."id"));

-- 3. Enforce one row per cell (the UPSERT conflict target).
ALTER TABLE "BacktestReport"
  DROP CONSTRAINT IF EXISTS "BacktestReport_stockId_strategyName_timeframe_key";
ALTER TABLE "BacktestReport"
  ADD CONSTRAINT "BacktestReport_stockId_strategyName_timeframe_key"
  UNIQUE ("stockId", "strategyName", "timeframe");
