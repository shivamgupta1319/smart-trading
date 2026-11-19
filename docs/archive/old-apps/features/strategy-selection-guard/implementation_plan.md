# FEAT-003 — Strategy-Level Selection Guard · Implementation Plan

One vertical slice, well under 500 LOC, in the engine's auto-select path only. A single
branch + PR off `roadmap-v2`, against the DB clone per
[v2-environment.md](../../v2-environment.md).

**Hard dependency:** [FEAT-001](../backtest-report-trust/implementation_plan.md) must have
landed (deduped, capped, latest-per-cell table). Until then this feature stays `BLOCKED` —
a strategy average over the raw append-only table is noise.

---

## Phase 1 — Strategy-average eligibility gate

**Goal:** auto-select rejects every cell of a strategy whose deduped reliable-sample
average ROI is ≤ threshold.

1. Add config to [auto_select.py](../../../apps/engine/routers/auto_select.py) near the
   existing gate constants ([auto_select.py:44](../../../apps/engine/routers/auto_select.py#L44)):
   `STRATEGY_AVG_MIN_ROI` (default 0.0), `MIN_RELIABLE_TRADES` (default 20),
   `MIN_RELIABLE_CELLS` (default 3), all env-overridable.
2. Before the per-stock loop, compute per-strategy averages from the **deduped**
   `BacktestReport` (FEAT-001 makes the table latest-per-cell, so a plain
   `avg(roiPercentage) ... WHERE totalTrades >= MIN_RELIABLE_TRADES GROUP BY strategyName`
   is now honest). Build `eligible: dict[strategyName -> bool]`.
3. Apply the fallback for strategies with `< MIN_RELIABLE_CELLS` reliable cells (per the
   decided rule in understanding.md): default = treat as "insufficient data," skip the
   strategy-average gate, log it.
4. In the per-stock loop, add the gate **before** the per-cell checks:
   ```python
   if not eligible.get(sname, True):
       rejections.append({"symbol": symbol, "gate": "strategy-average",
                          "value": strategy_avg[sname]})
       continue
   ```
5. Include the strategy-average decision in the per-strategy run summary so a user can see
   why a strategy contributed zero picks.
6. Tests: a strategy whose reliable cells average negative contributes zero candidates even
   when one cell would pass per-cell gates; a positive-average strategy is unaffected; the
   insufficient-data fallback behaves as decided.

**Done when:** all ACs. ~60–120 LOC incl. tests.

---

## Sequencing & rollback

```
(FEAT-001 landed) → review-docs → Phase 1 (PR) → verify-feature
```

- Single-PR revert. Pure additive gate; reverting restores today's per-cell-only behavior.
- No migration, no schema change, no live-stack change until promotion.

## Validation note (from F4)

Walk-forward HDFCBANK Bollinger_Mean_Reversion 1D out-of-sample and confirm it regresses
toward the −21% strategy mean — i.e. the cell the guard newly blocks was indeed luck, not
edge. Record this in the verification report as the falsification test.
