-- Strategy-testing lab: the FUNDED/SHADOW dual-track is removed. Every signal is now a
-- real mock-money trade sized off its own per-cell ₹10k compounding fund, so the funding
-- label and its index are no longer needed.

DROP INDEX IF EXISTS "Trade_status_fundingStatus_idx";

ALTER TABLE "Trade"
  DROP COLUMN IF EXISTS "fundingStatus";
