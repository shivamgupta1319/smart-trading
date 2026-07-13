# Analyst Report — trust & correctness audit (docs + live data + code)

- **Date:** 2026-07-13
- **Lens:** what makes the v2 system untrustworthy or incorrect, and what to fix
- **Data window:** live trades 2026-06-09 → 2026-07-13 (~34 days); full code + docs review
- **Sample:** 174 closed live trades, 7 open, 68→ active cells; all of `docs/**` and the
  Python engine + NestJS API + React frontend

> **Note on process:** unlike the pure analyst loop (agent proposes → human gates → act),
> this run was **human-directed and acted upon in the same session**. Findings below carry
> their verdict (all Accepted by the owner) plus **what was actually changed**. Kept in this
> folder because it's the same evidence-first shape and belongs with the report history.

## TL;DR (≤5 bullets)

- **The backtest that drives auto-select was ranking on inflated ROI** — uncapped compounding ×
  leverage made a ₹10k slot backtest to +₹187k / +639%, so the most overfit cells ranked highest
  and the drawdown/return gates never bit. **Fixed** (notional cap + rank by NET avg-R).
- **Auto-select re-promoted manually-pruned losers** every run (no denylist). Fibonacci_Golden_Zone
  and Volume_Profile_POC, cut 2026-07-11, were back in ActiveConfiguration. **Fixed** (persistent denylist).
- **Live P&L ledger is honest** — stops honored exactly (0 trades breach 1.2× risk; all losers cap at
  −1.00R), partial-exit accounting doesn't double-count, long/short signs correct.
- **But the backtest ≠ live** in exit modeling (dead swing trail, different intraday exits, gross-vs-net
  P&L) — so backtest metrics can't be trusted to predict live for intraday. **Not yet fixed (Phase C).**
- **Performance:** +₹5,193 net / PF 1.14 / 52.9% WR over 34d; all profit is ~4 intraday momentum
  strategies; the swing book is a −₹1,487 drag; edge is thin (+₹30/trade, R inflated by ~1% stops).

## Data health first

- Closed live trades: **174** — enough for strategy-level reads, thin for single-cell reads.
- Open positions: **7** (₹70.6k margin / ₹235.9k notional at 5× intraday).
- Backtest reports table: append-only, mixes engine versions — trust freshly-recomputed metrics, not
  the stored leaderboard aggregate.
- Caveats: 34-day window, single regime; `HistoricalData` last bar = Fri 2026-07-10 (weekend gap).

---

## Findings

### F1 — Backtest ROI is inflated by uncapped compounding → auto-select ranks overfit cells

- **Observation:** `qty = int(current_capital × leverage / entry)` sizes off *compounding* equity with
  the configured `max_position_value` cap left as dead code. In-image test: a compounding intraday cell
  backtested to **ROI 2458%**; with the cap it drops to **358%** (6.9×) while its edge (avgR 1.58) is
  unchanged. Live artifact: ADANIPOWER EMA_RSI 1D = +187% / +₹187k on a ₹10k slot.
- **Evidence:** `strategies/base.py:171-172`, `backtest_config.py:66-69` (cap unused), `_score` ranked
  on `roi/dd` (`auto_select.py:124-128`).
- **Sample size:** whole backtest surface — **confidence: high** (mechanism + reproduced).
- **Broken rule or regime?** Broken rule (sizing/metric bug).
- **Hypothesis:** cap notional at `max_position_value` and rank by NET avg-R (compounding/horizon-
  independent) → gates bite, ranking reflects real edge.
- **VERDICT:** ☑ Accept — _**Done.** `BT_CAP_POSITION_VALUE` (default on) caps notional; `avgRMultiple`
  added to metrics; `_score` and the sort now rank by NET avg-R. Verified in the engine image._

### F2 — Auto-select gates were toothless / lenient

- **Observation:** with inflated ROI, the 40% DD ceiling and return/DD≥1.5 never bit; PF≥1.05 barely
  beats breakeven after costs; walk-forward needed only 2-of-5 profitable folds with the consistency
  flag off. Post-fix full dry-run: **6 quality picks** across 31 strategies (all DD 6–24%, avgR>0);
  rejections dominated by de-inflated `roi` (91) and `trades` (70).
- **Evidence:** `auto_select.py:41-57` (thresholds), `:204-238` (gate chain).
- **Sample size:** 31 strategies × 19 stocks — **confidence: high.**
- **VERDICT:** ☑ Accept — _**Done.** MAX_DD 40→25%, PF 1.05→1.3, OOS folds 40→60%,
  `WF_REQUIRE_CONSISTENT` on, added `MIN_AVG_R` gate. All env-tunable._

### F3 — No denylist: pruned losers get re-promoted

- **Observation:** append mode only skips *currently-active* cells, so a manually-removed loser is
  "new" again next run. Fibonacci_Golden_Zone (×3) and Volume_Profile_POC (×2), cut 2026-07-11, were
  back in ActiveConfiguration on 2026-07-13.
- **Evidence:** `auto_select.py:288-291`; live `ActiveConfiguration` counts.
- **VERDICT:** ☑ Accept — _**Done.** `AUTOSELECT_DENYLIST` (strategies or `SYMBOL|STRATEGY` cells),
  wired through compose env; seeded with DMA20_Pullback, Fibonacci_Golden_Zone, Volume_Profile_POC,
  BSE|15m_ORB. Dry-run confirms they're skipped._

### F4 — Backtest non-determinism ("F1" from prior reports) = mutated tail candle

- **Observation:** `refreshData` re-fetches before every backtest and upserts overwrite the still-forming
  last candle; open positions mark to `c[n-1]`, so repeat runs pick different cells. `simulate()` itself
  is deterministic; MC/WF are seeded.
- **Evidence:** `routers/backtest.py:81`, `routers/history.py:165`, `base.py:212-213`.
- **VERDICT:** ☑ Accept (partial) — _**Mitigated** for auto-select: it now drops the trailing (possibly
  forming) bar before backtesting. The shared `/run-backtest` refresh path is unchanged (Phase C/next)._

### F5 — Backtest ≠ live exits (the core parity gap) — NOT yet fixed

- **Observation:** (a) live swing trailing stop is **dead code** — `get_recent_candles(n=10)` fetches 15m
  candles, so daily ATR is all-NaN and the chandelier trail never updates for any swing/mid/long trade,
  while the backtest trails aggressively. (b) Intraday exits differ entirely (backtest fixed SL/TP across
  days vs live breakeven+partials+candle-trail+reversal+15:15 square-off). (c) Live books **gross** P&L,
  backtest books **net** of costs. Consequence: proven live intraday winners (VWAP_MACD_RSI +₹2,943,
  RVOL_ORB +₹1,208) pass **0** gates because the backtest can't reproduce their exits.
- **Evidence:** `scanner/live_scanner.py:204,476-490,423-518`; `base.py:199-231`; `signals.service.ts:260`.
- **Sample size:** all 18 swing + 14 intraday strategies — **confidence: high.**
- **VERDICT:** ☑ Accept — _**Deferred to Phase C** (changes live execution; needs its own verification).
  Until then auto-select systematically undervalues intraday momentum — do not read a 0-pass as "bad."_

### F6 — P&L bookkeeping honesty gaps (FEAT-002, still open)

- **Observation:** scratches booked WIN (no BREAKEVEN band) inflate win-rate; `realizedPnl` column wrong
  on 177 rows (diverges from `pnl` by ~₹800); per-trade `pnlPercent` divides by leveraged notional not
  margin. Absolute `pnl` and cell compounding are correct, so the ledger is sound — the derived display
  fields mislead.
- **Evidence:** `signals.service.ts:264,286`; `trades.service.ts:344`.
- **VERDICT:** ☑ Accept — _**Pending (Track 3).** Portfolio "Invested Now" already corrected to margin
  (`investedNow = notional/leverage`) 2026-07-13._

### F7 — Swing book is a net drag; a few strategies bleed

- **Observation:** INTRADAY +₹6,680 (53% WR) carries the book; SWING −₹1,487 (−0.16R). Worst active
  strategy DMA20_Pullback −₹1,890 (PF 0.25). 15m_ORB is −₹1,554 overall **but** the loss is BSE|15m_ORB
  (already inactive); its 3 active cells are net +₹892 — so 15m_ORB was **not** cut.
- **Evidence:** per-strategy / per-cell SQL over 174 closed trades.
- **VERDICT:** ☑ Accept — _**Done.** Pruned DMA20_Pullback, Fibonacci_Golden_Zone, Volume_Profile_POC
  (9 cells, 77→68 active); recorded in `infra/scripts/hygiene-prune-losers.sql`. 15m_ORB kept._

---

## What I could NOT conclude

- **Whether the strict gates are "right."** 6 picks is defensibly quality-first, but it partly reflects
  F5 (backtest can't validate intraday), not just cell quality. The honest read: gates are correct given
  the current backtest; their real test comes after Phase C makes the backtest live-faithful.
- **True per-cell edge.** With notional (not risk-based) sizing, `cellRoiPct` is confounded by stop width;
  avgR is the cleaner metric but the live sample per cell is still thin.

## Actions taken this session (2026-07-13)

1. **Pruned** 9 ActiveConfiguration cells (DMA20_Pullback, Fibonacci_Golden_Zone, Volume_Profile_POC).
2. **Backtest de-inflation:** `BT_CAP_POSITION_VALUE` notional cap; NET `avgRMultiple` added to metrics.
3. **Auto-select:** rank by avg-R, tighter gates (DD 25 / PF 1.3 / OOS 60 / consistency on / MIN_AVG_R),
   persistent `AUTOSELECT_DENYLIST`, drop forming tail bar for determinism.
4. **Frontend/API:** Portfolio "Invested Now" now shows deployed margin, not leveraged notional.
5. **P&L bookkeeping (F6):** 0.1R BREAKEVEN band, `realizedPnl:=pnl` on close, margin-based per-trade %;
   history backfilled (`infra/scripts/backfill-pnl-bookkeeping.sql`).
6. **Phase C1 (F5a):** revived the dead live swing trailing stop (daily ATR via `get_recent_daily_candles`).
7. **Phase C2 (F5c):** live P&L now booked NET of transaction costs (`apps/api/src/common/costs.ts`, a
   verified port of the engine cost model). **This flipped the book from +₹4,623 gross to −₹4,182 net** —
   costs (₹8,805, ≈all intraday) exceed the gross edge. All 178 closed trades backfilled to net; win-rate
   45.5%, PF 0.90, ROI −13.9%. The honest baseline: **the current strategy mix does not beat costs.**
8. Deployed engine + api + frontend; verified via read-only dry-run auto-select and `/api/trades/stats`.

## The bottom line (post-cost)

The single most important number this audit produced: **net −₹4,182 / PF 0.90 / −13.9% ROI** once costs
are real. The intraday book over-trades at ~₹30 gross edge against ~₹49 cost. Improving the system now
means *fewer, higher-edge trades* — which is exactly what the tightened auto-select gates enforce (only
6 cells cleared). Phase C3 (make the backtest model live intraday exits) is the remaining lever so
auto-select can fairly rank the intraday strategies that live actually profits from before costs.

## Suggested next report

- **Phase C parity check:** after fixing the live swing trail (daily candles) + booking live P&L net of
  costs, re-run auto-select and compare its picks against the live leaderboard — they should start to
  agree. Until they do, treat auto-select as a *risk filter*, not a *winner picker*, for intraday.
