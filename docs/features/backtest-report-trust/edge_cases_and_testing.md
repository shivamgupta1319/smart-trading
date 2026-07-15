# FEAT-001 — Backtest Report Trust · Edge Cases & Testing

## Edge cases

### Migration / dedup
- **Tie on `createdAt`** for two rows of the same cell → break ties on `id` (higher = newer).
  The DELETE must be deterministic; verify no cell ends with >1 row after migration.
- **Cells with only `totalTrades = 0` rows** (e.g. Episodic_Pivot, 17 empty rows) → keep one
  row (default, non-destructive) but ensure aggregates exclude it. Confirm such a cell doesn't
  become a unique-constraint violation.
- **Concurrent writes during migration** → run migration with the scanner/auto-select paused,
  or inside a transaction; the new unique constraint makes a concurrent INSERT fail loudly
  rather than silently duplicate (acceptable — it'll retry as UPSERT post-migration).

### UPSERT write path
- **Two simultaneous backtests of the same cell** (auto-select + manual re-run) → the unique
  constraint + `ON CONFLICT DO UPDATE` serialize them; last writer wins, no duplicate row, no
  crash. Assert no `P2002`/IntegrityError escapes.
- **NULL/NaN metric** from a degenerate backtest → UPSERT must not write NaN into NUMERIC
  columns; guard `float('nan')` → reject or store 0 with `totalTrades=0` (mirror existing
  behaviour, don't regress).
- **`engineVersion` unset** (env missing) → defaults to `"unversioned"`; never NULL-crashes.

### Sizing model (Phase 3)
- **Penny stock** (`entry` < ₹10) with a ₹10k slot → `qty` large but capped at
  `max_position_value / entry`; ensure no integer overflow and `qty ≥ 1`.
- **`entry` ≥ slot capital** (price > ₹10k, e.g. some 1D names) → `int(slot/entry) = 0` →
  `max(1, …)` forces qty 1; verify ROI math still sane (one share, bounded).
- **Compounding removed** → confirm `current_capital`-dependent drawdown logic still computes
  `max_dd_pct` correctly against the fixed slot (no div-by-zero when peak == slot).
- **Option B chosen instead** → cap applies inside the compounding numerator; assert ceiling
  still bounds a long winning run.

### Backwards compatibility
- Frontend sends/reads no new fields → assert leaderboard + monitored-stocks JSON keys are
  byte-identical except added optional fields.

## Test matrix

| # | Test | Type | Phase | Asserts |
|---|------|------|-------|---------|
| T1 | Re-run same cell twice (same code/config) | engine pytest | P1 | exactly 1 row; metrics == latest; `updatedAt` advances |
| T2 | Migration on a seeded dup set (3 rows, 1 cell) | SQL/integration | P1 | collapses to 1 (newest); unique constraint holds |
| T3 | Concurrent UPSERT of one cell | engine pytest | P1 | no IntegrityError; 1 row |
| T4 | `engineVersion` stamped on write | engine pytest | P1 | row has expected version |
| T5 | Leaderboard excludes `totalTrades=0` | engine pytest | P2 | empty cell absent from aggregates |
| T6 | Leaderboard ranks on latest-per-cell | engine pytest | P2 | avg ROI matches deduped query, not all-rows |
| T7 | Confidence = distinct-cell based | engine pytest | P2 | a 1-cell-rerun-20× strategy shows low confidence |
| T8 | Sizing cap bounds ROI | engine pytest | P3 | ADANIPOWER SuperTrend_EMA 1D ROI ≤ slot-bounded ceiling (no 639%) |
| T9 | `max_position_value` exercised | engine pytest | P3 | regression: cap is read (not dead code) |
| T10 | Penny-stock & price>slot sizing | engine pytest | P3 | qty ≥ 1, no overflow, sane P&L |

## Existing tests

`apps/engine/test/test_backtest_engine.py` (5 passing) — extend, don't replace. CI (GitHub
Actions: engine pytest + API build + frontend build) must stay green.

## Security / safety

- Migration is **destructive of duplicate rows** → snapshot `BacktestReport` to CSV before
  running; run on the clone first; never on the live `roadmap-v2` DB until promotion.
- No new endpoints, no new external input surface, no auth change. UPSERT uses parameterized
  SQL (no interpolation) — same pattern as the existing `save_report`.
