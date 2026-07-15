# FEAT-001 — Backtest Report Trust · Verification & Rollout

## Verification strategy

Because this is a bug fix, verification = **reproduce the broken behaviour, then prove it's
gone** — no walk-forward/Monte-Carlo gate needed.

### Pre-change baseline (capture on the clone before any edit)
- `SELECT count(*), count(DISTINCT (stockId,strategyName,timeframe)) FROM "BacktestReport";`
  → expect **1363 / 323**.
- Save the current `/leaderboard` JSON.
- Save the current ADANIPOWER SuperTrend_EMA 1D rows (the F1 exhibit).
- `SELECT round(avg("roiPercentage"),2) FROM "BacktestReport";` → **26.96**.

### Phase 1 verification
- Run migration on clone → `count(*) == count(DISTINCT cell) == 323`; unique constraint exists.
- Re-run one cell via `POST /api/engine/run-backtest` twice → still 323 rows; the cell's row
  updated in place, `updatedAt` advanced, `engineVersion` stamped.
- Run auto-select on clone → no new duplicate rows appear for re-evaluated cells.
- `pytest apps/engine/test/` green (T1–T4).

### Phase 2 verification
- `/leaderboard` avg ROI per strategy now matches the latest-per-cell query (≈ the 15.00%
  overall figure), not 26.96%. Record the ranking diff vs baseline.
- Seeded `totalTrades=0` cell absent from aggregates (T5–T7 green).

### Phase 3 verification
- Recompute ADANIPOWER SuperTrend_EMA 1D → `roiPercentage` falls from 639% to a realistic,
  slot-bounded figure; record before/after.
- T8–T10 green; `max_position_value` now provably exercised.

## Acceptance-criteria trace

| AC (understanding.md) | Verified by |
|---|---|
| #1 re-run → one row | T1, Phase 1 manual |
| #2 migration collapses 1363→323 | T2, Phase 1 baseline diff |
| #3 leaderboard latest-per-cell + honest confidence + excludes empties | T5–T7, Phase 2 |
| #4 `engineVersion` stamp | T4 |
| #5 ROI bounded by sizing model | T8, Phase 3 before/after |
| #6 auto-select no re-pollution | Phase 1 auto-select run |
| #7 clone-only, live untouched | Rollout checklist below |

## Rollout checklist

1. [ ] All three phases merged to `roadmap-v2` and green in CI.
2. [ ] CSV snapshot of live `BacktestReport` taken before applying the migration to live.
3. [ ] Pause scanner + auto-select (or run in a maintenance window) during the live migration.
4. [ ] Apply migration to the live DB; verify row count collapses and constraint is present.
5. [ ] Rebuild the engine image (sizing/leaderboard changes are Python — engine restart);
       API rebuild only if the Prisma client/schema change requires it.
6. [ ] Smoke: `/leaderboard` returns lower, sane numbers; a fresh re-run UPSERTs in place.
7. [ ] **Communicate the expected drop in displayed ROI** (less rosy = correct).
8. [ ] Re-run the analyst (`Run the analyst`) to confirm F1/F2 no longer reproduce, and
       update the verdicts in
       [2026-06-12-whats-not-working.md](../../agent-reports/2026-06-12-whats-not-working.md).

## Definition of done

All ACs traced green, CI green, live migration applied with a backup, and a follow-up analyst
run confirms the report table is now latest-per-cell and the leaderboard numbers are stable
across consecutive runs.
