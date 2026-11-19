# Intraday Strategies

## Trend-Following & Momentum (High Volatility)

These setups thrive in the first two hours of the session when institutional volume and directional conviction are highest.

- **1. 15-Minute Opening Range Breakout (ORB):** Mark the high and low of the first 15 minutes. Wait for a 5-minute candle to close completely outside this range with volume at least 1.5x the morning average. Enter in the direction of the breakout.
- **2. VWAP + MACD/RSI Confluence:** The algorithmic standard. Go long when price is above VWAP, RSI crosses **60**, and MACD shows a bullish crossover. Short when price is below VWAP, RSI drops under **40**, and MACD crosses bearishly.
- **3. Gap and Go:** Target counters opening with a significant gap due to news or earnings. If the asset sustains the gap in the first 5 minutes without filling it, enter in the direction of the gap. This is highly effective on high-beta defense sector ETFs or heavyweights during active market cycles.
- **4. Bull/Bear Flag Continuation:** Look for a sharp, near-vertical price surge (the pole) followed by a tight, sloping consolidation (the flag). Enter when the price breaks out of the flag formation, riding the secondary wave of the trend.

## Structural & Pullback Setups

When a trend is established, chasing breakouts becomes mathematically risky. These strategies allow you to enter at logical, low-risk pivot points.

- **5. Pullback to the 20 EMA:** Identify a strong morning trend. Instead of chasing, wait for the price to retrace to the 20-period Exponential Moving Average (EMA). Enter on a rejection candlestick off the EMA to rejoin the trend. This works exceptionally well on liquid commodities like gold or copper when they establish a clear intraday trajectory.
- **6. Central Pivot Range (CPR):** A math-heavy three-line indicator calculated from the previous day's high, low, and close. A mathematically narrow CPR algorithmically predicts a trending breakout day, while a wide CPR suggests a sideways, range-bound session.
- **7. Previous Day High/Low (PDH/PDL) Breakout:** Institutional stop-losses heavily cluster around the previous day's extremes. A high-volume break of the PDH or PDL often triggers a cascade of automated orders, driving immense directional movement.

## Range-Bound & Mean Reversion

These are designed for the mid-day chop (11:30 AM to 1:30 PM) when volume dries up and prices oscillate between defined boundaries.

- **8. Bollinger Band Mean Reversion:** When price pierces the upper or lower Bollinger Band (set at 2 standard deviations) and prints a reversal candlestick, enter a trade targeting the 20 SMA midline. This setup assumes the extreme price action is exhausted.
- **9. Volume Profile Point of Control (POC):** Plot the intraday Volume Profile. The POC is the exact price level with the highest traded volume. In a ranging market, price reliably gravitates back to the POC, acting as a massive gravitational center for mean-reverting trades.
- **10. Order Book Scalping (Tape Reading):** Requires Level 2 market data API feeds. Monitor the bid-ask spread, order flow velocity, and resting liquidity to capture rapid 1-2 point moves. This is purely quantitative, reacting to sudden block orders rather than chart patterns.
