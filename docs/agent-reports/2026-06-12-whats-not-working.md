# Analyst Report — What's not working as expected

- **Date:** 2026-06-12
- **Lens:** What is NOT working as expected (broken rules vs regime shifts), evidence-first
- **Data window:** Live trades 2026-06-09 → 2026-06-12; backtest reports 2026-05-22 → 2026-06-09
- **Sample:** 17 Trade rows (12 CLOSED, 5–6 OPEN), 17 LiveSignal rows, 1363 BacktestReport rows (only **323 distinct** stock×strategy×timeframe cells)

## TL;DR (≤5 bullets)

- **The backtest table is corrupted by non-determinism.** The same cell, same `totalTrades`, re-run minutes apart, reports wildly different ROI — e.g. ADANIPOWER SuperTrend_EMA 1D (13 trades) booked **30.7% → 243.6% → 639.0%** on 2026-06-08. Any ranking built on raw rows is meaningless.
- **The 1363-row averages are upward-biased.** De-duping to the latest report per cell drops overall avg ROI from **26.96% → 15.00%** and lifts negative-cell share from 20.9% → **36.5%**. The system's headline numbers flatter the strategies.
- **Live is deep red and disagrees with backtest:** 12 closed trades, **net −₹807.26**, win rate **33.3%**, avg **−0.345R** — yet *every* strategy that traded live backtested *positive*. Worst live strategy (Fibonacci_Golden_Zone, −₹485) is the *best* backtest strategy.
- **Two strategies are genuinely broken after costs** on real sample sizes: BB_Mean_Reversion_Intraday (latest avg ROI **−11.7%**, 6/9 cells negative on 57–84 trades) and Bollinger_Mean_Reversion (latest avg **−11.7%**, daily DD often > capital).
- **Mechanics caveats:** 17 zombie/empty-strategy rows recorded with 0 trades; a +0.04R scratch booked as a WIN (trade 22); partials/trailing only ever fired on 3 of 12 closed trades. No BREAKEVEN bug seen; stop discipline is clean (all 8 losses = exactly −1.00R).

## Data health first

> Before any finding: is there even enough data to conclude anything? Be blunt.

- **Closed live trades: 12** — far too thin to trust any per-strategy live conclusion. Largest live cell is 15m_ORB at **4 trades**. Treat all live findings as directional, not statistical.
- **Backtest reports: 1363 rows, but only 323 distinct cells.** 215 cells are duplicated (max 21 copies of one cell). **51 rows have 0 trades**, 180 have 1–5 trades, 511 have 6–19 — i.e. ~38% of rows are too thin to size a strategy on.
- **Inherited caveats:** tiny live sample; ~4-day live window (single regime); backtest non-determinism (see F1) means even the de-duped "latest" cell may be a coin-flip draw. Live universe is concentrated — 7 of 17 trades are GROWW, 5 are BSE.
- **The DB is live:** a new OPEN trade (id 25, GROWW Volume_Profile_POC) appeared mid-analysis. Counts below are as-observed.

---

## Findings

### F1 — Backtest engine is non-deterministic; the report table cannot be trusted as-is

- **Observation:** Identical (stock×strategy×timeframe×totalTrades) cells report grossly different ROI/netProfit across runs. ADANIPOWER SuperTrend_EMA 1D, 13 trades, all on 2026-06-08 within ~46 min: netProfit ₹3,069 (30.7%), ₹24,364 (243.6%), then ₹63,903 (639.0%) — a **20×** spread on the same trade count. ETERNAL Fibonacci_Golden_Zone 1D (29 trades, same day) ranges 22.4% → 155.8%. Dozens more cells show the same divergence.
- **Evidence:** BacktestReport ids 1397/1490/1552/1624/1664/1681 (ADANIPOWER SuperTrend_EMA). Query: per (stock,strategy,timeframe,totalTrades), 15 cells have ≥2 distinct ROI values with max−min spread up to 608 ROI points. winRate stays constant across these (e.g. 69.2%) while ROI explodes — so the divergence is in P&L/sizing math, not trade selection.
- **Sample size:** 1363 rows / 323 cells — **confidence: high.** This is a code/data defect, reproducible across many cells.
- **Is it a broken rule or a regime shift?** **Broken rule** (engine bug). Same inputs, same period, different outputs — no market can explain it. Likely non-deterministic position sizing, compounding, or a re-entry/partial accounting path.
- **Hypothesis:** A single backtest of a fixed cell+period+seed will produce the same netProfit every run; the current spread is caused by mutable state (e.g. capital/sizing carried between runs, or randomized fill/slippage without a fixed seed). Fixing it will collapse the 20× spread to ~0.
- **Suggested validation:** Re-run one offending cell (ADANIPOWER SuperTrend_EMA 1D) N=20 times with a pinned seed and identical config; assert variance of netProfit ≈ 0. If it isn't, bisect the sizing/fill path. Until then, freeze auto-select from consuming raw BacktestReport rows.

> **VERDICT (Claude + user review, 2026-06-12):** ☑ Accept the *concern* / ☑ Reject the *mechanism*.
> — _notes:_ The "runtime non-determinism" diagnosis is **wrong** — verified against raw rows:
> the latest **six** consecutive runs of ADANIPOWER SuperTrend_EMA 1D are byte-identical
> (ROI 639.03, ids 1552→1773, spanning 16:34 Jun-8 → 04:17 Jun-9). The engine is deterministic
> given fixed code+data. The 30.7→243.6→639 spread falls inside a single 46-min window that
> coincides with active development (commits `f61ef27` bucket R:R, `28820b8` metrics). **Real root
> cause:** `BacktestReport` is append-only ([backtest.py:50-55](../../apps/engine/routers/backtest.py#L50-L55))
> so the table mixes results from *different engine versions*, and the leaderboard averages across
> all of them without dedup (see F2). Plus uncapped compounding sizing ([base.py:161](../../apps/engine/strategies/base.py#L161);
> the `max_position_value` cap at [backtest_config.py:59-61](../../apps/engine/backtest_config.py#L59-L61)
> is dead code) produces the 639% single-slot ROI. → **Feature: backtest-report-trust** (see docs/features).

### F2 — Headline backtest profitability is inflated by keeping the luckiest duplicate

- **Observation:** Averaging all 1363 rows gives avg ROI **26.96%** and 20.9% negative cells. De-duping to the **latest** report per cell gives avg ROI **15.00%** and **36.5%** negative cells. The duplicate rows skew positive because re-runs that landed high ROI (per F1) survive in the raw average.
- **Evidence:** All-rows vs latest-only per strategy: SuperTrend_EMA 72.6% → 44.0%; Fibonacci_Golden_Zone 101.6% → 74.0%; Break_And_Retest 47.8% → 23.2%; SMC_FVG 12.4% → **1.0%**; RSI_Divergence 13.9% → 3.1%; Bollinger_Mean_Reversion 2.3% → **−11.7%**. Every top strategy loses 30–50% of its apparent edge after de-duping.
- **Sample size:** 323 distinct cells — **confidence: medium-high.** The direction (inflation) is certain; exact magnitudes depend on F1 being fixed first.
- **Is it a broken rule or a regime shift?** **Broken rule** (selection/aggregation artifact compounding F1).
- **Hypothesis:** Whatever ranks/auto-selects strategies is reading mean-over-all-rows (or max), not latest-per-cell, so it systematically over-promotes strategies whose duplicates happened to print high. Switching to latest-per-cell will demote SMC_FVG and Bollinger families and change the monitored set.
- **Suggested validation:** Re-run the auto-select ranking on `DISTINCT ON (stockId,strategyName,timeframe) ... ORDER BY createdAt DESC` and diff the chosen set vs current. Confirm whether currently-monitored strategies survive the stricter ranking.

> **VERDICT (Claude + user review, 2026-06-12):** ☑ Accept (direction confirmed).
> — _notes:_ Dedup inflation **verified** (avg ROI 26.96% → 15.00% on latest-per-cell). Refinement:
> the monitored-stocks view *already* dedupes to latest-per-cell ([configs.service.ts:23-26](../../apps/api/src/configs/configs.service.ts#L23-L26)),
> so that surface is fine. The broken consumer is the **leaderboard**, which does
> `avg(roiPercentage) GROUP BY strategyName` across *all* rows with no dedup
> ([advanced_backtest.py:27-37](../../apps/engine/routers/advanced_backtest.py#L27-L37)) — over-weighting
> often-rerun cells and counting duplicate re-runs as independent samples (`confidence = reports/10`).
> Auto-select recomputes fresh so its *decisions* aren't poisoned, but it appends yet more dupes.
> Rolled into **Feature: backtest-report-trust**.

### F3 — Live results contradict backtest: every live strategy backtested positive, live net is −₹807

- **Observation:** 12 closed live trades: **net −₹807.26**, win rate **33.3%** (4W/8L), avg **−0.345R**. Yet the backtest cells for every live-traded strategy are positive (latest-per-cell): 15m_ORB BSE +18.0%/ATGL +48.3%, Fibonacci_Golden_Zone ETERNAL +155.8%(!), RVOL_ORB GROWW +22.5%, Volume_Profile_POC GROWW +17.7%, SMC_FVG BSE +16.2%. Worst live strategy = best backtest strategy.
- **Evidence:** Live by strategy — Fibonacci_Golden_Zone −₹485.16 (1 trade, −1.00R), 15m_ORB **−₹356.76 (0/4, −1.00R avg)**, RVOL_ORB −₹41.40 (1/2), Volume_Profile_POC −₹38.54 (2/4), SMC_FVG +₹114.60 (1/1, +1.76R). By horizon: INTRADAY −₹322.10 (11 closed), MID_SWING −₹485.16 (1 closed).
- **Sample size:** **12 closed (low).** 15m_ORB at 4 trades, others at 1–4. **Confidence: low** as proof, but the *direction and consistency* (loss across 4 of 5 strategies) plus the backtest-inflation (F1/F2) make the gap credible.
- **Is it a broken rule or a regime shift?** **Cannot yet separate**, but F1/F2 mean the backtest "promise" was overstated, so part of the gap is a broken rule (over-optimistic expectation), not pure regime. The clean −1.00R on all 8 losses shows execution/stops are *not* the problem — entries/edge are.
- **Hypothesis:** After F1/F2 are fixed, the realistic expected R for the live-traded cells (esp. 15m_ORB intraday and Fibonacci_Golden_Zone) will be far below what auto-select believed, partly closing the gap; remaining gap is live slippage/regime. Falsifiable: de-duped backtest expectancy for these exact cells will be materially lower than the raw figures used to select them.
- **Suggested validation:** Walk-forward the 5 live strategies on their exact symbols over the live window (2026-06-09→06-12) and compare per-trade R to live; then a Monte-Carlo over 100 reshuffles to see if a −0.345R/12-trade run is within noise of the (de-duped) backtest expectancy.

> **VERDICT (filled by human review):** ☐ Accept ☐ Reject ☐ Needs more data
> — _notes:_

### F4 — Two Bollinger strategies are net-negative after costs on solid samples and should not be monitored

- **Observation:** BB_Mean_Reversion_Intraday (15m): latest-per-cell avg ROI **−11.7%**, with the worst real-sample cells ADANIPOWER −28.3% (84 trades, 34.5% WR), BSE −19.8% (79 trades), OLAELEC −10.3% (57). 6 of 9 cells negative — all on 55–84 trades, i.e. reliable. Bollinger_Mean_Reversion (1D): latest avg **−11.7%**, and produces the table's single worst drawdowns (BSE −₹58,078 net on 40 trades; ADANIPOWER −₹63,812, DD ₹78,098 > the ₹10k slot model).
- **Evidence:** BB_Mean_Reversion_Intraday latest cells listed above (all 57–84 trades). Bollinger_Mean_Reversion worst cells: BacktestReport ids 532, 478/315/559/342 (BSE, identical −58,078 dup set), 930, 936.
- **Sample size:** 57–84 trades per intraday cell, 24–40 per daily cell — **confidence: high.** Big enough to call.
- **Is it a broken rule or a regime shift?** **Broken rule / structurally weak strategy** — negative across most symbols and large samples, not a one-symbol blip. Mean-reversion fighting trend in this universe.
- **Hypothesis:** Removing both Bollinger strategies from the monitored/auto-select pool raises portfolio expectancy with no loss of positive cells. Falsifiable: their de-duped contribution to the selected set is net-negative.
- **Suggested validation:** Confirm whether either is currently monitored (cross-check against the live signal generator config). Walk-forward both over the next out-of-sample window; expect continued negative expectancy.

> **VERDICT (filled by human review):** ☐ Accept ☐ Reject ☐ Needs more data
> — _notes:_

### F5 — Bookkeeping anomalies: empty-strategy reports, a scratch booked as WIN, and partials that rarely fire

- **Observation:** (a) **51 BacktestReport rows have totalTrades=0** (winRate 0, ROI 0) — notably Episodic_Pivot (17 rows, 0 trades) and MTF_Alignment (1 row) are recorded as if backtested but generated nothing; they pollute averages and any "strategy exists" logic. (b) **Trade 22** (GROWW Volume_Profile_POC SELL) entered 192.00, exited 191.92 = +₹4.08 / **+0.04R**, booked **outcome=WIN** — a scratch mislabeled as a win, which will inflate live win-rate. (c) **Trailing/partials fired on only 3 of 12 closed trades** (ids 8 PHASE2, 15 PHASE3, 20 PHASE2); the other 9 closed INITIAL. Where partials did fire, `realizedPnl` (₹76.50, ₹35.46) diverges from `pnl` (₹117.81, ₹65.72) and the 3 winners' aggregate `realizedPnl` is **0** on trade 8 despite a ₹114.60 win — the realizedPnl field is unreliable for reporting.
- **Evidence:** zero-trade count = 51; Trade id 22 fields above; trailingState distribution INITIAL(9C/5O), PHASE2(2), PHASE3(1); Trade id 8 pnl=114.60 but realizedPnl=0.00.
- **Sample size:** backtest 51 rows (high confidence it's a real artifact); live mechanics 12 trades (low — but each is individually verifiable).
- **Is it a broken rule or a regime shift?** **Broken rule** (data hygiene + outcome-classification + realizedPnl accounting).
- **Hypothesis:** (i) outcome=WIN should require pnl > some min-R threshold (or a BREAKEVEN band), else scratches inflate win-rate; (ii) realizedPnl is not being populated consistently and should not be used for live P&L until reconciled to pnl. Falsifiable: re-deriving outcome from pnl/riskAmount reclassifies trade 22, and summing realizedPnl ≠ summing pnl on closed trades.
- **Suggested validation:** Query `SUM(realizedPnl)` vs `SUM(pnl)` over CLOSED trades (they won't match); add a BREAKEVEN band test on |pnl/riskAmount| < 0.1 and recount win-rate. Exclude totalTrades=0 rows from all aggregates.

> **VERDICT (filled by human review):** ☐ Accept ☐ Reject ☐ Needs more data
> — _notes:_

---

## What I could NOT conclude

- **Whether the live edge is truly negative.** 12 closed trades over one 4-day regime is statistically nothing. The −₹807 / −0.345R could be normal variance even for a genuinely +EV system. F3 flags the *backtest-vs-live disagreement*, not a proven live loss.
- **Per-strategy live verdicts.** No live strategy has >4 closed trades; SMC_FVG "looks great" on exactly 1 trade (+1.76R) and Fibonacci "looks broken" on exactly 1 (−1.00R). Both are noise.
- **The true profitability ranking of strategies.** Until F1 (non-determinism) is fixed, even the de-duped latest-per-cell numbers may be a single lucky/unlucky draw rather than the strategy's real expectancy. I can say the *raw averages are inflated*; I cannot yet hand you a trustworthy ranked list.
- **Whether SHADOW/capital-starvation is costing money.** All 17 trades are FUNDED; there are zero SHADOW trades in the table, so the "would-have-won but starved" question has no data this run.
- **Open-trade outcomes.** 5–6 trades are still OPEN (oldest id 13, ~2.1 days, a MID_SWING) — not yet stuck/abnormal, but unresolved and excluded from all P&L above.

## Suggested next report

- **After F1 is fixed:** a "true strategy ranking" report on de-duped, deterministic backtests with walk-forward + Monte-Carlo confidence bands per (strategy×timeframe), so auto-select consumes trustworthy expectancy. Pair it with a check of which strategies are *currently monitored* vs which the corrected ranking would keep — that diff is the highest-value action this analysis points to.
