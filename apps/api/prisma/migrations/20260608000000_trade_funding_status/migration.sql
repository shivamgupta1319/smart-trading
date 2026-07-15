-- Capital-constrained paper trading (dual-track).
-- Mark each Trade as FUNDED (the ₹1L account could afford it at entry — counts toward
-- portfolio ROI/P&L) or SHADOW (capital/heat was exhausted — tracked for would-be P&L only).
-- Existing rows default to FUNDED.

ALTER TABLE "Trade"
  ADD COLUMN IF NOT EXISTS "fundingStatus" TEXT NOT NULL DEFAULT 'FUNDED';

-- Speeds up the OPEN + FUNDED query used by the portfolio risk engine.
CREATE INDEX IF NOT EXISTS "Trade_status_fundingStatus_idx"
  ON "Trade" ("status", "fundingStatus");
