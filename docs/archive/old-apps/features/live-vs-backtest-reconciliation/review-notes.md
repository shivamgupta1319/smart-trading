# FEAT-004 — Live-vs-Backtest Reconciliation · Review Notes

- **Reviewed:** 2026-06-17 (provisional — feature is BLOCKED)
- **Docs:** understanding.md, implementation_plan.md, tasks.md, verification.md.

## Verdict: **APPROVE-AS-BLOCKED**

The docs correctly frame this as a *measurement/feedback* feature, not a code-bug fix, and
correctly mark it BLOCKED on FEAT-001 (trustworthy backtest) **and** FEAT-002 (trustworthy
live R). Acceptance criteria are explicitly provisional, which is appropriate — their final
shape depends on what FEAT-001's corrected numbers look like. No implementation should begin.

## Confirms

- Dependency on FEAT-002 is real and correctly listed: live realized R is itself wrong until
  the BREAKEVEN band + realizedPnl fixes land, so reconciling against it now would compare two
  wrong numbers.
- Re-uses existing engine helpers (`_walk_forward`, `_monte_carlo` at
  [auto_select.py:110-121](../../../apps/engine/routers/auto_select.py#L110-L121)) rather than
  rebuilding — right call.
- Phase 1 is read-only (emits a report file), Phase 2 (auto-select trust signal) is optional
  and flag-gated — good risk posture.

## Notes for the unblock review (not actionable now)

- **Define "inside the band" precisely** before Phase 1: which band (MC p5? a CI?), and the
  minimum live-trade count per cell to even attempt a verdict (the largest live cell today is
  5 trades — most cells will be "insufficient live data," and the report must say so rather
  than over-claiming).
- **Regime confound:** a single ~7-day live window cannot cleanly separate "overstated
  backtest" from "regime." The report should label low-confidence cells as such, not force a
  binary verdict. Already implied by AC #4; make it explicit at unblock.
- Reconfirm the 25/93 thin-sample monitored-cell figure against the live DB at unblock (it
  will have moved).

## Required doc edits before implementation

None now — re-review (`/review-docs`) when FEAT-001 + FEAT-002 reach `DONE` and firm up the
provisional ACs against real corrected output.

## Status

Index `status` stays **BLOCKED** with `docsReviewed: true` (provisional).
