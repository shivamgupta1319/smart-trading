# FEAT-001 — Backtest Report Trust · UI / UX

## Scope of UI impact

This is a **backend correctness feature**. It adds **no new screens, routes, or
components.** It changes the *numbers* shown by two existing surfaces, and the meaning of one
label.

## Affected existing surfaces

| Surface | Today | After |
|---------|-------|-------|
| 🏆 Leaderboard table (Backtesting page, `GET /api/engine/leaderboard`) | Ranks on avg-over-all-rows ROI; inflated. | Ranks on latest-per-cell ROI; lower, honest numbers. Order may change. |
| Monitored Stocks tab (`configs.service.ts` latest-per-cell) | Already correct (dedupes in app). | Unchanged behaviour; the underlying table is now unique-per-cell so its dedup is a no-op. |
| 🔬 Validate / backtest re-run | Each re-run appends a row. | Each re-run **replaces** the cell's row (UPSERT). User sees the same single latest result. |

## UX notes

- **Expect numbers to drop.** After Phase 2/3 the leaderboard and any ROI displays get less
  rosy (top strategies lose ~30–50% of apparent ROI; previously-absurd 600%+ cells fall to a
  realistic range). This is the point of the feature — but it should be surfaced in the
  release/rollout note so it doesn't read as a regression.
- **No loading/empty-state changes.** Response shapes are unchanged; the frontend needs no
  edits. `engineVersion`/`updatedAt` are additive fields the UI may ignore.
- **Optional (not in scope):** a future enhancement could show `engineVersion` / `updatedAt`
  as a small "last computed" caption on the leaderboard so the user knows how fresh a cell is.
  Logged here as a follow-up idea, not built.

## Confidence label

The leaderboard's `riskAdjustedScore` already folds in a `confidence` shrink. Its meaning
changes from "how many times re-run" to "how many distinct symbols back this strategy" — the
*displayed* number is unaffected for strategies with many symbols, but a strategy that looked
confident only because one cell was re-run 20× will now show lower confidence. No UI copy
change is strictly required; if a tooltip exists, update it to "based on number of symbols
tested."
