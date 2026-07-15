# FEAT-004 — Live-vs-Backtest Reconciliation · Tasks

Status legend: `TODO` · `IN_PROGRESS` · `DONE` · `BLOCKED`

## Gate
- [ ] `BLOCKED` — Depends on **FEAT-001** (`DONE`) — trustworthy backtest expectancy
- [ ] `BLOCKED` — Depends on **FEAT-002** (`DONE`) — trustworthy live R / win-rate
- [ ] `TODO` — At unblock: `/review-docs` to firm up the plan against FEAT-001's real output

## Phase 1 — Reconciliation report (read-only)
- [ ] `TODO` — Query live-traded cells + corrected realized R (FEAT-002)
- [ ] `TODO` — Recompute capped/deduped backtest expectancy + MC band per cell (FEAT-001)
- [ ] `TODO` — Label inside/outside band; emit corrected-top-set vs monitored-93 diff
- [ ] `TODO` — Flag the 25/93 monitored cells backed by only 1–5 backtest trades
- [ ] `TODO` — Write report to `docs/agent-reports/`; PR

## Phase 2 — Trust signal into auto-select (optional, gated on approval)
- [ ] `TODO` — Persist per-cell trust delta
- [ ] `TODO` — Auto-select demotion term behind a config flag
- [ ] `TODO` — Tests + selected-set diff with/without the signal
- [ ] `TODO` — PR

## Close-out (`verify-feature`)
- [ ] `TODO` — All ACs traced green
- [ ] `TODO` — Re-run analyst; confirm the live-vs-backtest gap is explained (regime vs overstated) per cell
