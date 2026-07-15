# Analyst Report — What's not working as expected

- **Date:** 2026-06-16
- **Lens:** What is NOT working as expected (broken rules vs regime shifts), evidence-first
- **Data window:** Live trades 2026-06-09 → 2026-06-16; backtest reports 2026-05-22 → 2026-06-12
- **Sample:** 45 Trade rows (40 CLOSED, 5 OPEN; 37 FUNDED / 8 SHADOW), 45 LiveSignal rows, 1901 BacktestReport rows (only **480 distinct** stock×strategy×timeframe cells)

## TL;DR (≤5 bullets)

- **Live loss shrank but is still red and still backtest-contradicting.** 40 closed trades: net **−₹75.54**, WR **52.5%** (21W/19L), avg **+0.096R** — but that +0.096R is entirely two SMC_FVG winners (+₹349.80). Strip them and it's **−₹425.34 / −0.073R over 38 trades.** Every big live *loser* cell backtested *positive*. F3 firms up.
- **The deduped backtest table flipped to majority-negative.** Latest-per-cell now: avg ROI **22.75% → 11.79%**, and **50.8% of 480 cells are net-negative** (was 36.5% of 323). On reliable samples (≥20 trades), **15 of 19 strategies have negative avg ROI.** The system's edge is thinner than any headline shows.
- **The compounding/DD artifact (F1 residue) is still in the live table.** ADANIPOWER EMA_RSI 1D books **+187% ROI / +₹187,034 net on 12 trades** on a ₹10k slot; 8 reliable cells show drawdowns > the ₹10k slot (EMA_RSI 1D up to **₹61,664 DD / −₹46,401 net**). These are uncapped-sizing artifacts, not real expectancy.
- **The Bollinger story narrowed correctly: broken, but already quarantined.** BB_Mean_Reversion_Intraday is −14.92% across **15/15 negative** reliable cells; Bollinger_Mean_Reversion −21.22%. BUT zero of the 93 monitored cells are net-negative on reliable samples — the broken Bollinger cells are NOT monitored. F4 refines from "remove them" to "confirm they stay out."
- **Bookkeeping: scratches-as-WIN and realizedPnl are still broken.** 3 WINs are <0.1R scratches (ids 40, 50, 22); `realizedPnl` is 0 for every INITIAL-state exit, so SUM(realizedPnl) **+₹737.43** vs SUM(pnl) **−₹75.54** — a ₹813 reporting gap. F5 firms up.

## Data health first

> Before any finding: is there even enough data to conclude anything? Be blunt.

- **Closed live trades: 40** (up from 12) — meaningful enough for *portfolio-level* directional reads, still **too thin per cell.** Largest live cell is GROWW RVOL_ORB at **5 trades**; most are 1–4. No per-strategy live verdict is statistically safe.
- **Backtest reports: 1901 rows, 480 distinct cells.** Of the 480 deduped cells: **42 have 0 trades**, 66 have 1–5, 148 have 6–19, **224 have ≥20** (reliable). Raw table still holds **104 zero-trade rows.**
- **SHADOW trades now exist:** 8 of 40 closed are SHADOW (capital-starved) — the first sample to even ask the "would-have-won but starved" question.
- **Inherited caveats:** ~7-day live window (single broad regime); the compounding/append-only artifacts (prior F1) are unfixed in the data (backtest-report-trust feature still in progress); live universe concentrated — GROWW 12 of 45 trades (27%), BSE 7.
- **The DB is live.** Counts are as-observed at ~2026-06-16 12:52 UTC.

---

## Findings

### F1 — Live still contradicts backtest; the +0.096R headline is two trades of noise

- **Observation:** 40 closed trades net **−₹75.54**, WR 52.5%, avg **+0.096R**. Removing the only outlier strategy (SMC_FVG, 2 trades, +₹349.80, +1.76R & +4.85R) leaves **−₹425.34 / −0.073R over 38 trades.** The largest live-loss cells all carry *positive* deduped backtest expectancy: ETERNAL Fibonacci_Golden_Zone (bt **+151% ROI** / live −1.00R / −₹485), ADANIPOWER Volume_Profile_POC (bt +9.6% / live −0.65R / −₹250), APOLLO EMA_RSI (bt +33.8% / live −1.00R / −₹250), BSE 15m_ORB (bt +21.9% / live −0.86R / −₹225), ATGL 15m_ORB (bt +42.6% / live −0.32R / −₹199).
- **Evidence:** Live-by-cell vs deduped-backtest join (any timeframe): 5 of the 6 worst live cells have positive bt ROI. SMC_FVG trades = ids 8 (BSE, +1.76R), 29 (APOLLO, +4.85R). EMA_RSI live: −₹232.91 over 6 (2W/4L). 15m_ORB live: −₹331.60 over 9.
- **Sample size:** 40 closed (largest cell 5) — **confidence: medium for the portfolio direction, low per cell.** The disagreement is now consistent across ~7 cells and ~4 strategies, not 1.
- **Is it a broken rule or a regime shift?** **Mostly broken rule (over-stated expectation).** Stop discipline is clean (16 of 19 losses are exactly −1.00R), so entries/edge — not execution — are the problem; and the backtest "promise" for these cells is itself inflated by the compounding/dedup artifacts (F2/F3). Part may be regime (one 7-day window), but the backtest was never as good as advertised.
- **Hypothesis:** After the deduped, compounding-capped expectancy for these exact cells is computed, ETERNAL Fibonacci, ADANIPOWER Volume_Profile_POC and the 15m_ORB cells will show materially lower (some negative) realistic R than what auto-select believed — closing much of the gap before invoking regime.
- **Suggested validation:** Walk-forward the live-traded cells on their exact symbols over 2026-06-09→06-16 with corrected sizing; then a Monte-Carlo over 200 reshuffles to test whether −0.073R/38-trade (ex-SMC) is inside the noise band of the corrected backtest expectancy.

> **VERDICT (filled by human review):** ☐ Accept ☐ Reject ☐ Needs more data
> — _notes:_

### F2 — Deduped backtest table is now majority net-negative; the edge is thinner than any headline

- **Observation:** Latest-per-cell dedup over 480 cells: avg ROI **11.79%** vs **22.75%** raw — and **50.8% of cells are net-negative** (244 of 480), up from 36.5% in the prior run. On reliable cells (≥20 trades), **15 of 19 strategies post negative average ROI**, including live-traded EMA_RSI (−9.25%, 15/19 cells neg), Volume_Profile_POC (−0.52%), VWAP_MACD_RSI (−0.97%), RVOL_ORB (−2.65%), SMC_FVG (−2.40%). Only Fibonacci_Golden_Zone (+109.4%), MACD_Stoch_Confluence (+36.2%) and DMA20_Pullback (+19.7%) look strongly positive — and the first is inflated by the compounding artifact (F3).
- **Evidence:** dedup vs raw: 480 cells / avg ROI 11.79 / 50.8% neg vs 1901 rows / 22.75 / 28.6% neg. Per-strategy ≥20-trade averages as listed above. Most "positive" strategies survive only via a few uncapped-compounding cells.
- **Sample size:** 480 deduped cells, 224 reliable — **confidence: high for the direction (inflation + majority-negative), medium for exact magnitudes** (still contaminated by uncapped sizing, see F3).
- **Is it a broken rule or a regime shift?** **Broken rule** (aggregation + sizing artifact). Half the universe being net-negative after costs is a structural property of the strategy pool + cost model, not a market move.
- **Hypothesis:** Once compounding is capped to the ₹10k slot (per backtest-report-trust), the handful of >+100% cells collapse, several "positive" strategies (Fibonacci especially) drop sharply, and the net-negative cell share rises further — meaning the deployable strategy set is much smaller than 480 cells implies.
- **Suggested validation:** Recompute per-cell ROI with the `max_position_value` cap actually enforced; re-rank strategies; diff the set that clears a "≥20 trades AND positive AND DD<slot" bar against the current 93 monitored cells.

> **VERDICT (filled by human review):** ☐ Accept ☐ Reject ☐ Needs more data
> — _notes:_

### F3 — Uncapped compounding still poisons the live backtest table (drawdowns and ROI exceed the slot)

- **Observation:** The ₹10k-slot model cannot produce these, yet they are live rows: ADANIPOWER EMA_RSI 1D = **+187.0% ROI / +₹187,034 net on 12 trades** (id 584); BSE EMA_RSI 1D +91.3% / +₹91,291; 3 deduped cells exceed +₹50,000 net. On the loss side, **8 reliable deduped cells have maxDrawdown > the ₹10k slot**: ADANIENT EMA_RSI 1D **DD ₹61,664 / −₹46,401 net**, VEDL EMA_RSI 1D DD ₹53,958 / −₹27,755, HDFCBANK EMA_RSI 1D DD ₹42,047 / −₹37,124, plus 5 Fibonacci_Golden_Zone 1D cells with DD ₹11k–₹17k.
- **Evidence:** netProfit>50000 → 3 cells, max ₹187,034. maxDrawdown>10000 & trades≥20 → 8 cells (EMA_RSI 1D and Fibonacci_Golden_Zone 1D dominate). winRate on the +187% cell is only 58.3% on 12 trades — impossible to compound to +₹187k from ₹10k without uncapped re-sizing.
- **Sample size:** Whole table — **confidence: high.** Deterministic, reproducible artifact; this is the residue of prior-F1's *real* root cause (uncapped sizing + dead cap at backtest_config.py), not non-determinism.
- **Is it a broken rule or a regime shift?** **Broken rule** (sizing/accounting). No market produces a ₹187k slot return.
- **Hypothesis:** Enforcing the `max_position_value` cap per slot collapses every >+100% ROI cell and every >₹10k DD cell to within-slot magnitudes; Fibonacci_Golden_Zone and EMA_RSI 1D will lose most of their apparent extremes in both directions.
- **Suggested validation:** Re-run ADANIPOWER EMA_RSI 1D (id 584) and ADANIENT EMA_RSI 1D with the position cap enforced; assert |netProfit| ≤ a few × ₹10k. This is a direct test of the backtest-report-trust fix.

> **VERDICT (filled by human review):** ☐ Accept ☐ Reject ☐ Needs more data
> — _notes:_

### F4 — Bollinger pair is structurally broken — but already quarantined from the monitored set

- **Observation:** Deduped, reliable: **BB_Mean_Reversion_Intraday (15m) = −14.92% avg, 15/15 cells negative** (ADANIPOWER −27.8%/88 tr, BSE −21.6%/86 tr, GROWW −18.7%/81 tr, etc.); **Bollinger_Mean_Reversion (1D) = −21.22%, 5/8 negative**, with the table's worst daily cells (MTARTECH −67.8%/30 tr, BSE −59.6%/32 tr, ETERNAL −51.9%/24 tr; DDs ₹4.7k–₹7.9k). **However:** of 93 monitored cells, **zero are net-negative on reliable samples**; the one monitored Bollinger_Mean_Reversion cell is **HDFCBANK 1D (+29.0% ROI, 18 trades)** — a positive outlier, not a broken cell. The broken Bollinger cells are not monitored.
- **Evidence:** BB_Mean_Reversion_Intraday 15 reliable cells all negative; Bollinger_Mean_Reversion worst cells listed. ActiveConfiguration has 1 Bollinger_Mean_Reversion row = HDFCBANK 1D; the monitored-vs-backtest join returns 0 negative-reliable monitored cells.
- **Sample size:** 57–88 trades/intraday cell, 18–32/daily cell — **confidence: high the strategies are weak; high they're currently quarantined.**
- **Is it a broken rule or a regime shift?** **Broken rule / structurally weak strategy** (mean-reversion vs trend across the universe). The quarantine working is a *correct* behavior, not a problem — the risk is a future auto-select re-promoting a lucky Bollinger cell.
- **Hypothesis:** A blanket exclusion of both Bollinger strategies from the auto-select pool costs nothing (their only surviving positive cells, e.g. HDFCBANK 1D, are small-sample luck and will mean-revert to the −15%/−21% strategy average on out-of-sample data).
- **Suggested validation:** Walk-forward HDFCBANK Bollinger_Mean_Reversion 1D out-of-sample; expect it to regress toward the −21% strategy mean. Add a guard so auto-select cannot pick any Bollinger cell while the strategy-level average is negative.

> **VERDICT (filled by human review):** ☐ Accept ☐ Reject ☐ Needs more data
> — _notes:_

### F5 — Bookkeeping still broken: scratches booked as WIN, realizedPnl unreliable, sub-1R loss leakage

- **Observation:** (a) **3 WINs are scratches** (|R|<0.1): id 40 GROWW EMA_RSI +0.031R (₹1.88), id 50 DATAPATTNS Volume_Profile_POC +0.038R (₹3.20), id 22 GROWW Volume_Profile_POC +0.044R (₹4.08) — inflating WR. (b) **`realizedPnl` is 0 on every INITIAL-state exit** even when pnl is large (id 9 pnl −₹485 / realized ₹0; id 8 pnl +₹114.60 / realized ₹0), so **SUM(realizedPnl) = +₹737.43 vs SUM(pnl) = −₹75.54** — an ₹813 reporting gap; realizedPnl tracks only partials, never the final leg. (c) **Stop leakage:** not all losses are −1R — id 51 GROWW EMA_RSI is a **−0.114R "loss" (−₹10)**, a scratch booked LOSS; id 30 BSE 15m_ORB −0.584R, id 47 ATGL −0.777R closed *better* than −1R (trailing/manual?), worth confirming intended. (d) Trailing fired on only **13 of 40** closed (8 PHASE2, 5 PHASE3); 27 closed INITIAL.
- **Evidence:** scratch WINs = ids 40/50/22; sub-1R losses = ids 51/30/47; realizedPnl=0 with non-zero pnl across all 27 INITIAL closes; SUM(realizedPnl) 737.43 vs SUM(pnl) −75.54; trailingState INITIAL=27C, PHASE2=8, PHASE3=5.
- **Sample size:** 40 closed (each individually verifiable) — **confidence: high** that these are real data-hygiene defects.
- **Is it a broken rule or a regime shift?** **Broken rule** (outcome classification + realizedPnl accounting). Persists from prior F5; the larger sample makes the realizedPnl/pnl divergence unambiguous.
- **Hypothesis:** (i) outcome should require |pnl/riskAmount| ≥ a BREAKEVEN band (~0.1R) else classify BREAKEVEN — reclassifies ids 40/50/22/51 and corrects WR; (ii) realizedPnl must include the final-leg P&L or be deprecated for reporting in favor of pnl.
- **Suggested validation:** Add the BREAKEVEN-band test and recount WR (expect it to drop from 52.5%); assert SUM(realizedPnl)=SUM(pnl) over CLOSED trades (currently fails by ₹813) and trace where the final leg is dropped.

> **VERDICT (filled by human review):** ☐ Accept ☐ Reject ☐ Needs more data
> — _notes:_

---

## What I could NOT conclude

- **Whether live edge is truly negative.** 40 trades over one ~7-day regime, largest cell 5 trades. Ex-SMC −0.073R could be variance for a genuinely flat/slightly-+EV system. F1 flags the *backtest-vs-live disagreement*, not a proven negative live edge.
- **Whether SHADOW capital-starvation is costing money.** The 8 SHADOW trades net **+₹17.84** (5W/3L, −0.148R) — slightly profitable but on 8 trades, so no signal on whether starving them lost real money. Two SHADOW losses (ids 37, 38, APOLLO EMA_RSI) were full −1R, so starving them *saved* money there.
- **The true strategy ranking.** Until compounding is capped (F3), even deduped cells mix realistic and ₹187k-slot numbers; Fibonacci_Golden_Zone's +109% strategy average is untrustworthy. I can say the deduped table is majority-negative; I cannot hand over a trustworthy ranked list.
- **Whether SELL underperforms BUY.** Aggregate SELL avg R (−0.148) looks worse than BUY (+0.366), but BUY is propped by SMC_FVG (+3.3R) and SELL has its own winners (ids 32, 33 at +1.4R); per-strategy the signal is mixed and the samples are 1–7. No conclusion.

## Suggested next report

- **After the compounding cap lands (backtest-report-trust):** a "true strategy ranking" report on capped, deduped, deterministic backtests with walk-forward + Monte-Carlo bands per (strategy×timeframe), and an explicit diff of the corrected top set vs the current 93 monitored cells — with attention to the **25 of 93 monitored cells backed by only 1–5 backtest trades** (thin selection risk this run surfaced). Pair it with a re-check of F1's live-vs-backtest gap on the (by then larger) closed sample.
