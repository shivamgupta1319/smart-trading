# Live System Performance Review — v2

**Review date:** 2026-07-11
**Data window:** 2026-06-09 → 2026-07-10 (~1 month live)
**Environment:** work-pc, `smart-trading-v2` stack (DB `smart-trading-v2-db`, port 5471)
**System status at review:** Healthy — all 6 services Up, scanner heartbeating,
`HistoricalData` fresh to 2026-07-10, 6 open positions.

> Scope: **v2 only.** Paper-trading, ₹1L account, 10 equal-weight ₹10k slots.

---

## 1. Headline (FUNDED closed trades)

| Metric | Value |
|---|---|
| Funded closed trades | 113 (5 open) |
| **Net realized P&L** | **−₹2,704** |
| Win rate | 49.1% (55 W / 57 L / 1 BE) |
| Profit factor | **0.69** |
| Gross profit / gross loss | +₹6,048 / −₹8,752 |
| Avg win / avg loss | +₹110 / −₹154 |
| **Payoff ratio (win:loss size)** | **0.72** ⟵ inverted |
| Expectancy per trade | **−₹24** |
| Best / worst single trade | +₹413 / −₹893 |
| Shadow closed book (not funded) | 114 trades, net −₹456 |

**Verdict:** Net negative, and the cause is **not** funding, execution, or bad luck — it
is **structural R:R inversion**. The system wins ~half its trades but the average loser
(₹154) is bigger than the average winner (₹110). Stop discipline is actually clean (losers
cluster at exactly −1.00R), so the leak is on the **profit side and in position sizing**,
not the stop side.

---

## 2. Why the profits are small (the "₹200–300 per trade" question)

Two independent reasons, both by design:

1. **Slot size caps the rupees.** Each position gets one ₹10k slot
   (`qty = floor(slot/entry)`, avg capital deployed ₹9,178). A good +2–4% intraday move on
   ₹9k is **₹180–370** — exactly the "small ₹200–300 wins" you see. Bigger absolute wins
   would require bigger slots (fewer concurrent positions, or more capital), not a code bug.
2. **Winners are cut to ~1R.** Avg winning trade is **+0.95R** — targets sit near 1R and
   many near-scratch exits get booked as tiny wins. There is no "let winners run" phase, so
   the upside tail that would pay for the losers never materializes.

Small wins are only a problem *because* the losers aren't equally small — see §3.

---

## 3. Why the month is net negative — the swing book

Splitting the funded book by hold type is the whole story:

| Bucket | Trades | Avg ₹ risk / trade | Net P&L |
|---|---:|---:|---:|
| **INTRADAY** | 101 | ₹121 | **+₹420** |
| **SWING** (short/mid/long) | 12 | ₹627 | **−₹3,124** |

- The **intraday book is roughly breakeven-positive** (+₹420 over 101 trades).
- **12 swing trades lost −₹3,124** — *more than the entire book's net loss.* Kill the
  swing book and v2 is marginally green.
- **Root mechanism — notional sizing ignores stop distance.** Sizing is
  `qty = floor(slot/entry)` (notional), so every trade deploys ~₹10k *regardless of how
  wide its stop is*. Swing trades have far wider stops, so the same ₹10k slot risks **~5×
  more rupees** (₹627 vs ₹121). When a swing trade hits its −1R stop it gives back ~5
  intraday winners. The book is therefore dominated by the highest-variance, widest-stop
  trades — and those are the ones bleeding.

### Worst offenders (funded closed, by strategy)

| Strategy | n | W/L | Net |
|---|---:|---|---:|
| **Fibonacci_Golden_Zone** | 4 | 0 / 4 | **−₹2,619** |
| DMA20_Pullback | 3 | 1 / 2 | −₹908 |
| MACD_Stoch_Confluence | 2 | 1 / 1 | −₹472 |
| VWAP_Supertrend | 11 | 5 / 6 | −₹292 |
| 15m_ORB | 23 | 9 / 13 | −₹267 |
| Volume_Profile_POC | 24 | 11 / 13 | −₹170 |

**Fibonacci_Golden_Zone alone (−₹2,619, 0-for-4) is ~97% of the net loss.** It is a
swing strategy that went 0/4, every loss a clean −1.00R. It is *still live with 6 active
cells* and will keep bleeding until pruned. This matches analyst finding **F3**: the cells
that lose worst live all backtested strongly positive — the backtest expectancy for these
cells is not surviving contact with the live tape (regime and/or inflated backtest).

---

## 4. Funded vs "unfunded" (SHADOW) — what you're seeing

- **FUNDED** = a free slot existed when the signal fired → it gets paper money and counts
  toward ROI. **SHADOW** = all 10 slots were already occupied → the trade is recorded for
  analysis but **not funded** and excluded from ROI. This is the ~50/50 split you noticed
  (113 funded / 114 shadow closed).
- The **shadow book is also net negative (−₹456)**, which is the important tell: funding
  more of them would have lost *more*, not less. The edge itself is thin/negative right now
  — this is not an allocation bug.
- Slots stay occupied for a long time because **swing positions sit open for weeks** (INFY
  open since Jun 24, ADANIPOWER since Jun 23). Long-held swings both (a) hog slots so fresh
  intraday signals go SHADOW, and (b) are the trades doing the damage.

---

## 5. Bookkeeping issues confirmed live (FEAT-002, still unfixed in prod)

Independent of P&L, the reported metrics are quietly distorted — both defects from the
[live-trade-bookkeeping-hygiene](features/live-trade-bookkeeping-hygiene/understanding.md)
doc are present in production data:

- **No BREAKEVEN band.** Only **1** trade in 113 is labelled BREAKEVEN — scratches that
  close a few rupees either side of zero are booked WIN/LOSS by sign, inflating the headline
  win-rate.
- **`realizedPnl` drops the final leg.** `SUM(realizedPnl)` and `SUM(pnl)` disagree by
  **₹6,181** across all closed trades, with **177 rows** showing `realizedPnl=0` on a
  non-zero `pnl`. Any consumer summing `realizedPnl` as account P&L is wrong (equity display
  itself sums `pnl`, so displayed equity is safe — but the column and the analyst assertions
  are not).

---

## 6. Recommendations (priority order)

1. **Prune the losing swing strategies now.** Run
   [`infra/scripts/hygiene-prune-losers.sql`](../infra/scripts/hygiene-prune-losers.sql)
   (removes Fibonacci_Golden_Zone, VWAP_Supertrend, Volume_Profile_POC from live scanning —
   reversible). This alone flips the book roughly breakeven-to-green. **Needs your sign-off;
   it is not auto-applied.**
2. **Fix the sizing asymmetry (the real structural fix).** Move swing trades to
   **risk-based sizing** (`qty = floor(risk_budget / stop_distance)`) so a wide-stop swing
   risks the same rupees as a tight-stop intraday trade, instead of ~5×. Today's notional
   sizing lets the widest-stop trades dominate P&L variance — that is why a 49%-win system
   is net red. (Note: the capital-slot model deliberately chose notional sizing for
   backtest≡live parity — so this is a *decision to revisit with eyes open*, and must be
   changed in **both** live and backtest sizing to stay consistent.)
3. **Let intraday winners run.** Payoff is 0.72 with winners capped near 1R. A trailing /
   phased exit that pushes the average winner past the average loser would turn the
   already-breakeven intraday book profitable on its own.
4. **Add a swing time-stop.** Positions open 2–3 weeks hog slots and force fresh signals to
   SHADOW. Cap swing hold duration so capital recycles.
5. **Implement FEAT-002 bookkeeping fixes** so win-rate and `realizedPnl` stop misleading
   the review (and the analyst agent's health checks pass).

> Items 2–5 are code changes in `apps/api` / `apps/engine`, out of scope for this review
> (which is diagnosis + the reversible strategy prune). Item 1 is a one-line SQL run.
