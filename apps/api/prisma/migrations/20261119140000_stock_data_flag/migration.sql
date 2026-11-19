-- Stock.dataFlag: set by the engine when a stock's stored daily history has a move above
-- 20% that nobody has reviewed (config/known_price_actions.json). NULL = nothing to review.
-- Idempotent.
ALTER TABLE "Stock"
  ADD COLUMN IF NOT EXISTS "dataFlag"       TEXT,
  ADD COLUMN IF NOT EXISTS "dataFlagDetail" TEXT;
