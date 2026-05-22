## Project Overview: Zero-Cost Algorithmic Trading Scanner

**Objective:** Build a local web application that backtests trading strategies, assigns the best-performing strategy to a specific stock, and monitors the live market (using free polling) to push real-time trade alerts to a frontend UI via WebSockets.
**Tech Stack:**

- **Frontend:** React (TypeScript)
- **Backend:** NestJS (Node.js) with Socket.io (WebSocket Gateway)
- **Engine:** Python (FastAPI wrapper, pandas, pandas-ta, yfinance, jugaad_data/nsepython)
- **Database:** PostgreSQL (with Prisma or TypeORM)

---

## Phase 1: Database Schema & Setup

Initialize a PostgreSQL database with the following core tables:

1. Stock: id, symbol (e.g., RELIANCE.NS), name, is_active.
2. HistoricalData: id, stock_id, timestamp, open, high, low, close, volume, timeframe (1D, 15m, 5m).
3. BacktestReport: id, stock_id, strategy_name, timeframe, win_rate, total_trades, max_drawdown, expectancy.
4. ActiveConfiguration: id, stock_id, strategy_name, timeframe (This links a stock to its winning strategy for live monitoring).
5. LiveSignal: id, stock_id, strategy_name, signal_type (BUY/SELL), entry_price, stop_loss, target, timestamp, status (ACTIVE/CLOSED).

---

## Phase 2: Python Backtesting & Data Engine (FastAPI)

Create a Python microservice that handles heavy data lifting.
**Endpoints required:**

- POST /api/engine/fetch-history: Uses yfinance to download 5 years of 1D data and 60 days of 5m/15m data, saving it to PostgreSQL.
- POST /api/engine/run-backtest: Runs a selected strategy on historical data and returns performance metrics to be saved in BacktestReport.

**The Strategy Library (pandas-ta):**
Implement the following 10 strategies mathematically in the engine.

**Top 5 Intraday Strategies (Timeframes: 5m, 15m):**

1. **15m ORB (Opening Range Breakout):** Note High/Low of the first 15m candle. Entry: Price breaks High/Low. SL: Midpoint of the 15m candle. Target: 1:2 Risk/Reward (RR).
2. **VWAP + Supertrend (10,3):** Entry Long: Price closes above VWAP AND Supertrend is green. Entry Short: Price closes below VWAP AND Supertrend is red. SL: Supertrend line.
3. **9/15 EMA Crossover + RSI:** Entry Long: 9 EMA crosses above 15 EMA AND 14-period RSI > 50. Entry Short: 9 EMA crosses below 15 EMA AND RSI < 50. SL: Previous swing low/high.
4. **MACD Zero-Line Cross:** Entry Long: MACD line crosses above Signal line AND both are below the 0 line. SL: 1 \* ATR below entry candle. Target: 1:2 RR.
5. **Inside Bar Breakout:** Identify an 'Inside Bar' (high is lower than previous high, low is higher than previous low). Entry Long: Break of previous mother bar high. SL: Low of the inside bar.

**Top 5 Swing Strategies (Timeframe: 1D):**

1. **44 SMA Pullback:** Condition: Price > 200 SMA. Entry Long: Price touches 44 SMA and forms a bullish reversal candle (close > open). SL: 1.5 \* Daily ATR below candle low.
2. **200 EMA + MACD Golden Trend:** Condition: Price > 200 EMA. Entry Long: MACD bullish crossover. SL: 1 \* ATR below recent swing low. Target: 1:2 RR.
3. **Bollinger Band Squeeze (20, 2):** Condition: Bollinger Bands contract (Bandwidth reaches 6-month low). Entry Long: Price closes above the Upper Band. SL: Middle Band (20 SMA).
4. **RSI Divergence:** Condition: Price makes a Lower Low, but 14-RSI makes a Higher Low. Entry Long: First green candle close. SL: Exact low of the pattern. Target: 50 EMA.
5. **50/200 Golden Cross:** Entry Long: 50 SMA crosses above 200 SMA. SL: 1.5 \* ATR below the 50 SMA. (Long-term swing).

---

## Phase 3: The Live Polling Scanner (Python to NestJS)

Since we are using free data, build a while loop script in Python that runs during market hours (09:15 to 15:30 IST).

1. Query ActiveConfiguration to see which stocks are paired with which strategies.
2. Poll nsepython or jugaad_data every 60 seconds to get the CMP (Current Market Price) of those specific stocks.
3. Append the CMP to the local OHLCV arrays to form live candles.
4. Check the live candles against the assigned strategy conditions.
5. **Trigger:** If a condition is met, execute an HTTP POST request to the NestJS backend: POST /api/signals/new with payload { stock, strategy, type, entry, sl, target }.

---

## Phase 4: NestJS Backend & WebSocket Gateway

Create the core backend system.

1. **REST APIs:** CRUD operations for Stocks, Configs, and triggering the Python engine endpoints.
2. **Signal Receiver:** Implement the POST /api/signals/new endpoint. When triggered, it saves the signal to the LiveSignal table.
3. **WebSocket Gateway (@WebSocketGateway):** Immediately upon saving the new signal, emit a socket event: server.emit('NEW_TRADE_ALERT', signalPayload).

---

## Phase 5: React Dashboard (Frontend)

Build a multi-page dashboard.

1. **Backtest Arena:** A UI to select a stock and run backtests. Display results in a table. Include a button: "Set as Active Strategy" which writes to the ActiveConfiguration table.
2. **Live Scanner / Alert Feed (The Core View):**

- Connect to the NestJS Socket.io server on component mount.
- Listen for NEW_TRADE_ALERT.
- When an alert arrives, trigger an audio chime (HTML5 Audio API) and pop up a visual toast notification.
- Display a live, auto-updating table of "Active Signals" showing the Stock, Strategy, Entry Price, SL, and Target.
