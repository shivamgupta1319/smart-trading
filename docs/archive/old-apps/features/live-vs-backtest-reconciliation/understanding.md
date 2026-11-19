# FEAT-004 — Live-vs-Backtest Reconciliation · Understanding

## Origin

From analyst finding **F3** (both reports) reinforced by **F1** on 06-16
([2026-06-16](../../agent-reports/2026-06-16-whats-not-working.md)): *every big live-loss
cell backtested positive.* The system trades on expectancy the live tape contradicts.

## Problem statement

There is a persistent, consistent gap between what the backtest promises and what live
delivers — and it is not yet attributable:

- 40 closed live trades net **−₹75.54** (ex the two SMC_FVG outliers: **−₹425.34 /
  −0.073R over 38**). Stop discipline is clean (16 of 19 losses are exactly −1.00R), so
  the failure is **entry/edge, not execution**.
- The worst live cells all carry **positive** deduped backtest expectancy:
  ETERNAL Fibonacci_Golden_Zone (bt +151% / live −1.00R), ADANIPOWER Volume_Profile_POC
  (bt +9.6% / live −0.65R), APOLLO EMA_RSI (bt +33.8% / live −1.00R), BSE 15m_ORB
  (bt +21.9% / live −0.86R), ATGL 15m_ORB (bt +42.6% / live −0.32R).

Two non-exclusive causes: (a) the backtest numbers are **inflated** (the compounding /
append-only artifacts FEAT-001 fixes), and (b) **regime** — one ~7-day window. We cannot
separate them until the backtest is trustworthy. This feature is the **measurement** that
does the separation and feeds it back so auto-select stops believing inflated cells.

## Why this is BLOCKED (and not just lower priority)

- **Needs FEAT-001:** a reconciliation against an inflated/duplicated backtest table just
  re-measures the artifact. The capped, deduped, deterministic table is the prerequisite
  baseline.
- **Needs FEAT-002:** live R-multiples and win-rate are themselves wrong (scratches as
  WIN, realizedPnl gap) until bookkeeping is fixed — so the live side of the comparison
  must be trustworthy too.

Until both land, any "gap" number here mixes three errors (backtest inflation, live
mislabeling, regime) and proves nothing. Documented now so it is **tracked and sequenced**,
not started.

## Non-goals / out of scope

- **No strategy logic changes.** This is analysis + a feedback signal, not a new edge.
- **No live trading halt.** It informs selection; it does not gate execution directly in v1.
- **Not a backtest-engine rewrite.** It consumes FEAT-001's corrected engine output.

## Actors

| Actor | Interest |
|-------|----------|
| Analyst agent / user | Wants a per-cell "is the live result inside the backtest's noise band?" verdict. |
| Auto-select | Could consume a "trust score" so cells with a proven live-vs-backtest gap are demoted. |
| Corrected backtest (FEAT-001) | Provides capped, deterministic expectancy + the cells to compare. |
| Live trades (FEAT-002) | Provides trustworthy realized R per cell. |

## Proposed approach (to be detailed after unblock)

1. For each **live-traded** cell, recompute capped/deduped backtest expectancy on its exact
   symbol over the live window (walk-forward), plus a **Monte-Carlo band** (the engine
   already has `_monte_carlo` / bootstrap at
   [auto_select.py:110-121](../../../apps/engine/routers/auto_select.py#L110-L121)).
2. Classify each cell: live result **inside** the corrected backtest's noise band
   (→ regime/variance, keep) vs **outside** (→ the cell's expectancy was overstated, demote).
3. Emit a per-cell **trust delta** and an explicit diff of the corrected top set vs the
   current 93 monitored cells (the 06-16 report flags **25 of 93 backed by only 1–5 backtest
   trades** as thin-selection risk to examine here).

## Acceptance criteria (provisional — refine after unblock)

1. A reproducible report joins each live-traded cell to its **capped/deduped** backtest
   expectancy and a Monte-Carlo band, labelling each inside/outside the band.
2. The known offenders (ETERNAL Fibonacci, the 15m_ORB cells, APOLLO EMA_RSI) are
   re-evaluated; cells whose corrected expectancy is far below the figure auto-select used
   are flagged.
3. Output is consumable by auto-select as a demotion/trust signal (even if wiring it in is a
   follow-up phase).
4. The report distinguishes "broken rule (overstated backtest)" from "regime" per cell,
   instead of asserting one globally.
