-- One-time P&L bookkeeping backfill (smart-trading-v2) — pairs with the code fix in
-- SignalsService.closeWithPrice / TradesService.manualClose + common/risk.ts (2026-07-13).
-- Corrects HISTORICAL closed trades that were booked before the fix. Fully idempotent.
--
-- ┌── NOT AUTO-APPLIED — review counts, confirm with owner, then run: ────────────┐
-- │   ssh work-pc 'docker exec -i smart-trading-v2-db psql -U trader \             │
-- │       -d smart_trading' < infra/scripts/backfill-pnl-bookkeeping.sql           │
-- └──────────────────────────────────────────────────────────────────────────────┘
--
-- Two corrections:
--  1. realizedPnl gap: on a CLOSED trade remainingQty=0, so ALL P&L is realized —
--     realizedPnl must equal pnl. Old one-shot closes left it at the partial-only
--     sum (0). (~6 rows as of 2026-07-13.)
--  2. Scratch band: trades within 0.1R of breakeven were booked WIN/LOSS; reclassify
--     to BREAKEVEN so win-rate / profit factor aren't distorted. (~8 rows.)
--     BREAKEVEN_R here (0.1) MUST match common/risk.ts BREAKEVEN_R.

BEGIN;

-- 1. realizedPnl := pnl for every closed trade where they diverge.
UPDATE "Trade"
SET "realizedPnl" = "pnl"
WHERE status = 'CLOSED'
  AND round("realizedPnl", 2) <> round("pnl", 2);

-- 2. Reclassify sub-0.1R closes as BREAKEVEN (only where riskAmount is known).
UPDATE "Trade"
SET outcome = 'BREAKEVEN'
WHERE status = 'CLOSED'
  AND outcome IN ('WIN', 'LOSS')
  AND "riskAmount" > 0
  AND abs("pnl") <= 0.1 * "riskAmount";

COMMIT;
