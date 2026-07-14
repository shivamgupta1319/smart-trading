# FEAT-005 — Risk-Normalized Sizing · Architecture (source of truth)

Sizing is computed in **two** places that MUST agree (the parity invariant). This doc pins the
exact formula and the touch-points on each side.

## The formula (single source of truth)

```
riskPerShare   = |entry − stop|                       # stop = the PLANNED stop
notionalBudget = cellCapital × leverage               # unchanged
riskBudget     = cellCapital × RISK_PER_TRADE_PCT      # NEW
notionalQty    = floor(notionalBudget / entry)         # unchanged
riskCappedQty  = riskPerShare > 0 ? floor(riskBudget / riskPerShare) : notionalQty   # NEW, guarded
quantity       = max(1, min(notionalQty, riskCappedQty))
```

- `leverage`: INTRADAY 5×, else 1× (unchanged: `leverageFor` / bucket leverage).
- `RISK_PER_TRADE_PCT`: default **0.02**, env `RISK_PER_TRADE_PCT`. **Identical on both sides.**
- The cap is applied to **notional-derived qty**, not to `capitalUsed` — `capitalUsed` and
  `riskAmount` are then recomputed from the final `quantity` exactly as today.

## Live side (TypeScript · NestJS API)

- **Constants** — [apps/api/src/common/risk.ts](../../../apps/api/src/common/risk.ts):
  add `RISK_PER_TRADE_PCT = Number(process.env.RISK_PER_TRADE_PCT || 0.02)` and a helper
  `export const riskBudgetFor = (cellCapital: number) => cellCapital * RISK_PER_TRADE_PCT;`
  Document (comment) that it MUST equal `backtest_config.py`'s value.
- **Sizing** — [apps/api/src/signals/signals.service.ts:104-108](../../../apps/api/src/signals/signals.service.ts#L104-L108):
  insert the `riskBudget` / `riskCappedQty` / `min()` between `notionalBudget` and `capitalUsed`.
  `riskPerShare` is already computed at line 82 (`Math.abs(entryPrice - stopLoss)`).
  `capitalUsed`/`riskAmount` lines stay but now derive from the capped `quantity`.

## Backtest side (Python · engine)

- **Constant** — [apps/engine/backtest_config.py](../../../apps/engine/backtest_config.py):
  add `RISK_PER_TRADE_PCT = _f("RISK_PER_TRADE_PCT", 0.02)` next to `LEVERAGE_*` (line ~42–43);
  optionally a `RiskConfig` field mirroring `cap_position_value` style.
- **Sizing** — [apps/engine/strategies/base.py:185-190](../../../apps/engine/strategies/base.py#L185-L190):
  today
  ```python
  notional = current_capital * leverage
  if RISK.cap_position_value:
      notional = min(notional, RISK.max_position_value)
  qty = max(1, int(notional / entry))
  ```
  becomes (add the risk cap alongside the existing notional cap):
  ```python
  notional = current_capital * leverage
  if RISK.cap_position_value:
      notional = min(notional, RISK.max_position_value)
  notional_qty = int(notional / entry)
  risk_per_share = abs(entry - stop)                       # stop already available in the loop
  risk_budget = current_capital * RISK_PER_TRADE_PCT
  risk_qty = int(risk_budget / risk_per_share) if risk_per_share > 0 else notional_qty
  qty = max(1, min(notional_qty, risk_qty))
  ```
  `stop` is the per-row planned stop the simulate loop already uses for exits — confirm the
  variable name at implementation time and use the **entry-time** stop (not a trailed value), to
  match the live `stopLoss` at signal creation.

## Parity check (mandatory)

A single worked example asserted in BOTH test suites (same inputs → same qty):

| input | value |
|-------|-------|
| cellCapital | 10000 |
| leverage | 1 (swing) |
| entry | 78.00 |
| stop | 72.86 (riskPerShare 5.14) |
| RISK_PER_TRADE_PCT | 0.02 → riskBudget 200 |
| notionalQty | floor(10000/78) = 128 |
| riskCappedQty | floor(200/5.14) = 38 |
| **quantity** | **max(1, min(128, 38)) = 38** |

(This is live open trade #241 IFCI·Fibonacci_Golden_Zone: notional would size 128 sh / ₹658 risk;
the cap trims it to 38 sh / ~₹195 risk.) An intraday example where the notional bound wins should
also be asserted (tight stop → riskCappedQty ≥ notionalQty → notional binds).

## Backfill (data restatement)

- **Script** — `apps/api/scripts/backfill-position-sizing.ts` (new), jiti-runnable, `--dry-run`
  default, `--apply` writes a JSON backup and requires a prior `pg_dump`. Mirror v1's script at
  `/home/shivam/workspace/smart-trading/apps/api/scripts/backfill-position-sizing.ts`.
- Per `Trade` (open + closed): `newQty = capped qty using originalStopLoss` (the PLANNED stop —
  never the trailed `stopLoss`); `k = newQty / oldQty`; scale `quantity, capitalUsed, riskAmount,
  pnl, realizedPnl` by `k`. `pnlPercent` is scale-invariant (leave as-is).
- **Costs:** P&L is linear in qty but round-trip costs have fixed components (DP charge), so
  recompute NET costs on the rescaled buy/sell values via
  [apps/api/src/common/costs.ts](../../../apps/api/src/common/costs.ts) `roundTripCost` rather than
  linearly scaling the stored `pnl`. Document the small delta vs pure-linear.
- Target DB: work-pc (`ssh work-pc … psql`), port 5471. `pg_dump` backup first.

## Data model

No schema change. `Trade.quantity/capitalUsed/riskAmount/pnl/realizedPnl` already exist
(all `Decimal`, `quantity Int`). `originalStopLoss` (`Decimal?`) is the planned-stop source for
the backfill.
