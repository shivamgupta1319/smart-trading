# FEAT-001 — Backtest Report Trust · Tasks

Status legend: `TODO` · `IN_PROGRESS` · `DONE`

## Gate
- [x] `DONE` — Sizing model chosen: **Option A** (fixed-slot, non-compounding, capped) — user, 2026-06-12.
- [ ] `TODO` — `/review-docs` approves overall scope before implementation begins.

## Phase 1 — Latest-per-cell report table
- [ ] `TODO` — Schema: add `engineVersion`, `updatedAt`, `@@unique([stockId,strategyName,timeframe])`
- [ ] `TODO` — Hand-written migration SQL (add cols → collapse dupes → add constraint)
- [ ] `TODO` — Apply migration to **clone**; verify 1363 → 323 rows, constraint present
- [ ] `TODO` — `ENGINE_VERSION` constant in `backtest_config.py`
- [ ] `TODO` — Shared `save_report()` UPSERT helper; wire into `backtest.py` + `auto_select.py`
- [ ] `TODO` — Tests T1–T4 (idempotent write, migration collapse, concurrent UPSERT, version stamp)
- [ ] `TODO` — PR off `roadmap-v2`; CI green

## Phase 2 — Trustworthy leaderboard
- [ ] `TODO` — `advanced_backtest.py`: exclude `totalTrades=0`; confidence = distinct cells
- [ ] `TODO` — Record leaderboard ranking diff vs pre-dedup baseline
- [ ] `TODO` — Tests T5–T7
- [ ] `TODO` — PR; CI green

## Phase 3 — Bounded position sizing (after gate)
- [ ] `TODO` — Implement chosen sizing model in `strategies/base.py` `simulate()`
- [ ] `TODO` — Recompute F1 exhibit cells; record before/after ROI
- [ ] `TODO` — Tests T8–T10 (ROI bound, cap exercised, penny/expensive-stock sizing)
- [ ] `TODO` — Rollout note: displayed ROI will drop (intended)
- [ ] `TODO` — PR; CI green

## Close-out (`verify-feature`)
- [ ] `TODO` — All ACs traced green; rollout checklist done on live with CSV backup
- [ ] `TODO` — Re-run analyst; confirm F1/F2 no longer reproduce; update report verdicts
