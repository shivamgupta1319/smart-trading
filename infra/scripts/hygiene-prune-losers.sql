-- Hygiene prune (smart-trading-v2) — rationale in docs/performance-review-2026-07.md
-- Remove chronically unprofitable strategies from live scanning. Fully reversible:
-- re-run POST /api/engine/auto-select, or re-insert the ActiveConfiguration rows.
--
-- ┌── NOT AUTO-APPLIED ─────────────────────────────────────────────────────────┐
-- │ This changes LIVE scanning behaviour. Review the numbers, confirm with the   │
-- │ owner, THEN run manually:                                                     │
-- │   ssh work-pc 'docker exec -i smart-trading-v2-db psql -U trader \            │
-- │       -d smart_trading' < infra/scripts/hygiene-prune-losers.sql              │
-- └──────────────────────────────────────────────────────────────────────────────┘
--
-- APPLIED 2026-07-11 (per-cell ₹10k + leverage model, after the in-place migration).
-- Net P&L by strategy over ALL closed trades at that time:
--   Volume_Profile_POC     -Rs 3,696   23W / 28L   (5 cells removed)
--   Fibonacci_Golden_Zone  -Rs 2,619    0W /  4L   (6 cells removed; analyst F3 offender,
--                                                    wide 11% stops = top risk-engine heat)
--
-- KEPT (was on the old cut list, but PROFITABLE under the new leverage sizing — do NOT prune):
--   VWAP_Supertrend        +Rs   768   11W /  6L
--
-- RE-APPLIED 2026-07-13 (audit — see docs/agent-reports/). auto-select had RE-PROMOTED
-- both prior cuts (Fibonacci_Golden_Zone ×3, Volume_Profile_POC ×2 back in ActiveConfiguration),
-- so a one-off DELETE is NOT sticky — the real fix is the auto-select selection guard (FEAT).
-- Cut list this round (currently-active, clear losers over all closed trades):
--   DMA20_Pullback         -Rs 1,890    2W /  6L   PF 0.25  avg -0.38R   (4 cells)
--   Fibonacci_Golden_Zone  -Rs 2,619   (hist)      0W /  4L              (3 cells, re-added)
--   Volume_Profile_POC     -Rs 3,696   (hist)                            (2 cells, re-added)
-- NOT cut (checked, do NOT prune):
--   15m_ORB      -Rs 1,554 overall BUT the loss was BSE·15m_ORB (already inactive); the
--                3 active cells are net +Rs 892 (ATGL +1145, VEDL +130, MTARTECH -383).
--   MACD_Stoch_Confluence  thin sample (1-2 trades) — on watch, not enough evidence to cut.
--
-- NOTE: the scanner reads ActiveConfiguration (joined to Stock.isActive) to decide what to
-- scan, so deleting these cells stops NEW signals immediately. Existing OPEN positions are
-- unaffected — they exit via normal stop/target/time-stop rules (e.g. the open IFCI
-- Fibonacci_Golden_Zone position remains until it hits its stop/target).
--
-- RE-APPLIED 2026-07-14 (avg-loss > avg-win audit — docs/agent-reports/2026-07-14-...). The 3
-- "kept" 15m_ORB cells have since turned negative, so this round adds CELL-SPECIFIC cuts (not the
-- whole strategy — OLAELEC·15m_ORB stays, +Rs 425 / 100% win). Over all closed trades now:
--   ATGL·15m_ORB      (stockId 12)  -Rs 690   18 trades  50% win   -> CUT
--   VEDL·15m_ORB      (stockId 10)  -Rs 677   14 trades  43% win   -> CUT
--   MTARTECH·15m_ORB  (stockId 24)  -Rs 670    6 trades  50% win   -> CUT
--   OLAELEC·15m_ORB   (stockId 22)  +Rs 425    1 trade  100% win   -> KEEP (do NOT delete)
--   BSE·MACD_Stoch_Confluence (stockId 7) -Rs 573  1 trade  (MID swing, wide stop) -> CUT (thin
--                     sample; owner may prefer to let auto-select judge it instead).
-- The durable fix is still the auto-select selection guard + denylist (F5): after this prune, run
-- the real quality-gated `POST /api/engine/auto-select` so the roster becomes the quality picks and
-- the deny-listed chronic losers can't be re-promoted. A one-off DELETE alone is not sticky.
-- Reverse a cell: re-INSERT its ActiveConfiguration row, or re-run auto-select.
--
-- Current work-pc AUTOSELECT_DENYLIST = "DMA20_Pullback,Fibonacci_Golden_Zone,Volume_Profile_POC,BSE|15m_ORB".
-- To make THIS round sticky, extend it in the work-pc .env to (then restart engine/scanner):
--   AUTOSELECT_DENYLIST=DMA20_Pullback,Fibonacci_Golden_Zone,Volume_Profile_POC,BSE|15m_ORB,ATGL|15m_ORB,VEDL|15m_ORB,MTARTECH|15m_ORB,BSE|MACD_Stoch_Confluence
-- (denylist matches whole strategy "Name" or a cell "SYMBOL|Strategy" — auto_select.py:60-63,179-189.)

BEGIN;

-- 2026-07-11/13 rounds: whole-strategy cuts (every cell of these strategies loses).
DELETE FROM "ActiveConfiguration"
WHERE "strategyName" IN ('DMA20_Pullback', 'Fibonacci_Golden_Zone', 'Volume_Profile_POC');

-- 2026-07-14 round: CELL-SPECIFIC cuts (keep the other cells of these strategies).
DELETE FROM "ActiveConfiguration"
WHERE ("strategyName" = '15m_ORB'               AND "stockId" IN (12, 10, 24))  -- ATGL, VEDL, MTARTECH
   OR ("strategyName" = 'MACD_Stoch_Confluence' AND "stockId" = 7);             -- BSE

COMMIT;
