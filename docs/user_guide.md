# Smart Trader - End-to-End Testing Guide

Welcome to the **Smart Trader** platform! This guide will walk you through the end-to-end user flow for testing the platform locally.

## Prerequisite: Starting the Services
Ensure that all services are running via Docker Compose:
```bash
docker compose up --build -d
```
You can verify the status with `docker ps`. You should see `frontend`, `api`, `engine`, and `db` running.

Access the Web UI at **http://localhost:5173/**.

---

## Step 1: Adding a Stock (Very Important!)
Before you can fetch historical data, run a backtest, or scan a stock, **it must exist in your local database**. 

If you try to fetch history for a stock (like `JWL`) before adding it, the Python Engine will reject it with a `404 Not Found` error (`Stock JWL not found in DB. Add it first.`).

1. Open the Web UI and navigate to the **Backtest Arena**.
2. Locate the **"Manage Stocks"** or **"Add Stock"** section.
3. Enter a valid NSE stock ticker (e.g., `RELIANCE.NS`, `TCS.NS`, `INFY.NS`). 
   *(Note: The Python Engine uses `yfinance`, so Indian stocks generally need the `.NS` suffix).*
4. Click **Add Stock**. This creates the record in the PostgreSQL database.

---

## Step 2: Fetching Historical Data
Once the stock is added to the database, you need to populate its OHLCV (Open, High, Low, Close, Volume) data.

1. Select your newly added stock from the UI.
2. Choose a timeframe (e.g., `15m` for intraday, or `1d` for swing trading).
3. Click **Fetch History**.
4. The NestJS API will forward this request to the Python Engine, which will download the data from Yahoo Finance and save it to the database. You should see a success message in the UI once this completes.

---

## Step 3: Running a Backtest
With historical data available, you can simulate trading strategies.

1. In the **Backtest Arena**, select the stock you just fetched data for.
2. Select a timeframe (e.g., `15m`).
3. Select a strategy from the dropdown (e.g., `15m Opening Range Breakout`).
4. Click **Run Backtest**.
5. The UI will render the results, displaying metrics like **Total Return**, **Win Rate**, and **Max Drawdown**.

---

## Step 4: Enabling the Live Scanner
The Live Scanner monitors the market in real-time and broadcasts signals via WebSockets.

1. Navigate to the **Live Scanner** tab in the Web UI.
2. Toggle the **"Enable Scanner"** switch for a specific stock/strategy combination. This sets the configuration to `active=true` in the database.
3. **Note:** The actual scanning loop runs inside the Python engine. Depending on the current implementation, it may run automatically via a background task, or you may need to start the manual scanner script inside the engine container. 

To run the manual live scanner script (if the background loop isn't active by default):
```bash
docker exec -it smart-trading-engine python -m apps.engine.scanner.live_scanner
```

### 🕒 Strict Scanner Operating Hours
The live scanner enforces real-world market hours to protect your capital:
- **Before 9:30 AM IST:** The scanner tracks prices but will **not** generate new signals (to avoid opening 15-minute fake moves).
- **After 3:00 PM IST:** No new INTRADAY setups will be generated.
- **At 3:15 PM IST:** All remaining open INTRADAY positions are forcefully squared off at the market price, and the scanner stops evaluating *all* strategies.

---

## Step 5: Telegram Alerts & Portfolio Accuracy
Once the scanner is running and active, the system handles the complete trade lifecycle automatically.

### Telegram Notifications
Ensure `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set in the API `.env` file. The system will send real-time alerts for:
- 🟢 **New Signals:** Generated when entry conditions are met.
- 🔒 **Trailing SL Updates:** When a trade reaches Phase 1 or 2, locking in breakeven or profit.
- 🤑 **Partial Closes:** When hitting 50% or 75% progress (if trade quantity >= 3).
- ⚠️ **Reversals:** If a pattern indicates a reversal after 80% progress.
- ✅/❌ **Trade Closed:** When the trade fully closes (SL, TP, or Intraday Auto-Square-Off), detailing final exit price and complete P&L.

### Portfolio Accuracy
The **Portfolio** tab tracks all active and closed trades. 
- P&L is calculated with exact mathematical precision, incorporating realized profits from partial exits and updating the `remainingQty` live. 
- If a Stop Loss or Take Profit is hit, the portfolio logs the exact SL/TP limit price to simulate a limit order and prevent false slippage reporting.

---

## Troubleshooting Common Errors

### "Stock XYZ not found in DB"
- **Cause:** You tried to fetch history or backtest a stock that hasn't been added.
- **Fix:** Follow **Step 1** to add the stock first.

### "HTTP ERROR 404" on localhost:5173
- **Cause:** The frontend container failed to build correctly or routing is broken.
- **Fix:** We fixed this by ensuring `docker-compose.yml` uses the root context for the frontend. Rebuild with `docker compose up --build -d frontend`.

### Missing Data during Backtest
- **Cause:** You haven't fetched historical data for the requested timeframe.
- **Fix:** Go back to **Step 2** and ensure you fetch data for the exact timeframe you want to backtest.
