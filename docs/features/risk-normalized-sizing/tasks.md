# FEAT-005 — Risk-Normalized Sizing · Tasks

Status legend: `TODO` · `IN_PROGRESS` · `DONE`

## Gate
- [ ] `TODO` — Confirm `RISK_PER_TRADE_PCT` default (0.02) with owner
- [ ] `TODO` — Confirm E4 behavior: floor to 1 share vs skip when riskBudget < 1 share
- [ ] `TODO` — `/review-docs` approves scope

## Phase 1 — Per-trade risk cap (API + engine, one PR for parity)
- [ ] `TODO` — `risk.ts`: `RISK_PER_TRADE_PCT` (env, default 0.02) + `riskBudgetFor(cellCapital)`
- [ ] `TODO` — `signals.service.ts:104-108`: add risk-cap bound; recompute capitalUsed/riskAmount from capped qty
- [ ] `TODO` — `backtest_config.py`: `RISK_PER_TRADE_PCT = _f(...)`
- [ ] `TODO` — `strategies/base.py:185-190`: add risk cap alongside notional cap (entry-time stop)
- [ ] `TODO` — Guards: riskPerShare==0 → cap inert; qty≥1 (E1, E4)
- [ ] `TODO` — Parity test both sides: IFCI 78/72.86/1×/0.02 → qty 38; intraday notional-binds case; cap-disabled regression (P3)
- [ ] `TODO` — PR off `roadmap-v2`; `nx build api` + engine `pytest` green

## Phase 2 — Validate the value
- [ ] `TODO` — Full backtest re-run with cap on; record payoff / avg-R / PF / typical size
- [ ] `TODO` — Tune `RISK_PER_TRADE_PCT` if needed (env only); record chosen value in docs

## Phase 3 — Backfill (gated on owner approval)
- [ ] `TODO` — `apps/api/scripts/backfill-position-sizing.ts` (mirror v1), --dry-run default
- [ ] `TODO` — Re-size off `originalStopLoss`; k-scale qty/capitalUsed/riskAmount/pnl/realizedPnl; recompute NET costs
- [ ] `TODO` — Guards: null originalStopLoss → skip+count (E7); oldQty==0 → skip (E8)
- [ ] `TODO` — `--dry-run` review; `pg_dump` + JSON backup; `--apply` on work-pc
- [ ] `TODO` — Re-run `scratchpad/audit.sql`: avg win ≥ avg loss, PF > 1, losers no longer out-risk winners

## Phase 4 — Swing time-stop (follow-up; may become FEAT-006)
- [ ] `TODO` — `TIME_STOP_BARS_BY_BUCKET` in backtest_config.py (SHORT 10 / MID 20 / LONG 40, env)
- [ ] `TODO` — Apply in live_scanner.auto_close_signals AND base.simulate() swing walk (parity)
- [ ] `TODO` — Exclude swing buckets from real-money candidacy until swing R-expectancy positive
- [ ] `TODO` — Parity test: time-stop fires identically live + backtest

## Close-out (`verify-feature`)
- [ ] `TODO` — All ACs traced green
- [ ] `TODO` — Re-run the 2026-07-14 analyst audit; confirm F1 no longer reproduces; update verdicts
