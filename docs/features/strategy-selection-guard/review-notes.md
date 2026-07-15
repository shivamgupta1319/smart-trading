# FEAT-003 — Strategy-Level Selection Guard · Review Notes

- **Reviewed:** 2026-06-17
- **Docs:** understanding.md, implementation_plan.md, tasks.md, verification.md.

## Verdict: **APPROVE (docs) — implementation remains BLOCKED on FEAT-001**

The feature is well-scoped and data-driven (no Bollinger blocklist). One substantive
design issue surfaced on code review and is now recorded as the key open question; two
smaller notes. None blocks doc approval, but the open question must be resolved at
implementation time.

## Verified against code

- Per-cell gates confirmed at
  [auto_select.py:204-238](../../../apps/engine/routers/auto_select.py#L204-L238)
  (trades, ROI>0, profit factor, drawdown, return/DD, walk-forward, Monte-Carlo). The
  guard correctly layers *above* these — no regression to them.
- The existing `MIN_ROI` gate ([auto_select.py:44,208](../../../apps/engine/routers/auto_select.py#L208))
  already rejects negative-ROI *cells* — so the guard's value is strictly the
  strategy-level case (lucky positive cell of a net-negative strategy). Scope is honest.

## Key open question (must resolve before Phase 1)

**Two different data sources for "is this good?"** The per-cell gates use **freshly computed**
metrics in-loop (`m = strategy.run_backtest(df)`,
[auto_select.py:199](../../../apps/engine/routers/auto_select.py#L199)), but the proposed
strategy-average guard reads the **persisted** `BacktestReport` table. These can disagree
(the table is written by *prior* runs; FEAT-001 makes it latest-per-cell but it is still a
snapshot, not this run's fresh numbers). Risk: a strategy could be blocked on a stale
persisted average while its fresh cell metrics look fine, or vice-versa.

Two options for the implementer:
- **(A)** Compute the strategy average from the persisted **deduped** table (as drafted) —
  simple, but snapshot-stale.
- **(B)** Accumulate this run's fresh per-cell metrics first, then compute each strategy's
  average from *those* and apply the guard as a second pass — fully consistent with the
  gates, but requires a two-pass restructure of the per-stock loop.

Recommendation: **(B)** if the loop restructure is cheap; else (A) with an explicit note that
the guard reflects the last persisted snapshot. Decide at Phase 1, record the choice.

## Smaller notes

- **Averaging method:** `avg(roiPercentage)` equal-weights a 20-trade cell and a 200-trade
  cell. Consider trade-weighting, or document equal-weight as intended. Minor; default
  equal-weight is acceptable for a coarse eligibility gate.
- **Insufficient-data fallback defaults to "eligible"** (`eligible.get(sname, True)`),
  so a brand-new strategy with 1–2 negative reliable cells can still leak a cell until it
  accrues ≥3. Acceptable (conservative against over-blocking new strategies) but call it out
  in the run summary so it's visible.

## Required doc edits before implementation — **DONE**

- [x] understanding.md: add the persisted-vs-fresh data-source decision as an explicit
      open question with options A/B.

## Phase sizing

Single phase, ~60–120 LOC incl. tests — under 500, independently reviewable. ✓

## Status

Docs approved; index `status` stays **BLOCKED** (depends on FEAT-001) with `docsReviewed: true`.
