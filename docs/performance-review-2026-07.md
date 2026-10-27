# Live System Performance Review — v1

**Review date:** 2026-07-08
**Data window:** 2026-06-05 → 2026-07-08 (~1 month live)
**Environment:** work-pc, `smart-trading` v1 stack (DB `smart-trading-db`, port 5470)
**System status at review:** Healthy — scanner running, 11 signals generated today, last signal 2026-07-08 10:31 IST.

> Scope: this review covers **v1 only**, as requested. The parallel v2 stack was excluded.

---

## 1. Headline

| Metric | Value |
|---|---|
| Total trades | 347 (334 closed, 13 open) |
| **Net realized P&L** | **+₹84,670** |
| Win rate | 47.9% (160 W / 174 L) |
| Profit factor | **1.30** |
| Gross profit / gross loss | +₹370,840 / −₹286,170 |
| Avg win / avg loss | +₹2,318 / −₹1,645 |
| Payoff ratio (win:loss size) | 1.41 |
| Expectancy per trade | +₹254 |
| Avg hold (closed intraday) | 1.8 h (max 5.9 h, 0 overnight) |

**Verdict:** The system is **net profitable and behaving as designed.** It wins on payoff, not hit-rate — a sub-50% win rate is fully carried by winners being ~1.4× the size of losers. This is a healthy, sustainable signature for a trend/breakout system, but it depends entirely on the exit engine (see §3) and leaves little cushion if that degrades.

---

## 2. Equity curve (weekly, cumulative)

| Week of | Trades | Weekly P&L | Cumulative |
|---|---:|---:|---:|
| 2026-06-01 | 6 | +₹5,621 | ₹5,621 |
| 2026-06-08 | 77 | +₹21,241 | ₹26,862 |
| 2026-06-15 | 75 | +₹26,630 | ₹53,492 |
| 2026-06-22 | 58 | +₹12,147 | ₹65,639 |
| 2026-06-29 | 89 | +₹28,827 | ₹94,466 |
| 2026-07-06 | 29 | **−₹9,796** | ₹84,670 |

Four straight positive weeks, then the current week is drawing down (−₹9,796). One down week after a strong run is normal, but it coincides with the weakest strategies still being live (§4) — worth watching, not yet alarming.

---

## 3. The core driver: the phased trailing engine

This is the most important finding. Segmenting by `trailingState`:

| Trailing state | Trades | Total P&L | Read |
|---|---:|---:|---|
| INITIAL (never trailed) | 215 | **−₹244,625** | SL hits + flat exits — the cost of doing business |
| PHASE2 (partial trail) | 39 | +₹66,459 | Winners that got legged up |
| PHASE3 (full trail) | 80 | **+₹262,836** | The profit engine |

**The entire net profit comes from the ~35% of trades that reach a trailing phase.** Trades that never trail bleed a quarter-million rupees; the phased protection recovers all of it and adds the surplus. This validates the trade-protection design ([trade_protection.md](trade_protection.md)) as the single most valuable component of the system. Any change that touches trailing logic should be treated as high-risk.

Corroborated by the R-multiple distribution:

| R bucket (pnl / risk) | Trades | P&L |
|---|---:|---:|
| ≤ −1R (full stop) | 68 | −₹135,517 |
| −1R…0R | 106 | −₹150,653 |
| 0R…1R | 65 | +₹63,386 |
| **1R…2R** | **87** | **+₹255,241** |
| 2R…3R | 4 | +₹19,309 |
| 3R+ | 4 | +₹32,904 |

The 1–2R bucket is the workhorse. There are very few 3R+ outliers, so profit is broad-based rather than lottery-driven — a good sign for stability.

---

## 4. Strategy performance

| Strategy | Trades | Win % | P&L | PF |
|---|---:|---:|---:|---:|
| EMA_RSI | 65 | 58.5 | +₹49,620 | 2.12 |
| CPR_Breakout | 71 | 47.9 | +₹36,313 | 1.54 |
| MACD_Zero | 42 | 52.4 | +₹19,845 | 1.59 |
| SMC_FVG | 12 | 58.3 | +₹8,344 | 1.95 |
| VWAP_MACD_RSI | 6 | 66.7 | +₹7,342 | 4.00 |
| RVOL_ORB | 5 | 80.0 | +₹7,004 | — (tiny n) |
| 15m_ORB | 52 | 44.2 | +₹1,513 | 1.03 |
| SMA44_Pullback | 1 | 0.0 | −₹1,941 | — |
| Inside_Bar | 3 | 33.3 | −₹2,964 | 0.26 |
| VWAP_Supertrend | 30 | 43.3 | −₹3,149 | 0.85 |
| Fibonacci_Golden_Zone | 5 | 20.0 | −₹7,340 | 0.06 |
| **Volume_Profile_POC** | 42 | 31.0 | **−₹29,917** | 0.38 |

**Winners:** EMA_RSI is the standout (₹49.6k, PF 2.12) and, with CPR_Breakout and MACD_Zero, produces ~₹105k of the ~₹85k net — i.e. the good strategies more than fully fund the losers.

**Clear drags:**
- **Volume_Profile_POC** — 42 trades, 31% win, PF 0.38, **−₹29,917.** This single strategy is the largest capital leak. It has a full sample and is unambiguously unprofitable as configured.
- **Fibonacci_Golden_Zone** (−₹7,340, PF 0.06) and **VWAP_Supertrend** (−₹3,149) are also negative.

Note: Volume_Profile_POC and the SMC/FVG strategies were added in the last refactor (commit `8831def`). SMC_FVG is doing well; Volume_Profile_POC is not.

---

## 5. Directional asymmetry (BUY vs SELL)

| Side | Trades | Win % | P&L | Avg win | Avg loss |
|---|---:|---:|---:|---:|---:|
| SELL (short) | 163 | 54.6 | **+₹84,533** | +₹2,211 | −₹1,517 |
| BUY (long) | 171 | 41.5 | +₹136 | +₹2,451 | −₹1,739 |

**Essentially 100% of the net profit came from the short side.** The long side broke even over a full month and a near-equal trade count. This is most likely a **market-regime effect** (the review window favored shorts) rather than broken long logic — the per-win sizes are comparable. But it's a concentration risk: if the regime flips, the long book needs to carry weight it hasn't shown yet. Worth tracking BUY vs SELL P&L going forward as a regime gauge.

---

## 6. Symbol concentration

| Top symbols | P&L | | Bottom symbols | P&L |
|---|---:|---|---|---:|
| HDFCBANK | +₹54,908 | | ADANIPOWER | −₹24,779 |
| ADANIENT | +₹36,357 | | GROWW | −₹10,399 |
| ZEEL | +₹12,171 | | JWL | −₹2,362 |

HDFCBANK + ADANIENT alone account for ~₹91k — more than the entire net. **ADANIPOWER is a persistent loser (−₹24.8k over 48 trades)** and is worth reviewing as a symbol-level exclusion or a signal-quality filter.

---

## 7. Open positions & the stale-swing concern

13 positions are currently open. Most are same-day (2026-07-08) intraday/swing entries — fine. But three are old **swing** trades that have never exited:

| Symbol | Strategy | Hold type | Days open |
|---|---|---|---:|
| VEDL | Bollinger_Mean_Reversion | MID_SWING | **26** |
| ADANIPOWER | SuperTrend_EMA | SHORT_SWING | 15 |
| ADANIPOWER | SMA44_Pullback | SHORT_SWING | 14 |

These are **not** orphaned intraday trades (closed intraday trades show 0 overnight holds and a 1.8 h average — that path is clean). They are swing trades whose exit conditions haven't fired. A MID_SWING position open for 26 days suggests the **swing-exit / max-hold logic is either missing or not triggering** for these newer strategies (Bollinger_Mean_Reversion, SuperTrend_EMA, SMA44_Pullback all have little-to-no closed history). Recommend adding a max-hold / time-stop for swing trades so positions can't drift indefinitely.

---

## 8. Recommendations

**High-priority**
1. **Retire or rework Volume_Profile_POC.** −₹29,917 at PF 0.38 over a full sample — disabling it alone would have lifted net P&L to ~₹115k. Same treatment for Fibonacci_Golden_Zone (PF 0.06).
2. **Add a swing max-hold / time-stop.** Close the gap that leaves MID/SHORT_SWING trades open for 2–4 weeks (VEDL, ADANIPOWER). Manually review the 3 stale opens now.
3. **Protect the trailing engine.** It generates 100% of net profit (§3). Freeze/regression-guard the trailing logic; add a monitoring alert if the PHASE2/PHASE3 share of trades drops sharply.

**Medium-priority**
4. **Investigate the long side.** BUY is break-even. Confirm whether it's regime (likely) or a systematic long-entry weakness; add BUY-vs-SELL P&L to the dashboard as a regime signal.
5. **Symbol-level review of ADANIPOWER** (−₹24.8k) — consider exclusion or a tighter filter.
6. **Watch the current down week.** −₹9,796 so far; not alarming after 4 up weeks, but confirm it's noise and not a strategy going bad.

**Low-priority / good-to-keep**
7. Concentrate capital toward the proven set (EMA_RSI, CPR_Breakout, MACD_Zero) once the drags are removed.
8. Keep the small-sample promising strategies (VWAP_MACD_RSI, RVOL_ORB, SMC_FVG) live but flagged as "insufficient sample" until n ≥ 20.

---

## 9. Bottom line

After a month live, v1 is **net profitable (+₹84,670, PF 1.30)** with a coherent, well-understood edge: a trend-following system whose profitability is manufactured by the phased trailing engine, concentrated in a handful of strong strategies and (this window) the short side. The single biggest, safest improvement available is **removing the known loser strategies** — that change alone would have grown net P&L by ~35% with no new risk. Second is closing the **swing time-stop gap** so positions can't sit open for weeks. The system is doing its job; the work now is trimming the drags and tightening the exits.
