# FEAT-001 — Backtest Report Trust · Implementation Plan

Three vertical slices, each ≤ 500 changed lines, each independently shippable and verifiable.
All work happens in the **isolated v2 worktree against a DB clone** (per
[v2-environment.md](../../v2-environment.md)); the running `roadmap-v2` stack is never touched
until promotion. Each phase is its own branch + PR off `roadmap-v2`.

---

## Phase 1 — Latest-per-cell report table (the keystone)

**Goal:** the report table holds exactly one row per (stock×strategy×timeframe); every writer
UPSERTs; existing dupes collapsed to latest.

1. Schema: add `engineVersion String? @default("unversioned")`, `updatedAt DateTime @updatedAt`,
   and `@@unique([stockId, strategyName, timeframe])` to `BacktestReport`.
2. Migration SQL: add columns → collapse duplicates to newest-per-cell → add unique constraint.
   Write it by hand (raw SQL), apply to the **clone** first, verify 1363 → 323 rows.
3. `backtest_config.py`: add `ENGINE_VERSION` constant (env-overridable).
4. Extract a single `save_report()` (UPSERT, stamps `ENGINE_VERSION`) into a shared engine
   module; import it from both `backtest.py` and `auto_select.py` (kills the duplication).
5. Tests: assert re-running the same cell twice yields **one** row and the latest metrics;
   assert UPSERT updates `updatedAt`.

**Ordering (must hold):** the migration (which adds the unique constraint) must be applied
**before** the engine's `INSERT … ON CONFLICT` code goes live — `ON CONFLICT (cols)` errors if
no matching unique index exists yet. On the clone, run the migration first, then deploy the
engine change. Verify the `timeframe` column has consistent values (e.g. `"1D"` not `"1d"`)
before relying on the unique key, or casing variants will escape dedup as separate cells.

**Done when:** AC #1, #2, #4, #6. Estimated ~150–250 LOC incl. migration + tests.

---

## Phase 2 — Trustworthy leaderboard

**Goal:** leaderboard ranks on the now-deduped table, excludes empties, honest confidence.

1. `advanced_backtest.py`: add `WHERE "totalTrades" > 0`; document that `reports` now counts
   distinct cells; keep the Calmar score + `confidence = min(1, reports/10)`.
2. Sanity: re-run `/leaderboard` against the clone; diff the ranking vs the pre-dedup ranking
   and record the delta (expect top strategies to drop 30–50% of apparent ROI, per F2).
3. Tests: leaderboard excludes a seeded `totalTrades=0` row; confidence reflects distinct cells.

**Done when:** AC #3. Estimated ~40–80 LOC. Depends on Phase 1.

---

## Phase 3 — Bounded position sizing (decision RESOLVED: Option A)

**Goal:** activate the per-position notional cap so single-cell ROI is realistic.

1. Implement **Option A — fixed-slot, non-compounding, capped at `max_position_value`** (chosen
   by the user 2026-06-12) in `strategies/base.py` `simulate()`: size from a fixed `slot`,
   `qty = max(1, int(min(slot, RISK.max_position_value) / entry))`, and compute ROI/drawdown
   against the fixed slot rather than a running compounded balance.
2. Recompute the offending cells (ADANIPOWER SuperTrend_EMA 1D etc.) and confirm ROI falls to
   a sane range; record before/after.
3. Tests: a known winning sequence can no longer produce ROI above the slot-bounded ceiling;
   `max_position_value` is now exercised (regression test that it's not dead code).
4. **Rollout note:** document that leaderboard/monitored numbers drop after this — intended.

**Done when:** AC #5. Estimated ~60–120 LOC incl. tests. Depends on Phase 1; independent of P2.

---

## Sequencing & gates

```
review-docs (approve scope + pick sizing model A/B)
  → Phase 1 (PR) → verify → Phase 2 (PR) → verify → Phase 3 (PR) → verify-feature
```

- Phase 1 is the prerequisite for 2 and 3.
- Phases 2 and 3 are independent of each other and could be parallel PRs.
- No phase touches strategy *logic* or the live stack; promotion happens after `verify-feature`.

## Rollback

Each phase is a single PR revert. The Phase 1 migration is additive (new columns + a unique
constraint + a row-collapse). Rollback of the constraint is a one-line `DROP CONSTRAINT`; the
collapsed rows are **not** restorable, but they were redundant duplicates of stale-version
results — acceptable and intended. Snapshot the clone's `BacktestReport` to CSV before running
the migration as a belt-and-suspenders backup.
