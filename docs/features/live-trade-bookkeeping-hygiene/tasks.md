# FEAT-002 — Live Trade Bookkeeping Hygiene · Tasks

Status legend: `TODO` · `IN_PROGRESS` · `DONE`

## Gate
- [ ] `TODO` — Confirm risk reference field on `Trade` (riskAmount vs derive vs capitalUsed)
- [ ] `TODO` — Confirm realizedPnl decision A (reconcile) vs B (deprecate) with user
- [ ] `TODO` — `/review-docs` approves scope

## Phase 1 — BREAKEVEN band
- [ ] `TODO` — Shared `classifyOutcome(pnl, riskRef)` helper with `BREAKEVEN_R` (default 0.1)
- [ ] `TODO` — riskRef fallback chain riskAmount→capitalUsed→floor (div-by-zero guard)
- [ ] `TODO` — Wire helper into `signals.service.ts:286` and `trades.service.ts:311`
- [ ] `TODO` — `BREAKEVEN_R` configurable (constant + env)
- [ ] `TODO` — Win-rate `WIN/(WIN+LOSS)` at trades.service.ts:59-61 AND :94-126; verify telegram emoji
- [ ] `TODO` — Tests: +0.04R→BE, −0.114R→BE, +1R→WIN, −1R→LOSS, riskAmount=0 no-crash, WR excludes BE
- [ ] `TODO` — PR off `roadmap-v2`; CI green

## Phase 2 — Reconcile realizedPnl
- [ ] `TODO` — Write `realizedPnl = round2(totalPnl)` on full close (signals.service.ts:288-304)
- [ ] `TODO` — Patch trades.service.ts:309 close path too; confirm partial→full delegates
- [ ] `TODO` — Tests: no-partial close ⇒ realizedPnl===pnl; partial+final ⇒ reconciles
- [ ] `TODO` — PR; CI green

## Phase 3 — Backfill (optional, gated on approval)
- [ ] `TODO` — Reviewed backfill script; CSV snapshot of CLOSED trades first
- [ ] `TODO` — Apply to clone; record win-rate delta; assert SUM(realizedPnl)=SUM(pnl)
- [ ] `TODO` — User approval before running on live

## Close-out (`verify-feature`)
- [ ] `TODO` — All ACs traced green
- [ ] `TODO` — Re-run analyst; confirm F5 no longer reproduces; update report verdicts
