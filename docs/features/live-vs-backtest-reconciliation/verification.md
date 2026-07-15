# FEAT-004 — Live-vs-Backtest Reconciliation · Verification

> Verification is meaningful only **after unblock** (FEAT-001 + FEAT-002 `DONE`). Running
> these checks against today's inflated backtest table / mislabeled live trades would
> measure the artifacts, not the gap. Provisional — refine with the Phase 1 plan.

## AC #1 — per-cell join with band label

- The report contains, for every live-traded cell: live realized R (FEAT-002 corrected),
  capped/deduped backtest expectancy (FEAT-001), Monte-Carlo p5/probability-of-profit band,
  and an `inside_band` / `outside_band` label. Re-running the report on the same data
  reproduces identical labels (deterministic).

## AC #2 — known offenders re-evaluated

- ETERNAL Fibonacci_Golden_Zone, BSE/ATGL 15m_ORB, APOLLO EMA_RSI appear with their
  **corrected** expectancy. Confirm the corrected figure is materially below the raw figure
  auto-select originally used (the F1/F3 hypothesis) and is flagged when the live result
  falls outside the band.

## AC #3 — consumable trust signal (Phase 2)

- The trust delta is persisted per cell and, with the config flag on, a dry-run auto-select
  demotes out-of-band cells. Diff the selected set flag-on vs flag-off and confirm only
  flagged cells move.

## AC #4 — broken-rule vs regime, per cell

- Each cell carries an explicit per-cell verdict (overstated-backtest vs regime/variance),
  not a single global claim. Spot-check: a cell whose live result sits **inside** the
  corrected band is labelled regime/variance (keep); one **outside** is labelled
  overstated (demote).

## Sanity / thin-sample surfacing

- The report lists the **25 of 93** monitored cells backed by only 1–5 backtest trades
  (06-16 report) as explicit thin-selection risk, with their corrected expectancy and band.
