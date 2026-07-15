-- Prune cells with no evidence, BEFORE the F1 live-fetch fix wakes them (2026-07-15).
--
-- Context: the scanner fetched ~102 daily bars while these strategies guard at 200-250,
-- so they silently returned all-zeros and produced 0 live signals for the system's entire
-- life (audit F1). Fixing the fetch turns 20 dormant cells ON at once. Re-running them on
-- the current engine (time-stop disabled, honest metrics persisted) showed all 20 have a
-- positive avgR -- but 11 of them rest on 1-3 trades in FIVE YEARS. avgR 4.722 off one
-- trade is not an edge, it is the same best-of-N illusion that made SMA44_Pullback look
-- good on MTARTECH while averaging -1.15% across 19 stocks.
--
-- Gate = the system's OWN AUTOSELECT_MIN_TRADES (10) + positive avgR. Not a new invention.
--
--   KEEP (9): EMA200_MACD    x5  10-18 trades, avgR 0.154-1.323
--             SMA44_Pullback x4  12-19 trades, avgR 0.318-0.739
--   PRUNE(11): Golden_Cross   x6  1-3 trades   <- best avgR of all, least evidence
--              RSI_Divergence x4  1-3 trades
--              Volume_Climax  x1  1 trade (8 trades across all 19 cells in 5y)
--
-- Pruned strategies are NOT condemned: at strategy level Golden_Cross (49 trades, 1.373R)
-- and RSI_Divergence (57 trades, 0.541R) look strong -- they just trade ~once per 2 years
-- per cell, so no single cell can prove itself. They can return via auto-select on the new
-- 60-stock universe if they earn it there. Volume_Climax is genuinely dead.
--
-- Applied by hand (docker exec psql), the pattern every migration/hygiene script here uses.
-- Idempotent. Deactivates rather than deletes, so the roster history stays intact.

BEGIN;

-- Sanity: this must remove exactly 11 rows. If it doesn't, the roster drifted -- stop and look.
DO $$
DECLARE n INT;
BEGIN
  SELECT COUNT(*) INTO n FROM "ActiveConfiguration"
  WHERE "strategyName" IN ('Golden_Cross', 'RSI_Divergence', 'Volume_Climax');
  IF n <> 11 THEN
    RAISE EXCEPTION 'Expected 11 unproven cells, found %. Roster changed since the 2026-07-15 audit — re-check before pruning.', n;
  END IF;
END $$;

DELETE FROM "ActiveConfiguration"
WHERE "strategyName" IN ('Golden_Cross', 'RSI_Divergence', 'Volume_Climax');

COMMIT;
