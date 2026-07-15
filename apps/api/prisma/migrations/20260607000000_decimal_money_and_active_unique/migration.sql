-- Phase 2 — Financial integrity
-- 1) Convert ledger money columns from double precision (Float) to NUMERIC(18,4)
--    so stored prices/P&L don't accumulate IEEE-754 drift.
-- 2) Add a PARTIAL UNIQUE index to prevent duplicate ACTIVE signals for the same
--    (stockId, strategyName) — closes the TOCTOU race in SignalsService.create().

ALTER TABLE "LiveSignal"
  ALTER COLUMN "entryPrice" TYPE NUMERIC(18,4),
  ALTER COLUMN "stopLoss"   TYPE NUMERIC(18,4),
  ALTER COLUMN "target"     TYPE NUMERIC(18,4);

ALTER TABLE "Trade"
  ALTER COLUMN "entryPrice"       TYPE NUMERIC(18,4),
  ALTER COLUMN "exitPrice"        TYPE NUMERIC(18,4),
  ALTER COLUMN "stopLoss"         TYPE NUMERIC(18,4),
  ALTER COLUMN "target"           TYPE NUMERIC(18,4),
  ALTER COLUMN "capitalUsed"      TYPE NUMERIC(18,4),
  ALTER COLUMN "riskAmount"       TYPE NUMERIC(18,4),
  ALTER COLUMN "pnl"              TYPE NUMERIC(18,4),
  ALTER COLUMN "originalStopLoss" TYPE NUMERIC(18,4),
  ALTER COLUMN "peakPrice"        TYPE NUMERIC(18,4),
  ALTER COLUMN "realizedPnl"      TYPE NUMERIC(18,4);

CREATE UNIQUE INDEX IF NOT EXISTS "LiveSignal_active_unique"
  ON "LiveSignal" ("stockId", "strategyName")
  WHERE status = 'ACTIVE';
