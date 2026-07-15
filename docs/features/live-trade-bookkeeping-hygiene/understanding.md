# FEAT-002 — Live Trade Bookkeeping Hygiene · Understanding

## Origin

From analyst finding **F5** in both reports
([2026-06-12](../../agent-reports/2026-06-12-whats-not-working.md) and
[2026-06-16](../../agent-reports/2026-06-16-whats-not-working.md)), firmed up on the
40-closed-trade sample. Verified against code 2026-06-16 — both defects are real and
unfixed.

## Problem statement

The live metrics the user reads (win-rate, net P&L) are computed from fields that are
quietly wrong:

1. **Scratches are booked as WIN — no BREAKEVEN band.** Outcome is decided by sign
   alone:
   ```ts
   const outcome = totalPnl > 0 ? "WIN" : totalPnl < 0 ? "LOSS" : "BREAKEVEN";
   ```
   ([signals.service.ts:286](../../../apps/api/src/signals/signals.service.ts#L286);
   mirrored in [trades.service.ts:311](../../../apps/api/src/trades/trades.service.ts#L311)).
   `BREAKEVEN` is therefore reachable only on an *exact* ₹0 close. Real trades that
   close at +₹1.88 / +0.031R (id 40), +₹3.20 / +0.038R (id 50), +₹4.08 / +0.044R
   (id 22) are booked **WIN**; a −₹10 / −0.114R scratch (id 51) is booked **LOSS**.
   These inflate/distort the headline win-rate (reported 52.5%).

2. **`realizedPnl` drops the final leg.** On close, the final P&L is computed and
   stored only in `pnl`:
   ```ts
   const finalLotPnl = pnlPerShare * trade.remainingQty;
   const totalPnl = trade.realizedPnl + finalLotPnl;   // ← correct total
   // ...
   data: { pnl: round2(totalPnl), /* realizedPnl NOT updated */ }
   ```
   ([signals.service.ts:280-304](../../../apps/api/src/signals/signals.service.ts#L280-L304)).
   `realizedPnl` only ever accumulates *partial* exits
   ([signals.service.ts:250](../../../apps/api/src/signals/signals.service.ts#L250)),
   so for the 27 of 40 trades that closed in `INITIAL` state (no partial fired) it
   stays **0** even on a large win/loss. Result: `SUM(realizedPnl) = +₹737.43` vs
   `SUM(pnl) = −₹75.54` — an **₹813 reporting gap** on the same 40 trades.

## Non-goals / out of scope

- **No strategy/entry logic changes.** This is outcome-classification + accounting only.
- **No backtest changes.** Those belong to [FEAT-001](../backtest-report-trust/understanding.md).
- **No new BREAKEVEN trading behavior.** A reclassified scratch is still a real, closed
  trade with its real `pnl`; we only change the *label* and the win-rate denominator math.

## Actors

| Actor | Interest |
|-------|----------|
| `signals.service.ts` close path | Sets `outcome`, `pnl`, `realizedPnl` on the FULL-close leg. |
| `trades.service.ts` | Second copy of the same `outcome` formula — must stay in sync. |
| Win-rate / P&L reporting (UI, analyst) | Consumes `outcome` and `realizedPnl`; both currently mislead. |
| Analyst agent | Asserts `SUM(realizedPnl)=SUM(pnl)` and a BREAKEVEN-band win-rate as health checks. |

## Key decision — BREAKEVEN band threshold

A trade is `BREAKEVEN` when `|pnl / riskRef| < BREAKEVEN_R` (default **0.1R**), else
`WIN`/`LOSS` by sign. `riskRef` resolves in order: **`riskAmount`** (confirmed present on
`Trade`, `Decimal @default(0)` = `(entry − SL) × quantity`) → **`capitalUsed`** if
`riskAmount` is 0/null → an absolute ₹ floor (e.g. ₹5) as a last resort. The 0-default on
`riskAmount` means the **div-by-zero fallback is mandatory, not optional**. The band value
is configurable (env or constant) so it can be tuned without a code change.

## Key decision — win-rate denominator (RESOLVED)

The live code computes win-rate as `wins / fundedClosed.length`
([trades.service.ts:59-61](../../../apps/api/src/trades/trades.service.ts#L59-L61)) — i.e.
**WIN ÷ all funded closed**, putting LOSS *and* the soon-to-exist BREAKEVEN in the
denominator. **Decision:** compute win-rate as `WIN / (WIN + LOSS)`, **excluding BREAKEVEN
from both** numerator and denominator. This is a deliberate behavior change. There are
three consumers to update consistently: the portfolio win-rate
([trades.service.ts:59-61](../../../apps/api/src/trades/trades.service.ts#L59-L61)), the
per-strategy group win-rate
([trades.service.ts:94-126](../../../apps/api/src/trades/trades.service.ts#L94-L126)), and
the Telegram outcome emoji
([telegram.service.ts:116](../../../apps/api/src/telegram/telegram.service.ts#L116), display
only — no math, but should render `BREAKEVEN` as ➖, which it already does).

## Decision — realizedPnl

Pick one (implementer to confirm with the user during review):

- **(A — recommended) Make `realizedPnl` whole.** On full close, set
  `realizedPnl = round2(totalPnl)` alongside `pnl`. Then `realizedPnl` = sum of every
  leg and reconciles to `pnl` by construction. Lowest-surprise; keeps the field meaningful.
- **(B) Deprecate `realizedPnl` for reporting.** Leave it as partials-only but stop any
  consumer from summing it as account P&L; document `pnl` as the single source of truth.

Default to (A) unless a consumer specifically needs partials-only realized P&L.

> **Scope note (verified):** account equity already sums `pnl`, not the broken column
> (`realizedPnl = closedFunded.reduce((s,t) => s + toNum(t.pnl), 0)` at
> [signals.service.ts:87](../../../apps/api/src/signals/signals.service.ts#L87)). So this
> fix makes the **column** self-consistent (so `SUM(realizedPnl)=SUM(pnl)` holds and the
> analyst assertion passes) — it does **not** change displayed equity. Lower risk than it
> first appears.

## Acceptance criteria

1. A trade closing within ±0.1R of breakeven is labelled `BREAKEVEN`, not `WIN`/`LOSS`;
   ids 40/50/22 reclassify from WIN→BREAKEVEN and id 51 from LOSS→BREAKEVEN on replay.
   A trade with `riskAmount = 0` does not crash — it uses the `capitalUsed`/floor fallback.
2. Win-rate is computed as `WIN / (WIN + LOSS)` excluding `BREAKEVEN` from both numerator
   and denominator, at **all three** consumers (trades.service.ts:59-61, :94-126; telegram
   emoji display-only). The reported number changes from 52.5% on the current 40-trade
   sample (recorded before/after).
3. The two `outcome` formulas (`signals.service.ts`, `trades.service.ts`) are identical
   and ideally share one helper so they cannot drift.
4. With decision A: `SUM(realizedPnl) === SUM(pnl)` over all CLOSED trades (currently
   off by ₹813). With decision B: no consumer sums `realizedPnl` as account P&L.
5. The BREAKEVEN band is configurable without code edits.
6. Existing closed trades are not silently rewritten unless a one-time, reviewed
   backfill migration is explicitly run (see implementation_plan.md).
