# Smart Trading: user guide

This guide is for the owner. It explains what the app does, what each screen is for and
how to read the numbers. No trading or coding background is assumed.

## 1. What the app is

Smart Trading tests trading strategies with pretend money ("paper trading") on Indian
stocks. Its job is to answer one question honestly: **which strategy, on which stock,
keeps making money after all costs?**

It does not promise profit. A computer cannot create an edge. It can only find one that
exists, or show that there is none. Expect most of what is tested to fail. That is the
app working, not the app broken.

## 2. Why earlier backtests looked good and live trading lost

Five reasons were found and fixed in the app:

1. **Picking winners from a huge list.** About 1,800 stock-and-strategy pairs were
   backtested and the best were chosen. With that many tries, many look good by luck.
   In the old data the backtest rank did not predict the live result at all.
2. **Costs.** Brokerage, taxes and slippage are small per trade and large over hundreds
   of trades. On a ₹10,000 cell with a tight stop, costs can eat a third of the risk
   before the trade starts.
3. **Fills that were too kind.** The backtest assumed you always got your stop price.
   When a stock opens below the stop, the real fill is worse.
4. **No limit on repeat trades.** Live, a strategy could re-enter the same stock again
   and again in one bad day.
5. **Trading against the market.** Trades in the market's direction did better than
   trades against it.

What changed: every number is after costs, fills are pessimistic, repeat entries are
limited, a trade is skipped when its costs are more than a quarter of its risk, and the
backtest is treated as a first filter only. **The live paper record decides.**

## 3. Words used in the app

| Word | Meaning |
|---|---|
| **Cell** | One stock with one strategy, for example ATGL with VWAP_MACD_RSI. Each cell is tested on its own. |
| **Fund** | Each cell starts with ₹10,000 of pretend money. Profits and losses stay in that cell. |
| **Leverage** | Intraday trades may hold shares worth up to 5 times the fund. Swing trades use the fund only. |
| **Stop** | The price at which a losing trade is closed. |
| **Target** | The price at which a winning trade is closed. |
| **Risk** | The rupees lost if the stop is hit. No trade may risk more than 2% of what it may hold: ₹200 for a swing trade (2% of ₹10,000) and ₹1,000 for an intraday trade (2% of ₹50,000). |
| **R** | The result divided by the risk. +1R: made what it risked. −1R: lost the full risk. An average above 0 over many trades is what matters. |
| **After costs** | Brokerage, taxes and slippage are already taken off. Every figure in the app is after costs. |
| **Profit factor** | Total won divided by total lost. Above 1 is profitable; 1.3 or more is the bar for Proven. |
| **Intraday** | Opened and closed the same day. Everything is closed by 15:15. |
| **Swing** | Held for days or weeks on daily candles. Buy only. |
| **Backtest** | The strategy replayed on past prices. A promise, not a result. |

## 4. The status of a cell

The app sets the status itself from the cell's own closed paper trades.

| Status | Meaning | Rule |
|---|---|---|
| **Testing** | Still collecting evidence | Where every cell starts |
| **Paused** | It kept losing | Last 20 trades average below −0.15R, or only ₹5,000 is left of the cell's ₹10,000 fund |
| **Proven** | It has earned trust | 40 or more trades, average above +0.10R, profit factor 1.3 or more, and positive in both the first and second half of its history |

A paused cell keeps paper trading so it can recover. Those trades go into the **test
book** and are not counted in the main results. It returns to Testing after 20 new
trades that average above +0.05R, provided its fund is back above ₹5,000.

- **Main book:** trades from cells that were Testing or Proven when the trade opened.
  This is the result to judge the app by.
- **Test book:** trades from cells that were Paused. Kept apart on purpose.

Proven takes time. At a few trades a week, a cell needs months to reach 40 trades.

## 4b. What it takes to go live (paper)

One rule decides whether a stock and strategy pair is good enough to start paper trading.
On its backtest, after costs, it needs all of:

1. an average per trade above +0.10R;
2. a profit in both halves of its history, so it is not one lucky stretch;
3. enough trades: 30 for intraday, 10 for swing;
4. a profit factor of 1.5 or more (total won ÷ total lost);
5. a profit at least twice its worst drawdown;
6. a total return of at least 10% of the fund;
7. for swing: a strategy that passes the luck check.

The same rule is used by Auto-select, by the roster, and by the Set Live button, which
tells you what a row misses and asks before putting it live anyway. Each strategy's result
page lists the stocks that meet the rule first.

Passing the rule only earns a place. From then on the pair's own paper trades decide
(section 4).

## 4c. Which stocks are tested

- **Swing:** the NIFTY 500, minus stocks that trade too little each day for a backtest
  price to be believable. Daily prices only.
- **Intraday:** a short list of liquid stocks that move the most in a day, because intraday
  only pays where the move is large against the costs. Only these get 5- and 15-minute
  prices.

Both lists are chosen from measured figures, not by hand. The more stocks are tested, the
more pairs look good by luck alone, so a pair still has to pass the live rule and then
prove itself in paper trading.

The Dashboard opens on the stocks **in use** (on the intraday list, or with a pair on the
roster). "All stocks" and the search box show the rest.

## 5. The screens

**Dashboard.** The stock list with live prices. Click a stock for its chart, its
strategies and an AI research note.

**Live Scanner.** Open trades and new signals as they happen. The second tab lists every
monitored cell with its latest backtest, where a cell can be re-tested or removed.

**Portfolio.** Totals after costs, split into main book and test book, with a line
showing what simply holding NIFTY did over the same days. Below it: the best cells, risk
in use, and the journal of every trade. If a stop has been moved, the planned stop is
shown under it.

**Scorecard.** The most important screen. One row per cell: status and the reason, the
live record, and the live result next to what the backtest promised. A stock with a
price-data problem is marked. The real-money line and switch are here too.

**News** and **Sectors.** Market news and sector write-ups from the AI router. They are
reading material; no trade depends on them.

**Backtesting.** Run a strategy on past prices. At the top, "Is any of it more than
luck?" lists the strategies with a positive average and, for each, the chance that its
result is luck. With many strategies tested together some always look good by chance, so
a good row is a reason to watch a strategy, not proof. It refreshes each trading day
after the close.

**Builder.** Compose a strategy from indicators and backtest it.

**Settings.** Stocks, strategies and app settings.

## 6. Closing a trade yourself

Use **Close** on the Portfolio or Live Scanner page. The app books the live price. If
there is no live price at that moment, it asks you for the price you exited at. It never
closes a trade without a real price.

## 7. Telegram messages

The bot sends:

- an alert when a trade opens, when part of it is booked, when a stop is moved and when
  it closes;
- a **daily summary at 15:45** on trading days;
- on **Fridays**, the week at 15:50 and everything since the start at 15:55.

Summaries are after costs, show the main book and the test book separately, and list the
cells that changed status. Messages can be switched off with `TELEGRAM_ENABLED=false` in
the settings file on work-pc (see the deployment runbook).

## 8. Real money

Real-money trading through Dhan is built in and **switched off**. Nothing can place a
real order today.

When it is turned on, a real order needs two locks:

1. the cell is **Proven**, and
2. you switched that cell on, on the Scorecard page.

A cell that drops out of Proven stops opening new real trades. A real position that is
already open is always managed to its exit, even when entries are off. A daily loss
limit stops new entries for the day. Intraday only.

Read [real-money-trading.md](real-money-trading.md) and
[live-capabilities.md](live-capabilities.md) before turning anything on. The plan is
three to six months of paper trading first.

## 9. Does a good number mean anything?

Three checks before trusting a result:

- **Enough trades.** Under 20 trades a result is noise. Under 40 it is a hint.
- **Both halves positive.** A cell that won early and lost later is not proven.
- **Better than doing nothing.** Compare with the NIFTY line on the Portfolio page.

As of 2026-11-19 the honest backtest says: every intraday strategy loses after costs at
₹10,000 per cell, mostly because costs are large against small stops. Most swing
strategies are positive, six of them in both halves of five years, on a stock list that
flatters them. None passes the strictest luck test yet. See [strategies.md](strategies.md) for the detail.

## 10. A weekly routine

1. Open the **Scorecard**. Look for cells that changed status and read the reason.
2. Open the **Portfolio**. Compare the main book with NIFTY.
3. Read the Friday Telegram summary.
4. Do not switch strategies on a few days of results. Decide on months, not days.

## 11. What the app does not do yet

- It does not switch strategies by market condition. Every trade records the market
  condition at entry so this can be judged later; no trade is blocked by it today.
- It does not trade swing signals with real money.
- It checks open trades about every 100 seconds, so a stop can be noticed after the
  price has moved past it. The loss is then booked at the worse price.
- Prices come from a free source that can be late or briefly unavailable.

## 12. When something looks wrong

| You see | What to do |
|---|---|
| Prices not loading | The price source is slow or down. Wait a few minutes and reload. |
| An AI note says the service is busy | The AI router has no free model right now. Try again later. |
| No Telegram summary after 15:45 | Follow "Check that it is healthy" in [work-pc-deployment.md](work-pc-deployment.md). |
| A stock is marked with a data warning | Its price history has a jump nobody has reviewed. Its results are not reliable until it is. |
| No trades all day | Normal on a quiet day or a market holiday. The scanner only opens trades between 09:30 and 15:00. |
