# Glossary — every term in one plain sentence

Written for the owner. If a doc uses a word that is not here, that is a bug — tell me.

---

## The words that matter most

**Edge** — a real, repeatable reason a strategy makes money. Without edge, everything else is
decoration. Most strategies have no edge; they just got lucky in the test.

**Friction** — everything you pay to trade: brokerage, taxes, fees, and slippage. Charged *per
trade*, win or lose. **The single most important idea in this project** — see the User Guide, §3.

**Backtest** — running a strategy on old price data to see what it *would have* done. Useful, but
easy to fool yourself with. Every "amazing" backtest in V1 and V2 was a bug or luck.

**R-multiple (or "R")** — how much you made compared to how much you risked. If you risk ₹200 and
make ₹400, that is **2R**. If you lose the ₹200, that is **−1R**. We rank strategies by average R
instead of by profit %, because profit % lies when the time periods differ.

**avgR** — the average R across all trades. This is **the honest scoreboard**. Above 0 means the
strategy made money relative to risk. V2 computed this correctly and then threw it away for a year.

---

## Money and risk

**Slot** — one funded position. You put **₹10,000** into a slot when you turn it on. This is your
model, and the whole system is built around it.

**Leverage** — borrowing from the broker to buy more than your cash. Intraday you get **5×**: ₹10,000
of yours controls ₹50,000 of stock. It multiplies gains *and* losses.

**Risk cap (2%)** — never risk more than ₹200 (2% of ₹10,000) on one trade. This decides how many
shares you buy: fewer shares if the stop is far away.

**Stop loss** — the price where you admit you were wrong and get out. It defines your risk.

**Notional** — the full value of the position (shares × price), as opposed to the cash you put in.

**Intraday** — buy and sell the same day. Uses 5× leverage. No overnight risk. **High friction
because it trades often.**

**Delivery (or CNC)** — you actually own the shares overnight. No leverage. Cheaper per trade but you
pay the ₹14.75 DP charge when selling.

**DP charge** — a **flat ₹14.75** every time you sell delivery shares. Flat is the problem: it is
0.015% of a ₹95,000 position but **0.5% of a ₹3,000 one**. Small positions get eaten alive by it.

**Drawdown** — how far you fell from your best point. "30% drawdown" means you were down 30% from the
peak. This is what actually makes people quit.

---

## Types of strategy

**Time-series strategy** — asks *"is THIS stock a buy right now?"*, one stock at a time. All 31 of
V1/V2's strategies were this type.

**Cross-sectional strategy** — asks *"which 5 of these 60 stocks are best right now?"* Ranks them all
and holds the winners. **Never tested in V1 or V2**, and it is the type with real evidence.

**Momentum** — buy what has been going up over the last year. The most studied strategy in finance.
Trades rarely, so friction is small (**~2.8%/yr** — measured; run `make friction`).

**PEAD (post-earnings drift)** — buy stocks that surprise everyone with good results, and hold for a
month or two, because the price keeps drifting up. Needs earnings data we do not currently have.

**Rebalance** — the moment you re-rank everything and swap your holdings. Monthly or quarterly.

---

## How we avoid fooling ourselves

**Lookahead (or lookahead bias)** — accidentally using information you could not have had at the
time. V1 bought at the *same candle's closing price* that produced the signal — impossible in real
life, and it made V1's results look far better than reality.

**Survivorship bias** — testing on a list of stocks chosen *today*. Today's popular stocks are
popular partly *because they went up*, so testing on them shows fake profit. **The biggest risk to
this project right now.**

**Multiple testing** — if you test 1,860 combinations, about 93 will look like winners by pure luck
even if all are worthless. V2 tested exactly 1,860 and had no protection. This is why its "winners"
were noise.

**Deflated Sharpe Ratio (DSR)** — the maths that corrects for the above. It asks: "given you tried
this many times, is your best result still impressive?" Usually the answer is no.

**Walk-forward / out-of-sample** — test on data the strategy has never seen. A strategy that only
works on data it was tuned on is worthless.

**Overfitting** — tuning a strategy until it perfectly explains the past, which guarantees it fails
in the future. Like memorising last year's exam paper.

**Attribution ladder** — our best tool. Change **one thing at a time** and measure the effect of each
change separately, so you know *exactly* what caused a difference instead of guessing. It caught a
bug in hours that would otherwise have cost months.

**Parity gate** — proof that our new engine reproduces the old one's numbers *exactly* before we
change anything. Without it, "the new system says something different" is meaningless — you cannot
tell a fix from a bug.

---

## Practical / technical

**Sharpe ratio** — return divided by how bumpy the ride was. Higher is better. ~1.0 is good, and most
claims above 2.0 are a bug.

**Cell / pair** — one (stock × strategy) combination, e.g. "RELIANCE × Momentum". V2 called these
cells and funded each with ₹10,000.

**OHLCV** — Open, High, Low, Close, Volume — the five numbers describing one candle.

**Corporate action** — a split, bonus, or demerger that changes the share price without anyone losing
money. If unhandled, the price history shows a fake crash. **3 of our 60 stocks have this problem
right now** (VEDL, TMPV, TRENT).

**Tick** — the smallest price step on NSE, usually ₹0.05. You cannot slip less than one tick — V2's
cost model assumed you could, which was physically impossible.

**TOTP** — the 6-digit rotating code (like Google Authenticator). V1 generates these itself in ~90
lines of code, which is how it solved the 24-hour Dhan token problem with no manual input.

**NIFTYBEES** — an index fund that returns ~12%/year for free. **Our benchmark.** If we cannot beat
it after costs, we should not be doing this at all.
