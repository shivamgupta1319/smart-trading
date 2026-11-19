# FEAT-002 — Live Trade Bookkeeping Hygiene · Verification

How we prove each acceptance criterion. All checks run against the **DB clone**; the
running stack is untouched until promotion.

## AC #1 / #2 — BREAKEVEN band reclassifies scratches and changes win-rate

- **Replay check:** recompute `outcome` for the current 40 closed trades with the band.
  Expect ids **40, 50, 22** (WIN → BREAKEVEN) and **51** (LOSS → BREAKEVEN) to flip.
  ```sql
  SELECT id, pnl, "riskAmount", outcome,
         ROUND(ABS(pnl / NULLIF("riskAmount",0))::numeric, 3) AS r_mult
  FROM "Trade" WHERE status='CLOSED' ORDER BY r_mult ASC LIMIT 8;
  ```
- **Win-rate delta:** record win-rate before (52.5%, current `WIN/allFundedClosed`) and
  after (`WIN/(WIN+LOSS)`, BREAKEVEN excluded from both). Must change and be documented in
  the verification report. Check both the portfolio
  ([trades.service.ts:59-61](../../../apps/api/src/trades/trades.service.ts#L59-L61)) and
  per-strategy ([trades.service.ts:94-126](../../../apps/api/src/trades/trades.service.ts#L94-L126))
  surfaces.
- **riskAmount=0 case:** a closed trade with `riskAmount=0` classifies via the
  `capitalUsed`/floor fallback and does not produce `NaN`/`Infinity`. Unit test asserts no
  divide-by-zero.

## AC #3 — single source of outcome logic

- Grep proves only one `classifyOutcome` definition and that both call sites import it:
  ```
  grep -rn "WIN.*LOSS.*BREAKEVEN\|classifyOutcome" apps/api/src
  ```
  Expect the inline ternary at `signals.service.ts:286` / `trades.service.ts:311` gone.

## AC #4 — realizedPnl reconciles to pnl (decision A)

- **Reconciliation:** over CLOSED trades, the two sums match (currently off by ₹813):
  ```sql
  SELECT ROUND(SUM("realizedPnl")::numeric,2) AS realized,
         ROUND(SUM(pnl)::numeric,2)          AS pnl,
         ROUND(SUM("realizedPnl" - pnl)::numeric,2) AS gap
  FROM "Trade" WHERE status='CLOSED';   -- gap must be 0.00
  ```
- **Unit:** open → full close (no partial) ⇒ `realizedPnl === pnl`; open → partial →
  full close ⇒ `realizedPnl === pnl === partialLeg + finalLeg`.

## AC #5 — band is configurable

- Set `BREAKEVEN_R` via env to 0.0 and confirm no trade classifies BREAKEVEN; set to 0.2
  and confirm more borderline trades do. No code edit required.

## AC #6 — no silent history rewrite

- Without running Phase 3, confirm existing rows are unchanged after deploy (only newly
  closed trades use the new logic). If Phase 3 runs, confirm a CSV snapshot exists and the
  win-rate/reconciliation deltas are recorded.

## Regression guard

- The full close path delegated from the partial→full branch
  ([signals.service.ts:233-243](../../../apps/api/src/signals/signals.service.ts#L233-L243))
  must produce the same `outcome`/`realizedPnl` as a direct close — add a test covering
  the partial-then-final path so the two close routes can't diverge.
