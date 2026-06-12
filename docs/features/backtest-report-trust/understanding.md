# FEAT-001 — Backtest Report Trust · Understanding

## Origin

This feature comes from the first analyst-agent report,
[2026-06-12-whats-not-working.md](../../agent-reports/2026-06-12-whats-not-working.md)
(findings **F1**, **F2**, and the sizing note), **after Claude verified the findings
against the live DB.** The agent's headline ("the backtest engine is non-deterministic")
was **rejected on verification** — six consecutive identical runs prove the engine is
deterministic given fixed code+data. The *real* root causes are below.

## Problem statement

Backtest-driven rankings are not trustworthy because the `BacktestReport` table and its
consumers mishandle repeated runs and unbounded sizing:

1. **Append-only report table mixes engine versions.** `save_report()` always `INSERT`s
   ([backtest.py:50-62](../../../apps/engine/routers/backtest.py#L50-L62); mirrored in
   [auto_select.py:130-141](../../../apps/engine/routers/auto_select.py#L130-L141)). The
   table holds **1363 rows for only 323 distinct (stock×strategy×timeframe) cells** — up to
   21 copies of one cell — and those copies were computed by *different versions of the
   engine over time*. Example: ADANIPOWER SuperTrend_EMA 1D shows ROI 30.7 → 243.6 → 639
   across a single 2026-06-08 development window (commits `f61ef27`, `28820b8`), then stable.
2. **The leaderboard averages across all rows without dedup.** `avg(roiPercentage) GROUP BY
   strategyName` over every row ([advanced_backtest.py:21-59](../../../apps/engine/routers/advanced_backtest.py#L21-L59))
   over-weights cells that were re-run more often, and treats duplicate re-runs as
   independent samples (`confidence = reports / 10`). De-duping to latest-per-cell drops
   overall avg ROI **26.96% → 15.00%** and raises the negative-cell share 20.9% → **36.5%**.
3. **Uncapped compounding position sizing.** `qty = max(1, int(current_capital / entry))`
   compounds unbounded ([base.py:161](../../../apps/engine/strategies/base.py#L161)); the
   configured no-leverage cap `max_position_value`
   ([backtest_config.py:59-61](../../../apps/engine/backtest_config.py#L59-L61)) is **dead
   code, never applied** — producing the absurd 639% single-slot ROI (₹10k → ₹73.9k over 13
   trades).

## Non-goals / explicitly out of scope

- **No phantom-RNG hunt.** The engine is deterministic; do not add seeds or chase randomness.
- **No strategy logic changes.** This is a correctness/bookkeeping fix, not a new edge.
- **No walk-forward gate.** A bug fix needs no out-of-sample validation; we validate by
  reproducing the bug and asserting it's gone.
- The live-vs-backtest gap (F3) and the Bollinger-strategy removal (F4) are **separate**
  future features — they depend on *this* one producing trustworthy numbers first.

## Actors

| Actor | Interest |
|-------|----------|
| Auto-select (`auto_select.py`) | Picks monitored stock×strategy cells; must not re-pollute the table and must read trustworthy expectancy. |
| Leaderboard (`/leaderboard`) | Ranks strategies; must rank on latest-per-cell, with honest confidence. |
| Monitored-stocks view (`configs.service.ts`) | Already dedupes to latest-per-cell — the **reference pattern** to mirror. |
| Analyst agent / user | Needs the report table to be a source of latest truth, not a mixed-version pile. |

## Key decision — RESOLVED (user, 2026-06-12): Option A

**The position-sizing model.** Today sizing *compounds* a single ₹10k slot unbounded. The
chosen fix:

- **✅ (A — CHOSEN) Fixed-slot, non-compounding, capped at one slot.** Size every trade from a
  fixed ₹10k slot (`qty = max(1, int(min(slot_capital, max_position_value) / entry))`), no
  compounding. ROI becomes "return on one slot," bounded and comparable across cells, and
  matches the v2 equal-weight 10×₹10k slot model. Single-cell ROIs can no longer blow up.
- ~~(B) Keep compounding but cap per-position notional at one slot.~~ Rejected — still rewards
  trade-frequency over edge and is less comparable across cells.

**Rationale (per the discussion):** a per-cell backtest answers *"how good is this strategy on
this stock?"* and needs a fixed, comparable yardstick — compounding one stock in isolation
measures trade-count × luck, not edge, and the uncapped version uses leverage the slot doesn't
have. **This does NOT remove compounding from the system.** Account-level compounding (size new
trades off the grown balance) is legitimate and belongs at the *portfolio* layer — see the
follow-up idea below.

> **Follow-up feature idea (not in scope here):** a **portfolio-level compounding backtest** that
> runs all strategies across all 10 slots and compounds the whole ₹1L account over time, so the
> user can see realistic "₹1L → ₹1.5L over 6 months" growth. That is the correct home for
> account compounding; this feature keeps it out of the *per-cell edge yardstick* only.

## Acceptance criteria

1. Re-running any cell twice with unchanged code+config produces **exactly one** row for
   that cell (latest wins) — the table is latest-per-cell by construction.
2. A one-time migration collapses the existing 1363 rows to 323 latest-per-cell rows with
   no data loss of the *latest* value per cell.
3. The leaderboard ranks on latest-per-cell only; `confidence` is based on the number of
   **distinct cells (symbols)** backing a strategy, not raw row count; `totalTrades = 0`
   rows are excluded from all aggregates.
4. Reports carry an `engineVersion` stamp so a future version mismatch is detectable.
5. With the chosen sizing model, no single-cell `roiPercentage` exceeds a sane bound
   (e.g. a slot can't 6× on 13 trades); the previously-absurd cells report realistic ROI.
6. Auto-select no longer appends duplicate rows for a cell it re-evaluates.
7. All changes verified against a DB clone; the `roadmap-v2` running stack is untouched.
