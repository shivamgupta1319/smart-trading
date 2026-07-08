-- Hygiene prune (2026-07-08) — rationale in docs/performance-review-2026-07.md
-- Remove chronically unprofitable strategies from live scanning and deactivate a
-- persistent-loser symbol. Fully reversible: re-insert ActiveConfiguration rows,
-- or set Stock.isActive = true.
--
-- Removed strategies (full-sample negatives over month-1 live):
--   Volume_Profile_POC    -Rs 29,917   PF 0.38   (already absent from configs; listed for idempotency)
--   Fibonacci_Golden_Zone  -Rs 7,340   PF 0.06
--   VWAP_Supertrend        -Rs 3,149   PF 0.85
-- Deactivated symbol:
--   ADANIPOWER            -Rs 24,779   (loss across multiple strategies)
--
-- NOTE: the scanner's get_active_configs() selects WHERE Stock.isActive = true,
-- so deactivating ADANIPOWER stops it being scanned without deleting its configs.
-- Existing OPEN positions are unaffected (they exit via normal rules / time-stop).

BEGIN;

DELETE FROM "ActiveConfiguration"
WHERE "strategyName" IN ('Volume_Profile_POC', 'Fibonacci_Golden_Zone', 'VWAP_Supertrend');

UPDATE "Stock"
SET "isActive" = false
WHERE symbol = 'ADANIPOWER';

COMMIT;
