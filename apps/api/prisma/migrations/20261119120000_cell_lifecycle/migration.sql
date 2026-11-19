-- Cell lifecycle (final-product plan, Phase 3).
--
-- A cell is one stock with one strategy (an ActiveConfiguration row). Until now nothing
-- ever switched a losing cell off: EMA20_Pullback lost Rs 6.56 lakh over 1,557 paper
-- trades and kept trading. Each cell now carries a status that the API sets from the
-- cell's own closed trades:
--   TESTING  default; collecting evidence
--   PROVEN   enough trades, positive after costs, in both halves
--   PAUSED   kept losing; it still paper-trades, but into the test book
-- Trade.cellStatusAtEntry records the status when the trade was opened, so the main
-- book can exclude trades taken while a cell was PAUSED.
--
-- Idempotent, like every migration here (they are applied by hand with psql).

ALTER TABLE "ActiveConfiguration"
  ADD COLUMN IF NOT EXISTS "status"          TEXT NOT NULL DEFAULT 'TESTING',
  ADD COLUMN IF NOT EXISTS "statusReason"    TEXT,
  ADD COLUMN IF NOT EXISTS "statusChangedAt" TIMESTAMP(3);

ALTER TABLE "Trade"
  ADD COLUMN IF NOT EXISTS "cellStatusAtEntry" TEXT;

CREATE INDEX IF NOT EXISTS "ActiveConfiguration_status_idx" ON "ActiveConfiguration"("status");
