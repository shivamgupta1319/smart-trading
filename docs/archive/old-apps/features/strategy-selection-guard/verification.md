# FEAT-003 — Strategy-Level Selection Guard · Verification

All checks run against the **DB clone** with FEAT-001 already applied (deduped/capped
table). The running stack is untouched until promotion.

## AC #1 / #2 — negative-average strategies are ineligible; lucky cells blocked

- **Strategy averages (deduped, reliable):** confirm both Bollinger strategies are negative.
  ```sql
  SELECT "strategyName",
         COUNT(*) AS reliable_cells,
         ROUND(AVG("roiPercentage")::numeric, 2) AS avg_roi
  FROM "BacktestReport"
  WHERE "totalTrades" >= 20
  GROUP BY "strategyName"
  HAVING COUNT(*) >= 3
  ORDER BY avg_roi ASC;
  -- expect BB_Mean_Reversion_Intraday and Bollinger_Mean_Reversion at the bottom, < 0
  ```
- **Lucky-cell block:** run `/auto-select` (dry run) and assert the HDFCBANK 1D
  Bollinger_Mean_Reversion cell (+29%, 18 trades) appears in rejections with
  `gate: "strategy-average"`, not in candidates.

## AC #3 — thresholds configurable

- Set `STRATEGY_AVG_MIN_ROI` to a large negative value via env and confirm previously-blocked
  strategies become eligible again (gate is data/threshold driven, no code edit).

## AC #4 — rejection transparency

- The auto-select response/summary lists a `strategy-average` rejection per blocked cell with
  the offending average value.

## AC #5 — insufficient-data fallback

- Seed a strategy with `< MIN_RELIABLE_CELLS` reliable cells; confirm it follows the decided
  fallback (default: strategy-average gate skipped, logged "insufficient data") rather than
  being silently admitted or blocked.

## AC #6 — no regression to per-cell gates

- A positive-average strategy's qualifying cells still pass and are ranked exactly as before
  the guard (diff the candidate set for a positive-average strategy vs the pre-guard run;
  expect identical).

## Falsification test (from F4)

- Walk-forward HDFCBANK Bollinger_Mean_Reversion 1D on the next out-of-sample window; expect
  ROI to regress toward the −21% strategy mean — confirming the blocked cell was luck, so the
  guard removed risk, not edge.
