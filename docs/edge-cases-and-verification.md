# Edge Cases & Verification Checklist

## Data Edge Cases

### yfinance / Market Data

| Edge Case | Handling |
|---|---|
| NSE holiday — yfinance returns empty DataFrame | Check `df.empty` before processing; log and skip |
| Rate limiting — too many requests too fast | Add `time.sleep(1)` between bulk downloads |
| Weekend data request | Detect day-of-week; skip scanner on Sat/Sun |
| 5m data limited to 60 days | Surface this limit in UI tooltip on Backtest Arena |
| Partial candle at end of day | For live polling, use `iloc[-2]` (previous complete candle) |
| Timezone mismatch | yfinance returns UTC; convert to IST (`Asia/Kolkata`) before all comparisons |
| Adjusted vs unadjusted prices | yfinance returns `auto_adjust=True` by default; keep consistent |
| Stock delisted | yfinance raises exception; catch and return 404 to frontend |
| Market halted mid-day | Scanner continues polling; no signals will fire (price frozen) |

### Strategy Computation

| Edge Case | Handling |
|---|---|
| Insufficient data for indicator | Min bars check: EMA(200) needs 200+ bars, Supertrend needs 10+ |
| NaN values in indicator columns | `dropna()` after computing indicators, before signal check |
| ORB strategy outside 09:15–09:30 window | Skip signal check if not in valid trading window |
| RSI Divergence — no divergence found in lookback | Return no signal (expected outcome) |
| Bollinger Squeeze — bandwidth never at 6-month low | Lower threshold or return no signal |
| Multiple signals on same candle | Only emit one signal per stock per candle |
| Backtest on insufficient historical data | If < 200 bars available for daily, warn user |

---

## WebSocket Edge Cases

| Edge Case | Handling |
|---|---|
| Frontend disconnects mid-session | Socket.io auto-reconnects with exponential backoff |
| Scanner sends duplicate signal | Check DB for existing ACTIVE signal on same stock+strategy before saving |
| Signal emitted before frontend connects | Frontend fetches `/api/signals` on mount to get existing active signals |
| Multiple browser tabs open | All tabs receive the same event (broadcast) |
| NestJS restarts mid-scan | Scanner retries HTTP POST with 3 retries and 5s delay |

---

## Database Edge Cases

| Edge Case | Handling |
|---|---|
| Duplicate stock symbol insert | Unique constraint on `symbol`; return 409 Conflict |
| ActiveConfiguration for non-existent stock | Foreign key constraint catches it |
| Concurrent backtest writes | Each backtest creates a new row (no upsert conflict) |
| HistoricalData re-fetch for existing stock | Upsert on `(stockId, timestamp, timeframe)` — update if exists |
| Very large HistoricalData table | Index on `(stockId, timeframe, timestamp)` for fast reads |

---

## API Edge Cases

| Edge Case | Handling |
|---|---|
| Python engine not running when NestJS proxies | Return 503 with message "Engine unavailable" |
| Invalid stock symbol sent to engine | Engine catches yfinance error, returns 422 |
| Run backtest before fetching history | Engine checks if HistoricalData exists; returns 400 if not |
| Set active config for strategy with no backtest | UI disables "Set Active" until backtest has been run |

---

## Verification Checklist

### Phase 1 — Database
- [ ] `prisma migrate dev` runs without errors
- [ ] All 5 tables created in PostgreSQL
- [ ] Unique constraints: `Stock.symbol`, `ActiveConfiguration.stockId`
- [ ] Foreign keys: `HistoricalData.stockId`, `BacktestReport.stockId`, etc.
- [ ] Index on `HistoricalData(stockId, timeframe, timestamp)`

### Phase 2 — Python Engine
- [ ] `uvicorn main:app --reload` starts on port 8000
- [ ] `POST /api/engine/fetch-history` with `RELIANCE.NS` → rows appear in DB
- [ ] `POST /api/engine/run-backtest` returns valid metrics (winRate is 0–100)
- [ ] Each of the 10 strategies runs without exception on test data
- [ ] ORB strategy: tested with candle at 09:20 (valid) and 14:00 (invalid window)
- [ ] Empty DataFrame handling: no crash when yfinance returns no data

### Phase 3 — NestJS Backend
- [ ] `npm run start:dev` starts on port 3000
- [ ] `GET /api/stocks` returns `[]` on empty DB
- [ ] `POST /api/stocks` creates a stock and returns 201
- [ ] `POST /api/signals/new` saves signal AND emits WebSocket event
- [ ] CORS headers allow `http://localhost:5173`
- [ ] Prisma graceful shutdown hook registered

### Phase 4 — React Frontend
- [ ] `npm run dev` starts on port 5173
- [ ] Backtest Arena: stock dropdown loads from `/api/stocks`
- [ ] "Fetch History" button triggers engine endpoint, shows success toast
- [ ] "Run Backtest" button shows spinner, then populates results table
- [ ] "Set Active Strategy" button calls `/api/configs` and shows confirmation toast
- [ ] Live Scanner: Socket.io connects on component mount
- [ ] `NEW_TRADE_ALERT` event → toast appears + audio plays + table row added
- [ ] Market status shows OPEN (09:15–15:30 IST) and CLOSED otherwise

### Phase 5 — End-to-End
- [ ] Start all services via `docker-compose up`
- [ ] Add RELIANCE.NS stock via frontend
- [ ] Fetch history for RELIANCE.NS
- [ ] Run all 10 backtests, confirm metrics appear
- [ ] Set VWAP+Supertrend as active strategy
- [ ] Start live scanner manually (`python scanner/live_scanner.py`)
- [ ] Manually trigger signal: `POST /api/signals/new` with test payload
- [ ] Confirm toast + audio fires on frontend
- [ ] Confirm signal appears in active signals table

---

## Known Limitations

1. **5m/15m data**: yfinance limits to 60 days — backtest period is shorter for intraday
2. **Live polling delay**: Signals fire when candle completes, not tick-by-tick
3. **NSE symbol format**: Must use `.NS` suffix — bare symbols like `RELIANCE` won't work
4. **yfinance uptime**: Occasionally rate-limited or returns stale data
5. **No order execution**: This is a scanner only — no brokerage API integration
