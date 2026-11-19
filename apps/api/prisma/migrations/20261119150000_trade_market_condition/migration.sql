-- The market's condition when a trade was opened, sent by the scanner with each signal.
-- Labels only: nothing is blocked on them. Idempotent.
ALTER TABLE "Trade"
  ADD COLUMN IF NOT EXISTS "regimeAtEntry"          TEXT,
  ADD COLUMN IF NOT EXISTS "marketDirectionAtEntry" TEXT,
  ADD COLUMN IF NOT EXISTS "breadthAtEntry"         DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS "alignedWithMarket"      BOOLEAN;
