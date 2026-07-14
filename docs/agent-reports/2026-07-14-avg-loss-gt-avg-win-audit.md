# Analyst Report — average profit < average loss (payoff ratio audit)

- **Date:** 2026-07-14
- **Lens:** the owner observed that avg profit per trade is smaller than avg loss per trade
  ("bad for the platform"). Find *why*, distinguish artifact from dead edge, and separate
  historical damage from what's still bleeding.
- **Data window:** live trades 2026-06-09 → 2026-07-14 (~35 days)
- **Sample:** 185 closed trades, 3 open, 69 active cells / 19 strategies. Live DB read-only
  (`ssh work-pc` → `docker exec smart-trading-v2-db psql -U trader -d smart_trading`).

> **Process note:** human-directed audit; findings carry a VERDICT box for review. Acting on
> accepted findings is planned as separate phases (roster hygiene, sizing fix, backfill, swing
> time-stop) — see `~/.claude/plans/please-read-the-memory-cozy-wilkes.md`.

## TL;DR (≤5 bullets)

- **Symptom is real:** 185 closed, net **−₹2,061.64**, win **50.8%**, avg win **₹429.51** <
  avg loss **₹466.32**, **payoff 0.921**, PF 0.951.
- **But the edge isn't dead — the sizing is.** Per-trade *R* is positive (intraday median win
  **+1.27R** vs loss **−1.08R**, R-expectancy **+1.77R**); the book still loses **rupees** because
  losing trades carried **more ₹-risk** (intraday ₹582 avg vs ₹486 on winners). Notional sizing
  never uses `riskAmount`, so ₹-risk is unequal across trades → avg₹loss > avg₹win is an artifact.
- **Winners are also structurally capped** by the 35/35 partial-exit design (win realizes <1.5R,
  reversal-to-breakeven nets ~+0.35R) while losers book the full −1R.
- **Swing book is the worst per-trade:** payoff **0.39** (SHORT) / **0.27** (MID), negative even in
  R; each wide-stop swing loses ₹600–800; swings hog cells for weeks (no time-stop).
- **Most damage is historical & already curated out.** Week of **2026-07-06 = −₹4,708** ≈ the whole
  net loss; **post-2026-07-13 tape is +₹1,587 / payoff 1.20 / 62% win**. The biggest losers are
  already deactivated — but the roster is still the stale 06-09 seed and prunes aren't sticky.

## Data health first

- Closed live trades: **185** — enough for strategy-level and book-level reads; thin per single
  cell and very thin for swings (**11 swing trades total**, do not over-read).
- Bookkeeping is **clean** this run: `SUM(realizedPnl) == SUM(pnl)` (both −2,061.64), 16 BREAKEVEN
  rows (the 0.1R scratch band works), 0 closed trades with null `originalStopLoss`. The FEAT-002
  defects from the 2026-07-11 review are resolved.
- Caveats: 35-day window, single regime; loss is concentrated in one week (2026-07-06); post-fix
  sample (13 trades) is too small to call the fixes proven, only encouraging.

---

## Findings

### F1 — Notional sizing decouples ₹-risk from R (root cause of payoff<1)

- **Observation:** live sizing is pure notional — `qty = floor(cellCapital × leverage / entry)`;
  `riskAmount` is computed but explicitly *not* used to size. So per-trade rupee risk varies with
  stop-distance%. Intraday winners carried **avg ₹486 risk** vs losers **avg ₹582** — losers are
  ~20% "bigger" in rupees. Per-trade R is positive (median win **+1.27R**, median loss **−1.08R**;
  R-expectancy **+1.77R** intraday) yet intraday still nets **−₹349** in rupees. The book wins small
  ₹ (tight-stop, high-R trades) and loses big ₹ (wider-stop trades).
- **Evidence:** `apps/api/src/common/risk.ts` (per-cell notional model, no risk sizing);
  `apps/api/src/signals/signals.service.ts:104-108` (`notionalBudget = cellCapital × leverage`,
  `qty = floor(notionalBudget/entry)`, comment: "riskAmount is kept for R-multiple analytics, not
  sizing"). Aggregate by hold-duration and win/loss risk from the audit SQL (below).
- **Sample size:** 174 intraday closed — **confidence: high** (mechanism + reproduced in aggregates).
- **Broken rule or regime?** Broken rule — a sizing/metric decision, regime-independent.
- **Hypothesis:** bound each trade to equal ₹-risk with a per-trade risk cap
  `qty = min(notionalQty, floor(riskBudget/stopDist))`, `riskBudget = cellCapital × RISK_PER_TRADE_PCT`
  (v1 pattern). Equalizes the loss denominator → avg₹loss ≈ 1R, wins become multiples → payoff > 1
  (since R-expectancy is already positive). Must be mirrored in the backtest for parity.
- **Suggested validation:** re-run the full backtest with the cap; confirm new payoff/expectancy and
  that losers no longer out-risk winners; dry-run backfill and re-query the aggregate.

> **VERDICT (human review):** ☑ Accept — _fix planned as Phase 2 (per-trade risk cap) + Phase 3
> (re-size existing data)._

### F2 — Winners capped by the partial-exit design

- **Observation:** intraday exits scale out 35% @ 0.5×target and 35% @ 0.75×target, move the runner
  to breakeven and trail it, so a "win" realizes well under its nominal target (best-case ≈1.475R,
  a reversal-to-breakeven after phase-2 nets ~+0.35R), while a loss stopped before phase-2 books the
  full position at **−1R**. Payoff<1 is partly baked in even before F1.
- **Evidence:** `apps/engine/strategies/base.py` `_intraday_exit`, `apps/engine/scanner/live_scanner.py`
  `auto_close_signals` (PHASE2 0.50 / PHASE3 0.75 / REVERSAL 0.80, 0.35 partials);
  `apps/engine/intraday_exits.py` thresholds.
- **Sample size:** all intraday — **confidence: medium-high** (mechanism clear; the net effect is
  entangled with F1's ₹-weighting).
- **Broken rule or regime?** Design tradeoff (protects against reversals, costs upside). Not a bug.
- **Hypothesis:** payoff can lift by letting a larger runner reach the full target (smaller/earlier
  partials, or a wider phase-3), but this trades win-rate for payoff — validate before changing.
- **Suggested validation:** parameter sweep on partial fractions/triggers in backtest, holding the
  risk cap fixed; compare net and payoff.

> **VERDICT (human review):** ☐ Accept ☐ Reject ☐ Needs more data — _lower priority than F1; revisit
> after the risk cap lands._

### F3 — Swing book is the worst per-trade (wide stop × notional, no time-stop)

- **Observation:** SHORT_SWING payoff **0.39** (avg win ₹251.87 vs loss ₹648.18), MID **0.27**
  (₹153 vs ₹573); both negative in R (SHORT −0.33R, MID −0.12R). The swing loss book is dominated by
  DMA20_Pullback: OLAELEC #172 −₹806 (232 sh), IFCI #128 −₹647 / #143 −₹605, MTARTECH #144 −₹534.
  Wide stops × 1× on a ₹10k fund = ₹600–800 risked per trade. Swings also sit open for weeks
  (INFY·Channel_Oscillation #116 open since 2026-06-24 = 3 weeks) — there is **no swing time-stop**.
- **Evidence:** by-hold-duration and swing-detail queries below; `TARGET_R_BY_BUCKET` +
  chandelier-trail exits in `backtest_config.py` / `base.py` / `live_scanner.py`.
- **Sample size:** **11 swing trades total** — **confidence: low on magnitude, high on direction**
  (too few to trust the exact numbers, but the wide-stop×notional mechanism is structural).
- **Broken rule or regime?** Mostly the F1 sizing mechanism amplified by wide swing stops; plus a
  missing time-stop.
- **Hypothesis:** the Phase-2 risk cap trims swing ₹-risk to parity; add a per-bucket time-stop
  (SHORT 10d / MID 20d / LONG 40d) to free hogged cells; keep swings lab-only (not real-money
  candidates) until they show positive R over a larger sample.
- **Suggested validation:** backtest the time-stop per bucket; re-check swing payoff after the cap.

> **VERDICT (human review):** ☑ Accept — _planned as Phase 4 (time-stop) + covered by Phase 2 cap._

### F4 — The realized loss is largely historical and already deactivated

- **Observation:** the net loss is concentrated in one week — **2026-07-06 = −₹4,708** (68 trades);
  every other week is ~flat/green (06-15 +82, 06-22 +1,610, 06-29 +1,283). **Post-2026-07-13**
  (after the C1–C3 net-cost + intraday-parity fixes deployed): **+₹1,587 / payoff 1.20 / 62% win**
  over 13 trades. The worst cells — BSE·15m_ORB −₹3,188, GROWW·RVOL_ORB −₹2,345, APOLLO·EMA_RSI
  −₹2,215, IFCI·DMA20_Pullback −₹1,252 — are **already removed** from ActiveConfiguration. Among the
  15 currently-active cells that have traded, winners **+₹8,089** outweigh losers **−₹2,611**.
- **Evidence:** weekly-trend, before/after-0713, and active-cell-join queries below.
- **Sample size:** 13 post-fix trades — **confidence: low** (encouraging, not proven).
- **Broken rule or regime?** Neither — this is the improvement trajectory; the headline −₹2k is a
  backward-looking sum dominated by since-fixed conditions.
- **Hypothesis:** the current active roster is roughly breakeven-to-positive; the reported deficit is
  legacy. Re-sizing history (Phase 3) will restate the equity curve to the corrected model.
- **Suggested validation:** re-run the audit SQL after each phase; watch the post-fix payoff trend.

> **VERDICT (human review):** ☑ Accept — _informational; drives Phase 3 (restate history)._

### F5 — Roster is stale and manual prunes aren't sticky

- **Observation:** 69 active cells across 19 strategies but only **15 have ever traded** (54
  untested, mostly daily swings). The improved quality-gated auto-select (built 2026-07-13) was never
  actually run — the roster is still the 2026-06-09 seed minus a few manual `DELETE`s. The 3 active
  `15m_ORB` cells kept on 07-13 as +₹892 (ATGL/VEDL/MTARTECH) have since bled to ~**−₹2,038**
  combined. Auto-select re-promotes pruned losers unless deny-listed — the open **Fibonacci_Golden_Zone
  trade #241** (opened 2026-07-13, on a pruned strategy) is the live artifact.
- **Evidence:** `ActiveConfiguration` join to `Trade` P&L (below); `infra/scripts/hygiene-prune-losers.sql`
  notes ("a one-off DELETE is NOT sticky — the real fix is the auto-select selection guard").
- **Sample size:** 69 cells — **confidence: high.**
- **Broken rule or regime?** Broken process — roster never re-selected; deny-list not enforced on run.
- **Hypothesis:** prune the now-losing active cells AND run the real quality-gated auto-select with
  the chronic losers deny-listed, so the roster becomes the quality picks and stays pruned.
- **Suggested validation:** after the auto-select run, re-query active cells joined to P&L; re-run
  auto-select and confirm the deny-listed losers do not reappear.

> **VERDICT (human review):** ☑ Accept — _planned as Phase 1 (roster hygiene)._

---

## What I could NOT conclude

- Whether the **post-2026-07-13 improvement is real or noise** — 13 trades is far too few. Only time
  (or backtest validation) settles it.
- The **exact payoff lift** from the risk cap — needs the dry-run backfill + backtest re-run; the
  direction is certain (equal ₹-risk on losers), the magnitude is not.
- Whether **F2 (partial capping)** is net-harmful — it protects against reversals; can't say it's
  wrong without a sweep. Left as lower priority.
- Swing magnitudes (F3) rest on 11 trades — directionally sound, numerically unreliable.

## Suggested next report

- After Phase 2+3 land: re-run this exact audit and report the restated book — confirm avg win ≥ avg
  loss, PF > 1, and that losers no longer carry more ₹-risk than winners. Then a partial-exit
  parameter sweep (F2) once the sizing floor is stable.

---

## Appendix — SQL used (all read-only)

Run via `ssh work-pc 'docker exec -i smart-trading-v2-db psql -U trader -d smart_trading' < file.sql`.
Scripts saved in this session's scratchpad (`audit.sql` … `audit5.sql`). Key aggregates:

- **Overall / by hold-duration / bookkeeping:** `audit.sql`
- **R-multiple signature, by-strategy, worst cells, swing detail:** `audit2.sql`
- **Active-config join, before/after 0713, weekly trend, intraday R medians & win/loss ₹-risk:**
  `audit3.sql`
- **ActiveConfiguration contents:** `audit4.sql`
- **Active cells joined to historical P&L + summary:** `audit5.sql`
