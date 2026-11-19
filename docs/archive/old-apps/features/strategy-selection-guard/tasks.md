# FEAT-003 — Strategy-Level Selection Guard · Tasks

Status legend: `TODO` · `IN_PROGRESS` · `DONE` · `BLOCKED`

## Gate
- [ ] `BLOCKED` — Depends on FEAT-001 (deduped/capped latest-per-cell table) landing first
- [ ] `TODO` — Confirm insufficient-data fallback rule (default: skip gate, log) with user
- [ ] `TODO` — `/review-docs` approves scope

## Phase 1 — Strategy-average eligibility gate
- [ ] `TODO` — Config: `STRATEGY_AVG_MIN_ROI`, `MIN_RELIABLE_TRADES`, `MIN_RELIABLE_CELLS` (env)
- [ ] `TODO` — Compute per-strategy avg ROI from deduped table (reliable samples only)
- [ ] `TODO` — Build `eligible` map + insufficient-data fallback
- [ ] `TODO` — Add `strategy-average` gate before per-cell loop
- [ ] `TODO` — Surface decision in per-strategy run summary
- [ ] `TODO` — Tests: neg-avg strategy → 0 candidates; pos-avg unaffected; fallback correct
- [ ] `TODO` — PR off `roadmap-v2`; CI green

## Close-out (`verify-feature`)
- [ ] `TODO` — All ACs traced green
- [ ] `TODO` — Falsification: walk-forward HDFCBANK Bollinger 1D regresses to strategy mean
- [ ] `TODO` — Re-run analyst; confirm no monitored cell belongs to a negative-avg strategy
