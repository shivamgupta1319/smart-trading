# FEAT-005 — Risk-Normalized Sizing · Edge Cases & Testing

## Edge cases

| # | Case | Expected behavior |
|---|------|-------------------|
| E1 | `riskPerShare == 0` (entry == stop, bad signal) | No div-by-zero: `riskCappedQty := notionalQty` (cap inert). Guarded on both sides. |
| E2 | Very tight stop (riskPerShare tiny) | `riskCappedQty` huge → `min()` picks `notionalQty` → notional binds (intraday unchanged). |
| E3 | Very wide stop / cheap stock (swing) | `riskCappedQty` small → cap binds → qty trimmed to ~`riskBudget/riskPerShare`. |
| E4 | `riskBudget/riskPerShare < 1` (fund too small for the stop) | `max(1, …)` floors to **1 share** (matches current behavior). Note: 1 share may exceed `riskBudget` — acceptable, same as today's `max(1, …)`; flag in logs if the owner wants a skip instead. |
| E5 | Blown-up cell (`cellCapital` at `MIN_CELL_CAPITAL` floor) | `riskBudget = MIN_CELL_CAPITAL × pct` — tiny but ≥0; qty floors to 1. |
| E6 | Leverage differs (intraday 5× vs swing 1×) | Cap is on `riskPerShare`, independent of leverage; notional bound still uses leverage. Both bounds coexist. |
| E7 | Backfill: `originalStopLoss` NULL on an old row | Skip re-sizing that row (leave as-is) and count it in the report; do not fall back to trailed `stopLoss` (v1 bug). All current closed rows have non-null `originalStopLoss` (verified). |
| E8 | Backfill: `oldQty == 0` | Guard `k = newQty/oldQty` against div-by-zero; skip + report (no valid rows expected). |
| E9 | Costs on rescaled trade | Recompute NET via `roundTripCost` on new buy/sell values; fixed cost components mean P&L is **not** perfectly linear in k — document the aggregate delta. |

## Parity (the invariant that matters most)

- **P1** — Same (entry, stop, cellCapital, leverage, pct) → identical `quantity` in
  `signals.service.ts` and `strategies/base.py`. Assert the worked example (IFCI 78/72.86/1×/0.02
  → 38) in both suites.
- **P2** — `RISK_PER_TRADE_PCT` default and env name match across `risk.ts` and `backtest_config.py`;
  a grep/test guards against drift (same discipline as the cost-model parity).
- **P3** — Regression: with `RISK_PER_TRADE_PCT` set so the cap never binds (e.g. 1.0), qty equals
  the pre-feature value on both sides (proves the cap is purely additive).

## Test matrix

| Test | Side | Assert |
|------|------|--------|
| tight-stop intraday | TS + Py | notional binds; qty unchanged vs pre-feature |
| wide-stop swing (IFCI example) | TS + Py | risk cap binds; qty = 38 |
| entry == stop | TS + Py | no throw; qty = notionalQty |
| cap disabled (pct = 1.0) | TS + Py | qty == pre-feature qty (P3) |
| backfill dry-run | script | k-distribution printed; restated payoff ≥ 1; no writes |
| backfill null originalStopLoss | script | row skipped + counted |
| full backtest re-run | engine | avg loss ≈ avg win; PF > 1; sizes sane |

## Security / safety

- Backfill mutates recorded history on the live work-pc DB → **mandatory** `pg_dump` + JSON backup
  before `--apply`; `--dry-run` is the default and must be run + reviewed first.
- No secrets read; DB access via the documented read/write path (`ssh work-pc … psql`).
- No change to real-money (Dhan) sizing — that path is independent (per
  [[v1-position-sizing-1lakh-cap]]); this feature is the sim/paper lab only.
