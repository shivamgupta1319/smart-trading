# Understanding: Zero-Cost Algorithmic Trading Scanner

## What This Platform Does

This platform is a **local algorithmic trading assistant** for Indian stock markets (NSE). It does three things:

1. **Backtests** 10 pre-coded trading strategies on historical OHLCV data for any NSE stock
2. **Assigns** the best-performing strategy to a stock as its "active configuration"
3. **Monitors** active stocks live during market hours and fires real-time alerts to the dashboard when a trade signal is triggered

---

## Indian Stock Market Context

| Fact | Detail |
|---|---|
| Exchange | NSE (National Stock Exchange of India) |
| Market hours | 09:15 – 15:30 IST (Mon–Fri) |
| Pre-market | 09:00 – 09:15 IST (thin liquidity) |
| yfinance suffix | Append `.NS` to ticker (e.g., `RELIANCE.NS`, `TCS.NS`) |
| Historical data | yfinance: 5 years of 1D, 60 days of 5m/15m |
| Live polling | yfinance `.download()` with period="1d" interval="5m" every 60s |
| Currency | INR (Indian Rupee) |

### Important Market Timings for Strategies

- **ORB (Opening Range Breakout)**: The "opening range" is only the **first 15-minute candle** (09:15–09:30). The strategy is only valid if the price breaks that candle's high/low **after** 09:30.
- **VWAP**: Resets every day at market open. Always compute VWAP fresh from 09:15 each day.
- **Intraday strategies**: Positions should notionally be squared off at 15:15 (15 minutes before close) to avoid delivery.

---

## Data Sources

### Historical Data (yfinance)
```python
import yfinance as yf
ticker = yf.Ticker("RELIANCE.NS")
# 5 years daily
hist_1d = ticker.history(period="5y", interval="1d")
# 60 days 15-minute
hist_15m = ticker.history(period="60d", interval="15m")
# 60 days 5-minute
hist_5m = ticker.history(period="60d", interval="5m")
```

### Live Polling (yfinance)
```python
# Every 60 seconds during market hours
live = yf.download("RELIANCE.NS", period="1d", interval="5m", progress=False)
latest_candle = live.iloc[-1]  # Most recent completed candle
```

---

## The 10 Strategies Explained

### Intraday Strategies (5m, 15m timeframes)

#### 1. 15m ORB (Opening Range Breakout)
- **Setup**: Record High and Low of the first candle of the day (09:15–09:30)
- **Entry Long**: Price closes **above** the ORB High
- **Entry Short**: Price closes **below** the ORB Low
- **Stop Loss**: Midpoint of the ORB candle `(ORB_High + ORB_Low) / 2`
- **Target**: 1:2 Risk/Reward — `entry + 2 * (entry - SL)` for longs
- **Time constraint**: Only valid until 14:00 (no late-day entries)

#### 2. VWAP + Supertrend (10, 3)
- **Setup**: Calculate VWAP (cumulative) and Supertrend(10, 3)
- **Entry Long**: Price **closes above VWAP** AND Supertrend is **green (uptrend)**
- **Entry Short**: Price **closes below VWAP** AND Supertrend is **red (downtrend)**
- **Stop Loss**: The Supertrend line value at signal candle
- **Target**: 1:2 RR

#### 3. 9/15 EMA Crossover + RSI Filter
- **Setup**: 9 EMA, 15 EMA, 14-period RSI
- **Entry Long**: 9 EMA crosses **above** 15 EMA AND RSI **> 50**
- **Entry Short**: 9 EMA crosses **below** 15 EMA AND RSI **< 50**
- **Stop Loss**: Previous swing low (long) / previous swing high (short)
- **Lookback for swing**: 5 candles

#### 4. MACD Zero-Line Cross
- **Setup**: MACD(12, 26, 9)
- **Entry Long**: MACD line crosses **above** Signal line AND **both are below 0**
- **Entry Short**: MACD line crosses **below** Signal line AND **both are above 0**
- **Stop Loss**: 1 × ATR(14) below entry candle low
- **Target**: 1:2 RR

#### 5. Inside Bar Breakout
- **Setup**: Identify Inside Bar — current bar's High < previous bar's High AND Low > previous bar's Low
- **Entry Long**: Price closes above **mother bar's High** (previous bar)
- **Entry Short**: Price closes below **mother bar's Low**
- **Stop Loss**: Low of the inside bar (long) / High of the inside bar (short)
- **Target**: 1:2 RR

---

### Swing Strategies (1D timeframe)

#### 6. 44 SMA Pullback
- **Filter**: Price must be above **200 SMA** (uptrend)
- **Entry Long**: Price **touches or dips below 44 SMA** and closes with a **bullish candle** (close > open)
- **Stop Loss**: 1.5 × ATR(14) below the candle's Low
- **Target**: 1:2 RR

#### 7. 200 EMA + MACD Golden Trend
- **Filter**: Price must be above **200 EMA**
- **Entry Long**: MACD has a **bullish crossover** (MACD crosses above Signal)
- **Stop Loss**: 1 × ATR(14) below recent 5-day swing low
- **Target**: 1:2 RR

#### 8. Bollinger Band Squeeze (20, 2)
- **Condition**: Bollinger Band **Bandwidth** (Upper − Lower) / Middle reaches a **6-month low** (120 trading days)
- **Entry Long**: Price **closes above** the Upper Bollinger Band
- **Entry Short**: Price **closes below** the Lower Bollinger Band
- **Stop Loss**: Middle Band (20 SMA)
- **Target**: 1:2 RR

#### 9. RSI Divergence (Bullish)
- **Setup**: Find a **price Lower Low** paired with an **RSI Higher Low** (14-period)
- **Entry Long**: The **first green candle** after the second low is confirmed
- **Stop Loss**: The **exact low** of the pattern (second price low)
- **Target**: 50 EMA value at signal time

#### 10. 50/200 Golden Cross
- **Entry Long**: 50 SMA crosses **above** 200 SMA (Golden Cross)
- **Entry Short**: 50 SMA crosses **below** 200 SMA (Death Cross)
- **Stop Loss**: 1.5 × ATR(14) below the 50 SMA at crossover
- **Target**: 1:2 RR (long-term swing)

---

## Backtest Metrics Explained

| Metric | Formula |
|---|---|
| **Win Rate** | `wins / total_trades × 100` |
| **Total Trades** | Count of all triggered signals in backtest period |
| **Max Drawdown** | Largest peak-to-trough loss in equity curve |
| **Expectancy** | `(Win Rate × Avg Win) − (Loss Rate × Avg Loss)` |

A strategy is considered "good" if:
- Win Rate > 45%
- Expectancy > 0
- Max Drawdown < 20%

---

## Glossary

| Term | Definition |
|---|---|
| **OHLCV** | Open, High, Low, Close, Volume — the standard price bar |
| **ATR** | Average True Range — measures volatility |
| **VWAP** | Volume Weighted Average Price — intraday mean |
| **EMA** | Exponential Moving Average |
| **SMA** | Simple Moving Average |
| **MACD** | Moving Average Convergence Divergence |
| **RSI** | Relative Strength Index (0–100) |
| **Supertrend** | Volatility-based trend indicator (ATR-based) |
| **RR** | Risk/Reward ratio |
| **SL** | Stop Loss |
| **TP** | Take Profit (Target) |
| **CMP** | Current Market Price |
| **ORB** | Opening Range Breakout |
