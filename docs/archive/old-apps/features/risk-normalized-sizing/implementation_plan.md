# FEAT-005 — Risk-Normalized Sizing · Implementation Plan

Three vertical slices, each < 500 changed lines, each independently verifiable. Phases 1+2 MUST
land together (or behind the same default-off flag briefly) because live≠backtest sizing breaks
the parity invariant. Work against a DB clone / dry-run first; never mutate the running work-pc
stack until promotion. Each phase = branch + PR off `roadmap-v2`.

---

## Phase 1 — Per-trade risk cap: API (live) + engine (backtest), together

**Goal:** both sizing paths apply `qty = max(1, min(notionalQty, floor(riskBudget/riskPerShare)))`.

1. **API constants** — `apps/api/src/common/risk.ts`: add `RISK_PER_TRADE_PCT` (default 0.02,
   env) + `riskBudgetFor(cellCapital)`; comment "MUST match backtest_config.py".
2. **API sizing** — `apps/api/src/signals/signals.service.ts:104-108`: insert the risk-cap bound
   (riskPerShare already at line 82). Recompute `capitalUsed`/`riskAmount` from the capped qty.
3. **Engine constant** — `apps/engine/backtest_config.py`: add `RISK_PER_TRADE_PCT = _f(...)`.
4. **Engine sizing** — `apps/engine/strategies/base.py:185-190`: add the risk cap alongside the
   existing notional cap (see architecture.md). Use the entry-time planned stop.
5. **Parity test** — assert the worked example (IFCI 78/72.86/1×/2% → qty 38) in BOTH suites, plus
   an intraday case where notional binds. TS: a small unit test; Python: `pytest` in the engine
   container.

**Done when:** AC #1, #2, #3, #4. ~120–200 LOC incl. tests. Deploy = engine restart + api rebuild.

---

## Phase 2 — Validate the `RISK_PER_TRADE_PCT` value on the backtest

**Goal:** confirm 0.02 (or a tuned value) actually restores payoff without over-shrinking size.

1. Re-run a full backtest across the active roster with the cap on; record new payoff, avg-R
   expectancy, PF, and typical position size vs pre-cap.
2. If positions are too small / too large, tune `RISK_PER_TRADE_PCT` via env and re-run — no code
   change. Record the chosen value in this doc + `docs/work-pc-deployment.md`.

**Done when:** a value is chosen with backtest evidence that avg loss ≈ avg win and PF > 1.
~0 LOC (config + notes). Depends on Phase 1.

---

## Phase 3 — Backfill: restate existing work-pc trades

**Goal:** historical `Trade` rows reflect the capped sizing so the equity curve / avg-win/loss the
owner reads are correct.

1. New `apps/api/scripts/backfill-position-sizing.ts` (mirror v1's), jiti, `--dry-run` default,
   `--apply` → JSON backup + requires prior `pg_dump`.
2. Recompute `newQty` under the Phase-1 cap using **`originalStopLoss`**; `k = newQty/oldQty`;
   scale `quantity, capitalUsed, riskAmount, pnl, realizedPnl`; recompute NET costs on rescaled
   buy/sell values (don't linearly scale cost). `pnlPercent` invariant.
3. `--dry-run`: print k-distribution + restated aggregate (avg win/loss, payoff, PF). Backup, then
   `--apply` on work-pc. Re-run `scratchpad/audit.sql` and confirm avg win ≥ avg loss, PF > 1.

**Done when:** AC #5. ~150–250 LOC. Gate on explicit owner approval — rewrites recorded history.
Full `pg_dump` + JSON backup are mandatory rollback artifacts.

---

## Phase 4 (follow-up, may split to its own feature) — Swing per-bucket time-stop

**Goal:** exit SWING/MID/LONG after N bars if neither stop nor target hit (frees hogged cells,
cuts dead-money swings). Audit F3.

1. Add per-bucket `TIME_STOP_BARS_BY_BUCKET` (env-tunable, e.g. SHORT 10d / MID 20d / LONG 40d) to
   `backtest_config.py`; apply in BOTH `apps/engine/scanner/live_scanner.py` `auto_close_signals`
   and `apps/engine/strategies/base.py` `simulate()` swing walk (parity, like the trail).
2. Recommend excluding swing buckets from real-money candidacy until swing R-expectancy is
   positive over a larger sample (currently 11 swing trades, negative).

**Done when:** time-stop fires identically in live + backtest on a worked example. ~100–150 LOC.
Independent of Phases 1–3; can be a separate PR or FEAT-006.

---

## Sequencing & rollback

```
review-docs → Phase 1 (API+engine PR, parity) → verify → Phase 2 (validate value)
            → [Phase 3 backfill, owner-approved] → verify → [Phase 4 time-stop] → verify-feature
```

- Phase 1 is a single revert (both files in one PR to preserve parity).
- Phase 3 is the only heavy rollback (rewrites rows): restore from `pg_dump` / JSON snapshot.
- `RISK_PER_TRADE_PCT` and time-stop bars are all env-tunable — behavior can be adjusted without
  redeploying logic.
