# Strategies

Last updated 2026-11-19. 28 strategies are registered (`apps/engine/strategies/__init__.py`):
11 intraday and 17 swing. This page says what each one trades, what the evidence says about
it, and its status. Rules shared by every strategy are in [architecture.md](architecture.md).

## What is on the roster

Since the evening of 2026-11-19 the roster is 100 cells, picked per cell from the backtest
(the owner's choice, "strict per cell"). A cell is on it when its backtest average is above
+0.10R, it is positive in both halves of its history and it has enough trades (30 intraday,
10 swing). Intraday cells also need a profit factor of 1.3; swing cells must belong to a
strategy that passes the first luck test.

- **Swing, 93 cells** on 38 stocks: MACD_Stoch_Confluence 17, SMA44_Pullback 17,
  MTF_Alignment 14, Break_And_Retest 13, EMA_10_50_Cross 13, EMA200_MACD 10,
  SuperTrend_EMA 7, Bollinger_Mean_Reversion 2. Golden_Cross has the best average but
  trades about twice per stock in five years, so no single cell reaches 10 trades.
- **Intraday, 7 cells**: VWAP_MACD_RSI on ADANIENT, ATGL, TMPV and VEDL; RVOL_ORB on 5PAISA;
  Inside_Bar on COFORGE; CPR_Breakout on IFCI. Seven of 645 intraday cells passing is about
  what chance alone would give, so these are being watched, not trusted.

The list is `infra/scripts/seed-starting-roster.sql`. The strategies below that are not on
the roster stay in the code and can be backtested; they are not paper trading. A good
backtest row puts a cell on the roster; only its own paper trades keep it there.

## How to read the numbers

- **R** is the result of a trade divided by the rupees it risked. +1R means it made what it
  risked; −1R means it lost its full risk. An average above 0 after costs is the only thing
  that matters over many trades.
- **Backtest avg R** is from engine `2026.11.19-parity2` on 61 stocks, after costs and
  slippage, with the cost rule on (a trade is skipped when costs are more than 25% of its
  risk) and with the same entry rules the live scanner applies. Intraday covers about 9
  months of candles; swing about 5.5 years. Data:
  `docs/agent-reports/data/2026-11-19-backtest-all-parity2.csv`. Re-run it any time **inside
  the engine container** with `python tools/backtest_all.py --out <file>` (read-only).
- **Live** is the paper track record up to 2026-11-19. Results from the first app are *before* costs and at a
  much larger position size, so they flatter. Results from the second app are after costs.

## Correction, 2026-11-19 (evening)

The swing figures first published on this page that morning were wrong. They came from a
backtest run outside the live containers, where a time-stop (sell a swing after 10, 20 or 40
days) was switched on by a code default. The live system has had that time-stop off since
July 2026. Run with the live rules, swing strategies hold their trades longer and do
clearly better: for example SMA44_Pullback went from 1,686 trades at −0.06R to 913 trades
at +0.15R. The default is fixed, so the two can no longer differ. The intraday figures
changed only slightly (the backtest no longer takes late-day and before-09:30 trades that
the live scanner never takes).

## What the evidence says, plainly

1. **No intraday strategy shows a reliable edge after costs** at ₹10,000 per cell. Across 61
   stocks every one is negative on average (−0.10R to −0.23R). On the four most volatile
   stocks (MCX, OLAELEC, IFCI, KAYNES) the best four are at break-even (+0.02R to +0.04R).
2. **Costs decide intraday.** A round trip costs about 0.2% of the position at this size. A
   0.3% stop means two thirds of the risk is gone before the trade starts. The first app's
   good-looking intraday results came from booking no costs at all.
3. **Swing looks better than first reported.** 14 of the 17 swing strategies have a positive
   average, and six are positive in both halves of 5.5 years: Golden_Cross, MTF_Alignment,
   EMA_10_50_Cross, SuperTrend_EMA, Break_And_Retest and Bollinger_Mean_Reversion. Treat
   this with care, for three reasons. The 61 stocks were chosen in 2026 for being liquid
   today, which favours stocks that went up, and a rule that holds winners for months
   gains most from that. Most of these strategies did better in the first half than the
   second. And every swing strategy lost in live paper trading during the Aug–Oct 2026
   fall, on a handful of trades each.
4. **A single cell's backtest is not evidence.** Of 381 cells with 30 or more trades, 10 pass
   "average above 0.1R and positive in both halves", about what chance alone would give.
   Decisions are made at strategy level and on live results, not per cell from a backtest.
5. **Live results and this backtest agree where costs were booked**: the cells that won live
   in the second app (KAYNES·RVOL_ORB, ATGL·VWAP_MACD_RSI, OLAELEC·VWAP_MACD_RSI) are also
   positive here.

## Is any of it more than luck?

Testing 28 strategies at once means some will look good by chance. The backtest tool
corrects for that (`apps/engine/research_stats.py`); the figures below are from
`docs/agent-reports/data/2026-11-19-backtest-strategies-parity2.csv`.

| Strategy | Trades | Avg R | Chance of this by luck, corrected for 28 tries | Stricter test (needs above 0.95) |
|---|---|---|---|---|
| Golden_Cross | 140 | +0.86 | under 0.1% | 0.53 |
| MTF_Alignment | 578 | +0.58 | under 0.1% | 0.01 |
| EMA_10_50_Cross | 633 | +0.40 | under 0.1% | 0.00 |
| SuperTrend_EMA | 518 | +0.27 | under 0.1% | 0.00 |
| EMA200_MACD | 676 | +0.20 | 0.1% | 0.00 |
| SMA44_Pullback | 913 | +0.15 | 0.8% | 0.00 |
| Break_And_Retest | 651 | +0.17 | 1.8% | 0.00 |
| MACD_Stoch_Confluence | 693 | +0.15 | 7.1% | 0.00 |
| Every other strategy | | | above 11% | 0.00 to 0.17 |

- The first test (false-discovery control at 10%) passes eight swing strategies. The
  stricter test (deflated Sharpe, which asks whether the best result beats what the best of
  all lucky tries would show) passes none: the highest is Golden_Cross at 0.53. The tool
  only says a strategy "stands out" when both agree, so its verdict is still **none**.
- Read this as: the trend-following swing strategies, Golden_Cross first, are the ones
  worth watching closely in paper trading. It is not proof. Their backtest is flattered by
  the stock list (today's liquid stocks) and they lost in live paper trading while the
  market fell.
- No intraday strategy comes close: every one has a negative average after costs.

Every strategy tested is added to `docs/agent-reports/data/trials-ledger.jsonl`, so the
count of tries used by the stricter test can only grow. It holds 84 tries: the 28 strategies
on three engine versions. The stricter-test figures above count 28; counted against all
84 they can only be lower.

## Intraday (positions closed by 15:15, shorts allowed)

All intraday cells are limited to 2 entries a day with a 30 minute wait after an exit.
Exits: book 35% at half-way to target and move the stop to break-even, book 35% at
three-quarters and trail the stop, exit the rest on a reversal or at 15:15.

| Strategy | Candle | Trades when | Stop | Backtest avg R | Live | Status |
|---|---|---|---|---|---|---|
| VWAP_MACD_RSI | 15m | Price above VWAP, RSI above 60, MACD histogram turns positive (mirror for shorts) | Candle low − 0.5% | −0.10 | the first app 34 trades +0.24R (no costs); the second app 65 trades +0.44R | Testing |
| RVOL_ORB | 15m | First close outside the day's first candle, with volume above 1.5× normal. One per day | Other side of the first candle | −0.11 | the first app 69 trades +0.31R (no costs); the second app 32 trades +0.36R | Testing |
| Inside_Bar | 15m | Close beyond the "mother" candle after an inside candle | Inside candle's low/high | −0.11 | the first app 73 trades +0.40R (no costs) | Testing |
| 15m_ORB | 15m | First close outside the day's first candle. One per day | Middle of the first candle | −0.12 | the first app 380 trades +0.04R (no costs) | Testing |
| SMC_FVG | 15m | A three-candle price gap appears (it enters as the gap forms; it does not wait for a pullback, whatever the name suggests) | Far edge of the gap ∓ 0.2% | −0.14 | the first app 68 trades +0.81R (no costs) | Testing |
| EMA_RSI | 5m | EMA 9 crosses EMA 15 with RSI on the same side of 50 | Five-candle swing low/high | −0.14 | the first app 583 trades +0.13R (no costs) | Testing |
| Gap_And_Go | 5m | Day opens with a 0.5% gap that still holds at 09:30 | Low/high of the day so far | −0.15 | None: before the 2026-11 fix it could not fire live | Testing (fixed) |
| PDH_PDL_Breakout | 5m | Close crosses the previous day's high or low | Candle low/high ∓ 0.2% | −0.17 | the first app 222 trades +0.41R (no costs) | Testing |
| CPR_Breakout | 5m | Close crosses the top or bottom of the previous day's pivot range | Other side of the range | −0.18 | the first app 361 trades +0.33R (no costs); the second app 16 trades +0.21R | Testing |
| BB_Mean_Reversion_Intraday | 15m | Price dips outside a Bollinger band and closes back inside | Candle low/high ∓ 0.2% | −0.19 | None | Testing |
| MACD_Zero | 15m | MACD crosses its signal line while both are on the far side of zero | 1 × ATR | −0.23 | the first app 314 trades +0.30R (no costs) | Testing |

## Swing (daily candles, buy only, held for days to weeks)

Target is 3R (short swing), 4R (mid swing) or 5R (long positional) from the signal candle's
close, with an ATR trailing stop. No strategy checks the overall market before buying yet;
that is Phase 4.

| Strategy | Hold | Trades when | Backtest avg R | First half / second half | Live | Status |
|---|---|---|---|---|---|---|
| Golden_Cross | Long | 50-day average crosses above the 200-day | +0.86 | +0.41 / +1.04 | the second app 4 trades −0.75R | Testing |
| MTF_Alignment | Long | Above the 50-week average and a new 20-day high | +0.58 | +1.01 / +0.19 | None: it crashed in backtest and never fired live before the 2026-11 fix | Testing (fixed) |
| EMA_10_50_Cross | Long | EMA 10 crosses above EMA 50 | +0.40 | +0.54 / +0.29 | the second app 7 trades −0.88R | Testing |
| SuperTrend_EMA | Short | EMA 5 crosses above EMA 20 with Supertrend up | +0.27 | +0.40 / +0.16 | the second app 4 trades −0.62R | Testing |
| Volume_Climax | Mid | Reclaims the high of a record-volume down day within 5 days | +0.23 | too few trades (19) | None | Testing |
| EMA200_MACD | Short | MACD crosses up while price is above the 200-day EMA | +0.20 | +0.51 / −0.07 | the first app 15 trades −0.10R; the second app 8 trades −1.04R | Testing |
| RSI_Divergence | Mid | Lower low in price with a higher low in RSI near the 200-day low | +0.19 | −0.03 / +0.41 | the first app 4 trades +0.35R | Testing (fixed) |
| Break_And_Retest | Short | Retest of a broken 60-day high within 20 days | +0.17 | +0.21 / +0.12 | the second app 5 trades −0.10R | Testing |
| Bollinger_Mean_Reversion | Mid | Close below the lower band with RSI under 30 | +0.16 | +0.26 / +0.08 | the second app 7 trades −0.97R | Testing |
| SMA44_Pullback | Short | Pullback to the 44-day average in an uptrend | +0.15 | +0.44 / −0.12 | the first app 15 trades −0.25R; the second app 12 trades −0.33R | Testing |
| MACD_Stoch_Confluence | Mid | MACD above zero and stochastic turns up from below 40 | +0.15 | +0.31 / −0.01 | the first app 4 trades +0.39R; the second app 8 trades −1.06R | Testing |
| Fibonacci_Golden_Zone | Mid | Pullback into the 50–61.8% zone of a 30-day up-move | +0.04 | +0.29 / −0.19 | the first app 15 trades −0.16R; the second app 27 trades −0.21R | Testing (fixed) |
| Channel_Oscillation | Mid | Bounce off the bottom of a flat 60-day range | +0.04 | +0.20 / −0.11 | the first app 17 trades −0.38R; the second app 23 trades −0.33R | Testing |
| VCP | Mid | New 20-day high on high volume after quiet, tight trading | +0.01 | +0.19 / −0.19 | the second app 2 trades | Testing |
| DMA20_Pullback | Short | Pullback to the 20-day average in an uptrend | −0.02 | +0.10 / −0.14 | the first app 3 trades; the second app 1 trade | Testing |
| BB_Squeeze | Mid | Close above the upper band coming out of a squeeze | −0.10 | +0.02 / −0.19 | the second app 1 trade | Testing (fixed) |
| Episodic_Pivot | Mid | Breaks above the range formed after a 5% gap up | −0.26 | −0.46 / −0.17 | the second app 1 trade | Testing |

## Retired (2026-11)

| Strategy | Why |
|---|---|
| EMA20_Pullback | 1,557 live trades, 33% wins, −₹6.56 lakh. It fired on every candle its condition held, so it re-entered about three times per stock per day |
| Volume_Profile_POC | 190 live trades, 32% wins, −₹1.07 lakh. Its "point of control" was the price of the highest-volume candle, not a volume profile, and it went stale |
| VWAP_Supertrend | Negative in both apps (130 and 109 trades). It re-fired on every VWAP re-cross with a target rarely reachable before 15:15 |

## Fixed in 2026-11

| Strategy | Fault | Fix |
|---|---|---|
| Gap_And_Go | Signalled on the 09:15 candle, which the live scanner cannot see | Decides on the 09:25 candle |
| Fibonacci_Golden_Zone | Did not check whether the swing was up or down | Requires the high to come after the low |
| BB_Squeeze | Measured the squeeze on the breakout candle, which itself widens the bands | Reads the squeeze from the 5 candles before |
| RSI_Divergence | Fired on every green candle while the set-up held | Fires once |
| MTF_Alignment | Crashed on stored history and with under 50 weeks of data | Works on any index; returns no signal when data is short |

## Known limits of these numbers

- A backtest must be run inside the engine container (or with the same settings). The
  morning figures of 2026-11-19 were wrong because one was not; see the correction above.
- With the time-stop off, a swing trade ends only at its stop, its trailing stop or its
  target, and a trade still open at the end of the data is valued at the last close.

- All 27 daily moves above 20% in stored history have been reviewed
  (`config/known_price_actions.json`). No stock is flagged: KAYNES's fall of
  2026-05-14 was a real move after results, and TRENT's step is its 1-for-2 bonus issue, which
  the data source carried back only to 2026-01-01 and the engine now scales out.
- The intraday history is about 9 months. That is one market period, mostly falling.
- Slippage is the larger of one ₹0.05 tick and 5 basis points per share and side. That is a
  cautious guess, not a measurement; real fills will tell. At 2 basis points the intraday
  average was −0.28R (no cost rule) instead of −0.35R: better, still negative.
- The 4R target override on the two mean-reversion swing strategies has not been re-measured.
