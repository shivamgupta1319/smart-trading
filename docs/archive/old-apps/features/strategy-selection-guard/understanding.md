# FEAT-003 — Strategy-Level Selection Guard · Understanding

## Origin

From analyst finding **F4**, refined across both reports
([2026-06-12](../../agent-reports/2026-06-12-whats-not-working.md) →
[2026-06-16](../../agent-reports/2026-06-16-whats-not-working.md)). The 06-16 report
narrowed the concern: the broken Bollinger cells are **already quarantined** (zero of 93
monitored cells are net-negative on reliable samples). The residual risk is a *future*
auto-select re-promoting a **lucky positive cell** of a structurally-broken strategy.

## Problem statement

Auto-select gates on **per-cell** quality and already rejects negative-ROI cells
([auto_select.py:204-238](../../../apps/engine/routers/auto_select.py#L204-L238):
in-sample ROI > 0, profit factor, drawdown, return/DD, walk-forward, Monte-Carlo). What
it does **not** check is the **strategy as a whole**. A strategy whose reliable-sample
average ROI is deeply negative can still expose one lucky cell that clears every per-cell
gate, and that cell can be selected.

Evidence (deduped, reliable ≥20-trade samples, 06-16 report):
- **BB_Mean_Reversion_Intraday (15m):** −14.92% avg, **15/15 cells negative.**
- **Bollinger_Mean_Reversion (1D):** −21.22% avg, 5/8 negative — yet its one *monitored*
  cell is **HDFCBANK 1D +29.0% / 18 trades**, a positive outlier the per-cell gate
  happily admits. Walk-forward expectation: it regresses toward the −21% strategy mean.

So a single small-sample positive cell of a strategy the data says is broken can leak
into the live monitored set. The guard closes that leak.

## Why this depends on FEAT-001

To judge a *strategy-level* average honestly we need the **deduped, capped, latest-per-cell**
table from [FEAT-001](../backtest-report-trust/understanding.md). On the raw append-only
table a strategy's average is polluted by duplicate re-runs and the +187%/−46k compounding
artifacts — so a guard computed on it would be measuring noise. Build FEAT-001 first;
this guard consumes its output.

## Non-goals / out of scope

- **No hardcoded Bollinger blocklist.** The guard is data-driven (any strategy whose
  average is negative), so it generalizes and self-updates as data grows — not a
  name list that rots.
- **No change to the per-cell gates.** Those stay; this is an *additional* strategy-level
  gate layered on top.
- **No removal of strategies from the registry.** A strategy stays available; it is just
  ineligible for auto-select while its average is negative, and becomes eligible again if
  its data turns positive on reliable samples.

## Actors

| Actor | Interest |
|-------|----------|
| Auto-select (`auto_select.py`) | Adds a strategy-level eligibility check before per-cell gating. |
| Deduped BacktestReport (FEAT-001) | Source for the trustworthy per-strategy average. |
| Monitored set / live signals | Benefits: structurally-broken strategies can't leak a lucky cell. |
| Analyst agent | Validates that no monitored cell belongs to a negative-average strategy. |

## Key decision — guard rule

A strategy is **ineligible** for auto-select when, over its deduped cells with
`totalTrades ≥ MIN_RELIABLE` (e.g. 20), its **average roiPercentage ≤ 0** (configurable
threshold, default 0). Cells of ineligible strategies are rejected with a new
`gate: "strategy-average"` rejection reason for transparency in the run summary.

Open question for review: require a *minimum number of reliable cells* (e.g. ≥3) before
the strategy-average gate can fire, so a brand-new strategy with one cell isn't blocked or
admitted on a single sample. Default: require ≥3 reliable cells, else fall back to
per-cell gates only and flag the strategy as "insufficient data."

**Open question — data source (resolve at Phase 1, see review-notes.md):** the per-cell
gates use *freshly computed* in-loop metrics
([auto_select.py:199](../../../apps/engine/routers/auto_select.py#L199)), but a strategy
average from the persisted (deduped) `BacktestReport` is a *snapshot* and can disagree.
Either (A) read the persisted deduped table (simple, snapshot-stale) or (B) accumulate this
run's fresh per-cell metrics and apply the guard as a consistent second pass. Decide and
record at implementation.

## Acceptance criteria

1. Auto-select computes a per-strategy reliable-sample average from the **deduped**
   table (FEAT-001) and rejects every cell of a strategy whose average ≤ threshold.
2. With current data, both Bollinger strategies are ineligible; the HDFCBANK 1D
   Bollinger_Mean_Reversion cell is **not** selectable despite being +29%.
3. The threshold and the `MIN_RELIABLE` / min-reliable-cells counts are configurable.
4. Rejections surface a `strategy-average` gate reason in the auto-select summary.
5. A strategy with insufficient reliable cells is handled per the decided fallback (not
   silently admitted or blocked) and is logged as such.
6. No regression to the existing per-cell gates; a positive-average strategy's good cells
   are still selected exactly as today.
