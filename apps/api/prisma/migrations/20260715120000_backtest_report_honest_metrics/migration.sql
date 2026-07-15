-- BacktestReport honest metrics (audit 2026-07-15, F3).
--
-- The engine computes 15 metrics per cell but only 7 were ever persisted. The four
-- that actually describe EDGE — avgRMultiple above all, which base.py's own comment
-- calls "the honest edge metric to rank cells on" — were computed and thrown away.
-- So every judgement (owner's and auto-select's leaderboard) fell back to
-- roiPercentage, which is raw-cumulative and window-dependent (1D ~5.1y vs 15m/5m
-- ~4.7mo => ~13x incomparable). That is the root cause of "12% ROI must mean the
-- strategy is bad": ranked by avgR the picture inverts.
-- See docs/agent-reports/2026-07-15-v1-v2-engine-audit.md.
--
-- Applied BY HAND to the live DB (docker exec psql), matching every prior migration
-- here — NOT via `prisma migrate deploy`. Idempotent, so a re-run is harmless.

-- NULLable on purpose: existing rows genuinely do not know these values. Defaulting
-- them to 0 would assert "zero edge / zero drawdown", which is a lie the UI would
-- then rank on. NULL reads as "not computed yet" and disappears on the next Run All.
ALTER TABLE "BacktestReport"
  ADD COLUMN IF NOT EXISTS "avgRMultiple"   DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS "profitFactor"   DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS "maxDrawdownPct" DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS "expectancy"     DOUBLE PRECISION;

-- Calendar years actually covered by the cell's bars, measured from the data (NOT a
-- per-timeframe constant): lets the UI show an annualised ROI that stays correct as
-- the stored window grows, and makes 1D vs 15m cells comparable for the first time.
ALTER TABLE "BacktestReport"
  ADD COLUMN IF NOT EXISTS "spanYears" DOUBLE PRECISION;
