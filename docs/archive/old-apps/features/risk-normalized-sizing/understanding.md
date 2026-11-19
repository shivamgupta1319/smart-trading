# FEAT-005 — Risk-Normalized Sizing (per-trade risk cap) · Understanding

## Origin

From the audit **F1** in
[docs/agent-reports/2026-07-14-avg-loss-gt-avg-win-audit.md](../../agent-reports/2026-07-14-avg-loss-gt-avg-win-audit.md),
prompted by the owner observing that **average profit per trade < average loss per trade**
on the live book. Verified against live data (185 closed trades, 2026-06-09→07-14) and code.

## Problem statement

The live payoff ratio is **0.921** (avg win ₹429.51 < avg loss ₹466.32), yet the per-trade
**edge in R is positive** (intraday median win **+1.27R** vs loss **−1.08R**, R-expectancy
**+1.77R**). The book still loses **rupees** because position sizing is **pure notional** and
never bounds rupee-risk:

```ts
// apps/api/src/signals/signals.service.ts:104-108
const notionalBudget = cellCapital * leverage;                     // ₹10k×5 intraday / ₹10k×1 swing
quantity   = Math.max(1, Math.floor(notionalBudget / dto.entryPrice));
capitalUsed = round2(quantity * dto.entryPrice);
riskAmount  = round2(quantity * riskPerShare);                     // computed, NOT used to size
```

Because `riskAmount = notionalBudget × (riskPerShare / entry)`, the rupees actually at risk
scale with the stop-distance **percentage**. Consequences measured on live data:

- Intraday **losers carried ₹582 avg risk vs ₹486 on winners** — a ~20% heavier ₹-weight on
  losses. A symmetric-R book still bleeds rupees.
- Wide-stop **swings** (1× on a ₹10k fund) risk ₹600–800 each — 3–4× a typical intraday win
  (SHORT_SWING payoff **0.39**, MID **0.27**).

The comment on the code already flags the intent: *"riskAmount is kept for R-multiple analytics,
not sizing."* This feature makes `riskAmount` an actual **cap** on size.

## The fix (decided with owner)

Keep notional sizing but add a **per-trade risk cap** (the v1 pattern
`min(notionalQty, riskCappedQty)`):

```
riskBudget = cellCapital × RISK_PER_TRADE_PCT           # default 0.02 = 2% of the cell fund
riskCappedQty = floor(riskBudget / riskPerShare)        # riskPerShare = |entry − stop|
quantity = max(1, min(floor(notionalBudget / entry), riskCappedQty))
```

- **Tight-stop trades** keep notional (risk cap rarely binds).
- **Wide-stop / swing trades** get trimmed so every trade risks ≤ `riskBudget`.
- Loss magnitudes converge toward **~1R** → avg₹loss ≈ avg₹win, and since R-expectancy is
  positive, payoff climbs above 1 and the book turns net-positive.

## Critical constraint — backtest/live parity

The whole v2 capital model is built on **backtest sizing == live sizing** (see
[[v2-capital-slot-model]]; the memory records that a risk-based cap that lived on only one side
silently skipped trades and corrupted ROI). Therefore the identical cap **must** be applied in
the engine's `simulate()` sizing (`apps/engine/strategies/base.py:185-190`, which today applies
only a notional cap via `RISK.cap_position_value` / `max_position_value`) with a matching
`RISK_PER_TRADE_PCT` constant in `apps/engine/backtest_config.py`. TS⇄Python parity is verified
on a shared worked example (same discipline used for `costs.ts` ⇄ `CostModel`).

## Non-goals / out of scope

- **No change to stops, targets, entries, or exit logic** (partials/trail/reversal/square-off).
  This is sizing only. Winner-capping (audit F2) is a separate, lower-priority question.
- **No change to the per-cell compounding fund model** — `cellCapital` still = ₹10k + cell
  realized P&L; only the qty formula gains a second bound.
- **Swing per-bucket time-stop** (audit F3) is a *related follow-up*, tracked as a later phase /
  its own feature, not required for the sizing cap to ship.
- **Roster hygiene** (audit F5) is handled outside this feature (reversible SQL + auto-select).

## Actors

| Actor | Interest |
|-------|----------|
| `signals.service.ts` sizing block | Computes live `quantity`/`capitalUsed`/`riskAmount` — gains the risk-cap bound. |
| `apps/engine/strategies/base.py` `simulate()` | Backtest sizing — must apply the identical cap or parity breaks. |
| `risk.ts` / `backtest_config.py` | Single-source constants (`RISK_PER_TRADE_PCT`); must match. |
| `backfill-position-sizing.ts` (new) | Re-sizes existing `Trade` rows off `originalStopLoss` so history is restated. |
| Portfolio metrics / analyst | Read avg-win/avg-loss/payoff — the numbers the owner flagged. |

## Key decision — `RISK_PER_TRADE_PCT` value

Default **0.02 (2% of the cell fund = ₹200 on a ₹10k seed)**, env-tunable
(`RISK_PER_TRADE_PCT`). Rationale: current avg risk is ~₹533 (~5.3% of a ₹10k fund) — far too
high for a per-cell testing fund; 2% is a conventional risk-per-trade and equalizes the loss
denominator. Tradeoff: absolute position sizes shrink ~2.6×; for a comparability lab that is the
point (P&L magnitude matters less than a clean, comparable payoff). The value is validated by
re-running the backtest and inspecting the new payoff/expectancy; tune via env, no code change.

## Acceptance criteria

1. Live sizing computes `quantity = max(1, min(floor(notionalBudget/entry), floor(riskBudget/riskPerShare)))`
   with `riskBudget = cellCapital × RISK_PER_TRADE_PCT`. A wide-stop swing is trimmed (risk cap
   binds); a tight-stop intraday is unchanged (notional binds).
2. The engine `simulate()` applies the **identical** cap; a shared worked example
   (entry, stop, fund, leverage) yields the **same qty** in TS and Python.
3. `RISK_PER_TRADE_PCT` is one constant per side, env-overridable, documented as "must match".
4. Guards: `riskPerShare = 0` (entry == stop) does **not** divide by zero — fall back to the
   notional qty; `quantity ≥ 1` always (a fund that can't afford 1 share still trades 1, matching
   current `max(1, …)` behavior — or is explicitly skipped, implementer to confirm).
5. A `--dry-run` backfill reports the k-distribution and the restated aggregate (expected: avg
   loss ≈ avg win, PF > 1); `--apply` only after a `pg_dump` + JSON backup.
6. No stops/targets/exits change; existing tests still pass; `nx build api` + engine `pytest` green.
