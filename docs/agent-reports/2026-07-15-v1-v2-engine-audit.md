# V1 vs V2 engine audit — why V2 reads worse, and what's actually broken

**Date:** 2026-07-15 · **Branch:** `roadmap-v2` · **Scope:** read-only (no prod writes)
**Trigger:** owner saw `SMA44_Pullback` (1D) at 12% ROI / ₹1,200 on ₹10k over ~5y, then observed
that **V1 shows good results on the same stock × strategy pairs while V2 shows terrible ones**, and
suspected the "hardening" (Monte Carlo, risk caps) made the system worse.

---

## TL;DR

**The owner is ~62% right, and the single worst offender is a change I shipped this morning.**

The V1→V2 swing ROI collapse is **30.28% → 1.38%** (mean over 286 identical 1D cells, −28.90pp).
Attributed by toggling one behaviour at a time on identical data:

| Rung | Mean ROI | Δ | What it is | Verdict |
|---|---:|---:|---|---|
| M0 V1-as-is | 30.28 | — | V1's loop verbatim | fantasy baseline |
| M1 +book open-at-end | 31.41 | **+1.13** | V1 silently *discards* a position still open at series end | V1 quirk (mildly pessimistic) |
| M2 +next-bar entry | 27.89 | **−3.51** | V1 buys at the **signal bar's own close** (lookahead) | **honesty — keep** |
| M3 +intrabar stops | 23.88 | **−4.01** | V1 checks stops on the **close only**; never sees the bar's Low | **honesty — keep** |
| M4 +costs/slippage | 20.85 | **−3.04** | V1 charges **zero** brokerage/STT/stamp/GST/DP/slippage | **honesty — keep** |
| M5 +V2 sizing (risk cap) | 2.87 | **−17.98** | deployed capital **₹95,512 → ₹3,097** (95.5% → 31.0% utilisation) | **NOT honesty — recoverable** |
| M6 +R-target override | 5.58 | **+2.71** | bucket R-target replaces structural target | **helps — keep** |
| M7 +chandelier trail | 4.95 | **−0.63** | ATR trail | mildly harmful |
| M8 +time-stop (**= V2 today**) | 1.38 | **−3.57** | 10/20/40-bar swing time-stop | **HARMFUL — disable** |

**Decomposition of the −28.90pp:**
- **−17.98pp (62%) = the risk cap shrinking deployed capital 31×.** This is *not* a truth
  improvement — it is an allocation choice. **This is the legitimate half of the owner's complaint.**
- **−10.56pp (37%) = genuine honesty** (lookahead, close-only stops, costs). **Not recoverable.**
  Chasing V1's number means restoring lookahead bias.
- **−3.57pp = the swing time-stop shipped 2026-07-15** (commit `697665f`). A regression.
- **+2.71pp = the R-target override**, which *helps*.

**On "Monte Carlo made it worse": no.** MC and walk-forward are auto-select *gates*; they cannot
change a backtest ROI and contributed **0.00pp** here. The owner's instinct that hardening hurt is
right, but the culprit is **sizing**, not MC. (F8 below is a real, separate WF defect.)

---

## Method & validation

Signals come from V2's `STRATEGY_REGISTRY` on every rung. V1/V2 strategy files are byte-identical
except a 200-bar guard (which passes on 5y data) — verified by full-tree diff; only
`episodic_pivot` and `mtf_alignment` have real logic differences, and both are excluded/flagged.
So **signals are constant and the execution model is the only variable.** Same data for all rungs
(V2's `HistoricalData`, 1D from 2021-05-24, ~1,117 bars/stock).

**Both ends of the ladder reconcile — this is the gate that makes the middle meaningful:**

- **Gate B — M8 vs V2's real `run_backtest`: 305/305 exact, d = 0.00.**
- **Gate A — M0 vs V1's real `run_backtest`: 182/190 exact.** All 8 failures are `Episodic_Pivot`
  — the one strategy V2 genuinely broke (see F2). Arrived at independently; confirms F2.

Also measured: **V1's stored rows are 89% reproducible** by V1's own code today (178/201, median
drift 0.00pp), so the head-to-head is not a staleness artifact. V1 nonetheless keeps **1,761 rows
for ~589 cells** across 19 run-dates with no UPSERT and no `engineVersion` — the disease FEAT-001
cured in V2.

---

## Findings, ranked

### F-A (P0, **live now**) — the swing time-stop is a regression. Disable it today.

Shipped this morning (`697665f`, deployed `2026.07.15-f3`). It **hurts 15 of 16 strategies**;
the only "winner" is `Volume_Climax`, which has 8 trades in 5 years.

| | with time-stop | without | effect |
|---|---:|---:|---|
| mean ROI (5.14y) | 1.38% | **4.95%** | **+3.57pp** |
| mean **avgR** | 0.108 | **0.354** | **3.3× better edge** |
| trades | 3,275 | 2,515 | +30% churn |

Worst hit: SuperTrend_EMA −9.68pp, Fibonacci_Golden_Zone −7.47, SMA44_Pullback −7.00,
EMA200_MACD −6.95, EMA_10_50_Cross −6.31. It converts positive-edge strategies into flat/negative
ones (SuperTrend_EMA avgR 0.379 → −0.034; EMA200_MACD 0.370 → −0.003).

**Cause:** a 3R target on a ~2.5 ATR risk needs a ~7.5 ATR move, which cannot occur within 10 bars,
so the stop fires flat on trades that were still working. **Fix: env-only, no redeploy** —
`TIME_STOP_BARS_SHORT_SWING=0`, `TIME_STOP_BARS_MID_SWING=0`, `TIME_STOP_BARS_LONG_POSITIONAL=0`.
Then either re-tune N against the 3R target or drop the feature.

### F-B (P0) — the risk cap, not honesty, is the main reason V2 reads worse

Utilisation **95.5% → 31.0%**; mean deployed **₹3,097** of the ₹10k fund. `base.py:187-200`: the
cap binds for any stop >2%, so deployed ≈ `₹200 / stop%`. Two consequences:

1. **ROI understates return-on-deployed by ~3.2×.** V2's 4.95%/5.14y on the fund ≈ **15.9% on
   capital actually at work**. Still modest, but a different conversation.
2. **Fixed costs now dominate.** The flat **₹14.75 DP charge** per delivery sell is ~0.6–0.8% of a
   ₹3,097 notional vs ~0.06% of V1's ₹95k. Visible as avgR 0.329 → 0.251 across the M5 rung — the
   cap costs ~24% of the edge purely via fixed costs.

**Do not remove the risk cap** (it fixed the real payoff-asymmetry leak, FEAT-005). Fix the *frame*:
report return-on-deployed, and allow concurrent positions so idle capital works.

### F1 (P0) — 20 of 65 active cells can never fire a live signal

`scanner/live_scanner.py:111` `period_map={"1D":"150d"}` ≈ 103 bars, −1 forming ⇒ **~102**.
Strategies guard 200–250 bars and silently return all-zeros. Clean natural experiment:

| Needs >102 bars | Active cells | Live signals **ever** |
|---|---:|---:|
| Golden_Cross, EMA200_MACD, SMA44_Pullback, RSI_Divergence, Volume_Climax | **20** | **0** |
| Control (≤60-bar guards) | 23 | fires normally |

Bitter irony: the guard exists to stop a crash on short walk-forward folds, and it created this.
Fix `period_map["1D"]` → ~`"400d"`, **paired with a prune** (owner decision) so weak cells don't
switch on. Add a test asserting every strategy's bar-guard ≤ the live fetch.

### F2 (P0) — Episodic_Pivot is mathematically dead, and it's a V2 regression

`episodic_pivot.py:67-68` raises `consolidation_high` to `high[i]`, then `:78` tests
`close > consolidation_high` ⇒ **`close > high`, impossible**. 15 reports, **0 trades**.
V1's version trades (Gate A's only failures). Fix: exclude the current bar's high from the
consolidation range before the breakout test.

### F3 (P0) — the honest metric is computed, then thrown away

`base.py:473` computes `avgRMultiple` — its own comment calls it *"the honest edge metric to rank
cells on"* — plus `profitFactor`, `maxDrawdownPct`, `expectancy`. `reports.py:17-31` /
`schema.prisma:54-75` persist **7 of 15**; none of those. **This is the root of the owner's
complaint: ROI is the only column that exists.** Ranked by avgR (time-stop off), the picture
inverts — real edges appear:

| strategy | trades | avgR (no TS) | avgR (V2 today) |
|---|---:|---:|---:|
| Golden_Cross | 49 | **1.373** | 0.646 |
| EMA_10_50_Cross | 205 | **0.707** | 0.367 |
| RSI_Divergence | 57 | **0.541** | 0.068 |
| MACD_Stoch_Confluence | 253 | 0.380 | 0.251 |
| SuperTrend_EMA | 258 | 0.379 | **−0.034** |
| EMA200_MACD | 379 | 0.370 | **−0.003** |
| SMA44_Pullback | 482 | 0.165 | **−0.080** |
| Bollinger_Mean_Reversion | 123 | −0.001 | −0.026 |

### F4 (P1) — ROI is raw cumulative, never annualised, window-dependent

`base.py:467`; `history.py:22-24`: 1D ≈ **5.14y**, 15m/5m ≈ **4.7mo** ⇒ **~13× incomparable**.
`auto_select.py:226` gates on `ret_dd = roi / maxDD ≥ 1.5` — raw cumulative ÷ max DD is
window-length-dependent, so 5-year swing cells clear it far more easily than intraday. A real
Calmar uses annualised return.

### F7 / F8 / F9–F12 (P2–P3)

- **F7** — near-dead strategies: MTF_Alignment 0.0 trades/cell/5y, Episodic_Pivot 0.0,
  Volume_Climax 0.4, BB_Squeeze 0.6. ~50 cells of dead weight.
- **F8** — WF folds starve 200-bar strategies (`advanced_backtest.py:101-110`, no warmup prepend;
  ÷5 ⇒ ~50 usable bars, ÷12 ⇒ 0 signals) ⇒ spurious OOS rejection. Plausibly why only 4/589 passed.
- **F9** — SHORT_SWING trail starts at `entry−6×ATR`, **below** a ~2.5 ATR stop ⇒ near-dead; costs
  −0.63pp overall (and −2.98 on SuperTrend_EMA).
- **F10** `qty = max(1, …)` breaches the risk cap on high-priced stocks. **F11** bare `except` in
  `_hold_bucket` silently disables long-only+time-stop+trail+target-R. **F12**
  `backtest_config.py:57-62` cites an API constant that no longer exists.

### RETRACTED — F6 ("the R-target override destroys structural targets")

**Wrong.** I predicted it would wreck mean-reversion strategies. Measured: it **helps +2.71pp**
overall and **+1.09pp on Bollinger_Mean_Reversion itself** (12 of 19 cells improve; IFCI +12.20,
BSE +9.39). Only Channel_Oscillation is hurt (−2.02). **Keep it.** The hypothesis was plausible and
the data refuted it.

---

## On the owner's original question: SMA44_Pullback

The 12% reading was **correct, and the strategy is weak** — but not for the reason assumed. Across
all 19 stocks it averages **−1.15% (V2 today)**; the 12.94% was `MTARTECH`, the best of 19 = noise.
Trade count is healthy (482, ~25/cell over 5y), so it is **not** starvation. However its **true
avgR is +0.165 with the time-stop off vs −0.080 with it on** — i.e. a thin but real edge that
today's engine converts into a loss.

---

## Recommendations (priority order)

1. **Today, env-only:** set `TIME_STOP_BARS_*=0` on the work-pc engine/scanner. Recovers +3.57pp
   and 3.3× avgR. No redeploy, no code change.
2. **Persist `avgRMultiple` / `profitFactor` / `maxDrawdownPct` / `expectancy`** and surface avgR +
   ROI/yr in the UI (F3). Until then every judgement is made on the wrong number.
3. **Fix the live 102-bar fetch + prune** (F1) — the only real-money defect here.
4. **Fix Episodic_Pivot** (F2); prune the near-dead strategies (F7).
5. **Reframe capital** (F-B): report return-on-deployed; consider concurrency. Keep the risk cap.
6. Then F4 comparability, F8 warmup, F9 trail. Re-run this audit after each.

## Caveats & confidence

- **High confidence** on the ladder: both ends reconcile exactly (305/305 and 182/190), signals are
  provably constant, one variable per rung.
- **High** on F1/F2/F3 (mechanical + DB-proven). **High** on F-A (15/16 strategies, consistent sign).
- **Medium** on magnitudes: single 5.14y window, 19 stocks, no OOS split. Many cells have <10 trades
  — per-cell numbers are noise; per-strategy aggregates are the trustworthy unit.
- **Not covered:** intraday (15m/5m) attribution — V2's C3 exit model is a different code path and
  needs its own ladder. The V1/V2 intraday gap is large (15m_ORB +36.53pp) and unexplained here.
- Reproduce: `scratchpad/attribute.py` + `ladder.py` (read-only; no prod writes).
