# Strategies

Last updated 2026-11-19. 28 strategies are registered (`apps/engine/strategies/__init__.py`):
11 intraday and 17 swing. This page says what each one trades, what the evidence says about
it, and its status. Rules shared by every strategy are in [architecture.md](architecture.md).

## How to read the numbers

- **R** is the result of a trade divided by the rupees it risked. +1R means it made what it
  risked; −1R means it lost its full risk. An average above 0 after costs is the only thing
  that matters over many trades.
- **Backtest avg R** is from the corrected engine on all 60 stocks, after costs and
  slippage, with the cost rule on (a trade is skipped when costs are more than 25% of its
  risk). Intraday covers about 9 months of candles; swing about 5.5 years. Data:
  `docs/agent-reports/data/2026-11-19-backtest-all-gate-0.25.csv`. Re-run it any time with
  `python tools/backtest_all.py --out <file>` inside the engine container (read-only).
- **Live** is the paper track record up to 2026-11-19. v1 results are *before* costs and at a
  much larger position size, so they flatter. v2 results are after costs.

## What the evidence says, plainly

1. **No intraday strategy shows a reliable edge after costs** at ₹10,000 per cell. Across 60
   stocks every one is negative on average. On the most volatile stocks (MCX, OLAELEC, IFCI,
   KAYNES) the best four are close to break-even.
2. **Costs decide intraday.** A round trip costs about 0.2% of the position at this size. A
   0.3% stop means two thirds of the risk is gone before the trade starts. v1's good-looking
   intraday results came from booking no costs at all.
3. **Four swing strategies are positive in both halves of 5.5 years**: Golden_Cross,
   EMA_10_50_Cross, Bollinger_Mean_Reversion and MACD_Stoch_Confluence. This backtest is
   flattered: the 60 stocks were chosen in 2026 for being liquid today, which favours stocks
   that went up. All swing strategies lost in live paper trading during the Aug–Oct 2026 fall.
4. **A single cell's backtest is not evidence.** Of 686 cells with 30 or more trades, 7 pass
   "average above 0.1R and positive in both halves", about what chance alone would give.
   Decisions are made at strategy level and on live results, not per cell from a backtest.
5. **The two apps' live results and this backtest agree where v2 booked costs**: the v2 cells
   that won live (KAYNES·RVOL_ORB, ATGL·VWAP_MACD_RSI, OLAELEC·VWAP_MACD_RSI) are also
   positive here.

## Is any of it more than luck?

Testing 28 strategies at once means some will look good by chance. The backtest tool now
corrects for that (`apps/engine/research_stats.py`); the run of 2026-11-19 with tick-based
slippage is in `docs/agent-reports/data/2026-11-19-backtest-strategies-luck-corrected.csv`.

| Strategy | Trades | Avg R | Chance of this by luck, corrected for 28 tries | Stricter test (needs above 0.95) |
|---|---|---|---|---|
| MTF_Alignment | 796 | +0.27 | under 0.1% | 0.00 |
| Golden_Cross | 138 | +0.27 | 7.4% | 0.21 |
| EMA_10_50_Cross | 717 | +0.14 | 7.4% | 0.00 |
| Every other strategy | | | above 39% | 0.00 to 0.22 |

- The first test (false-discovery control at 10%) passes the three long-term trend
  strategies. The stricter test (deflated Sharpe, which asks whether the best result beats
  what the best of 28 lucky tries would show) passes none. The tool only says a strategy
  "stands out" when both agree, so its verdict is **none**.
- Read this as: the three long-term trend strategies are the only ones worth watching
  closely in paper trading, not as proof. Their backtest is also flattered by the stock list
  (today's liquid stocks) and they lost in live paper trading while the market fell.
- No intraday strategy comes close: every one has a negative average after costs.

Every strategy tested is added to `docs/agent-reports/data/trials-ledger.jsonl`, so the
count of tries used by the stricter test can only grow.

## Intraday (positions closed by 15:15, shorts allowed)

All intraday cells are limited to 2 entries a day with a 30 minute wait after an exit.
Exits: book 35% at half-way to target and move the stop to break-even, book 35% at
three-quarters and trail the stop, exit the rest on a reversal or at 15:15.

| Strategy | Candle | Trades when | Stop | Backtest avg R | Live | Status |
|---|---|---|---|---|---|---|
| RVOL_ORB | 15m | First close outside the day's first candle, with volume above 1.5× normal. One per day | Other side of the first candle | −0.11 | v1 69 trades +0.31R (no costs); v2 32 trades +0.36R | Testing |
| VWAP_MACD_RSI | 15m | Price above VWAP, RSI above 60, MACD histogram turns positive (mirror for shorts) | Candle low − 0.5% | −0.12 | v1 34 trades +0.24R (no costs); v2 65 trades +0.44R | Testing |
| 15m_ORB | 15m | First close outside the day's first candle. One per day | Middle of the first candle | −0.12 | v1 380 trades +0.04R (no costs) | Testing |
| Inside_Bar | 15m | Close beyond the "mother" candle after an inside candle | Inside candle's low/high | −0.13 | v1 73 trades +0.40R (no costs) | Testing |
| Gap_And_Go | 5m | Day opens with a 0.5% gap that still holds at 09:30 | Low/high of the day so far | −0.14 | None: before the 2026-11 fix it could not fire live | Testing (fixed) |
| PDH_PDL_Breakout | 5m | Close crosses the previous day's high or low | Candle low/high ∓ 0.2% | −0.15 | v1 222 trades +0.41R (no costs) | Testing |
| SMC_FVG | 15m | A three-candle price gap appears (it enters as the gap forms; it does not wait for a pullback, whatever the name suggests) | Far edge of the gap ∓ 0.2% | −0.15 | v1 68 trades +0.81R (no costs) | Testing |
| EMA_RSI | 5m | EMA 9 crosses EMA 15 with RSI on the same side of 50 | Five-candle swing low/high | −0.15 | v1 583 trades +0.13R (no costs) | Testing |
| CPR_Breakout | 5m | Close crosses the top or bottom of the previous day's pivot range | Other side of the range | −0.16 | v1 361 trades +0.33R (no costs); v2 16 trades +0.21R | Testing |
| BB_Mean_Reversion_Intraday | 15m | Price dips outside a Bollinger band and closes back inside | Candle low/high ∓ 0.2% | −0.20 | None | Testing |
| MACD_Zero | 15m | MACD crosses its signal line while both are on the far side of zero | 1 × ATR | −0.26 | v1 314 trades +0.30R (no costs) | Testing |

## Swing (daily candles, buy only, held for days to weeks)

Target is 3R (short swing), 4R (mid swing) or 5R (long positional) from the signal candle's
close, with an ATR trailing stop. No strategy checks the overall market before buying yet;
that is Phase 4.

| Strategy | Hold | Trades when | Backtest avg R | First half / second half | Live | Status |
|---|---|---|---|---|---|---|
| Golden_Cross | Long | 50-day average crosses above the 200-day | +0.29 | +0.32 / +0.23 | v2 4 trades −0.75R | Testing |
| MTF_Alignment | Long | Above the 50-week average and a new 20-day high | +0.26 | +0.48 / +0.06 | None: it crashed in backtest and never fired live before the 2026-11 fix | Testing (fixed) |
| EMA_10_50_Cross | Long | EMA 10 crosses above EMA 50 | +0.12 | +0.14 / +0.11 | v2 7 trades −0.88R | Testing |
| Volume_Climax | Mid | Reclaims the high of a record-volume down day within 5 days | +0.16 | too few trades (20) | None | Testing |
| Bollinger_Mean_Reversion | Mid | Close below the lower band with RSI under 30 | +0.13 | +0.16 / +0.10 | v2 7 trades −0.97R | Testing |
| MACD_Stoch_Confluence | Mid | MACD above zero and stochastic turns up from below 40 | +0.10 | +0.15 / +0.05 | v1 4 trades +0.39R; v2 8 trades −1.06R | Testing |
| RSI_Divergence | Mid | Lower low in price with a higher low in RSI near the 200-day low | +0.02 | −0.28 / +0.26 | v1 4 trades +0.35R | Testing (fixed) |
| Channel_Oscillation | Mid | Bounce off the bottom of a flat 60-day range | −0.02 | +0.14 / −0.15 | v1 17 trades −0.38R; v2 23 trades −0.33R | Testing |
| Fibonacci_Golden_Zone | Mid | Pullback into the 50–61.8% zone of a 30-day up-move | −0.04 | +0.13 / −0.21 | v1 15 trades −0.16R; v2 27 trades −0.21R | Testing (fixed) |
| BB_Squeeze | Mid | Close above the upper band coming out of a squeeze | −0.06 | +0.09 / −0.20 | v2 1 trade | Testing (fixed) |
| VCP | Mid | New 20-day high on high volume after quiet, tight trading | −0.11 | +0.05 / −0.24 | v2 2 trades | Testing |
| Episodic_Pivot | Mid | Breaks above the range formed after a 5% gap up | −0.22 | −0.34 / −0.11 | v2 1 trade | Testing |
| SuperTrend_EMA | Short | EMA 5 crosses above EMA 20 with Supertrend up | −0.04 | +0.05 / −0.11 | v2 4 trades −0.62R | Testing |
| EMA200_MACD | Short | MACD crosses up while price is above the 200-day EMA | −0.06 | +0.04 / −0.14 | v1 15 trades −0.10R; v2 8 trades −1.04R | Testing |
| SMA44_Pullback | Short | Pullback to the 44-day average in an uptrend | −0.06 | +0.06 / −0.16 | v1 15 trades −0.25R; v2 12 trades −0.33R | Testing |
| Break_And_Retest | Short | Retest of a broken 60-day high within 20 days | −0.07 | −0.06 / −0.07 | v2 5 trades −0.10R | Testing |
| DMA20_Pullback | Short | Pullback to the 20-day average in an uptrend | −0.08 | 0.00 / −0.17 | v1 3 trades; v2 1 trade | Testing |

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

- All 27 daily moves above 20% in stored history have been reviewed
  (`config/known_price_actions.json`). No stock is flagged: KAYNES's fall of
  2026-05-14 was a real move after results, and TRENT's step is its 1-for-2 bonus issue, which
  the data source carried back only to 2026-01-01 and the engine now scales out.
- The intraday history is about 9 months. That is one market period, mostly falling.
- Slippage is the larger of one ₹0.05 tick and 5 basis points per share and side. That is a
  cautious guess, not a measurement; real fills will tell. At 2 basis points the intraday
  average was −0.28R (no cost rule) instead of −0.35R: better, still negative.
- The 4R target override on the two mean-reversion swing strategies has not been re-measured.
