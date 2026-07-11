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
-- v2 FUNDED closed P&L, 2026-06-09 → 2026-07-10 (113 trades, net -Rs 2,704).
-- Pruned strategies (negative in BOTH v1 and v2 live — consistent with the v1 cut):
--   Fibonacci_Golden_Zone   -Rs 2,619   0W / 4L   (~97% of the whole book's net loss;
--                                                   every big loser -1.00R; analyst F3
--                                                   offender: backtest +151% vs live 0/4)
--   VWAP_Supertrend          -Rs  292   5W / 6L
--   Volume_Profile_POC       -Rs  170  11W / 13L
--
-- WATCH (negative but thin sample or near-breakeven — NOT cut yet, revisit next review):
--   DMA20_Pullback           -Rs  908   1W / 2L   (n=3, too thin to trust either way)
--   MACD_Stoch_Confluence    -Rs  472   1W / 1L   (n=2)
--   15m_ORB                  -Rs  267   9W / 13L  (n=22, near-breakeven; watch)
--
-- NOTE: the scanner reads ActiveConfiguration (joined to Stock.isActive) to decide what
-- to scan, so deleting these cells stops new signals immediately. Existing OPEN positions
-- are unaffected — they exit via normal stop/target/time-stop rules.
-- Currently active cells being removed: Fibonacci_Golden_Zone=6, VWAP_Supertrend=2,
-- Volume_Profile_POC=5 (as of 2026-07-10).

BEGIN;

DELETE FROM "ActiveConfiguration"
WHERE "strategyName" IN ('Fibonacci_Golden_Zone', 'VWAP_Supertrend', 'Volume_Profile_POC');

COMMIT;
