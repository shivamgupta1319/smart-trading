# Architecture: Zero-Cost Algorithmic Trading Scanner

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      Docker Compose                         │
│  ┌────────────┐   ┌────────────┐   ┌──────────────────┐    │
│  │  frontend  │   │    api     │   │     engine       │    │
│  │ React/Nginx│   │  NestJS    │   │ Python/FastAPI   │    │
│  │  Port 5173 │   │  Port 3000 │   │   Port 8000      │    │
│  └─────┬──────┘   └─────┬──────┘   └───────┬──────────┘    │
│        │ WebSocket       │ HTTP Proxy        │ SQLAlchemy    │
│        └────────────────►│◄──────────────────┘              │
│                          │                                  │
│                 ┌────────▼────────┐                         │
│                 │   PostgreSQL    │                         │
│                 │   Port 5470     │                         │
│                 └─────────────────┘                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Services

### React Frontend (`apps/frontend`) — Port 5173
- React 18 + TypeScript + Vite (served via Nginx in Docker)
- Vanilla CSS dark terminal theme
- Pages: Backtest Arena, Live Scanner

### NestJS Backend (`apps/api`) — Port 3000
- Prisma ORM, Socket.io WebSocket gateway
- Modules: Stocks, Configs, Signals, Engine proxy, Prisma

### Python Engine (`apps/engine`) — Port 8000
- FastAPI, pandas-ta, yfinance, SQLAlchemy
- Handles data fetching, backtesting, live scanning

### PostgreSQL — Port 5470
- Schema: Stock, HistoricalData, BacktestReport, ActiveConfiguration, LiveSignal, Trade
- The `Trade` model auto-syncs with `LiveSignal` to build a live Portfolio and compute P&L.

---

## Data Flows

### Backtest Flow
```
User → React → POST /api/engine/run-backtest (NestJS proxy)
→ Python loads HistoricalData → runs 28 strategies
→ saves BacktestReports → returns metrics → React displays
```

### Live Alert Flow
```
live_scanner.py (every 60s, 09:30–15:15 IST)
→ 1. Evaluate Trailing SL, Partial Exits (35%, 40%), & Reversals (80%+)
→ 2. fetch yfinance candles → run strategy (if > 09:30 AM)
→ 3. signal detected → POST /api/signals/new (NestJS)
→ save LiveSignal → Create Trade (Risk Mgmt 2%) 
→ emit NEW_TRADE_ALERT (Socket.io) + Send Telegram Message
→ React: toast + audio + table update + Portfolio sync
```

---

## REST API

```
GET/POST   /api/stocks
GET/POST   /api/configs
POST       /api/signals/new
GET        /api/signals
POST       /api/engine/fetch-history
POST       /api/engine/run-backtest
```

## Nx Workspace Layout

```
smart-trading/
├── apps/
│   ├── frontend/     React + Vite
│   ├── api/          NestJS + Prisma
│   └── engine/       Python FastAPI
├── docs/
├── docker-compose.yml
├── nx.json
└── gemini.md
```

---

## v2 Architecture Updates (branch `roadmap-v2`)

**Security layer.** Every HTTP request and socket handshake now passes an opt-in
`API_KEY` (NestJS `ApiKeyGuard` + global throttle; FastAPI `require_api_key` +
LLM rate-limit). The key is threaded across all hops: frontend → API → engine,
and scanner → API. CORS and all secrets are env-driven from a single root `.env`.

**Data integrity.** Ledger money columns are Postgres `NUMERIC(18,4)` (Prisma
`Decimal`); a global interceptor coerces Decimal → number in responses so the
API contract stays numeric. Signal+Trade writes and closes are transactional; a
partial-unique index prevents duplicate active signals.

**Backtest engine.** `strategies/base.py` simulates realistic fills (intrabar
High/Low, next-bar entry, pessimistic straddle), Indian transaction costs +
slippage (`backtest_config.py`), and risk-based sizing. `simulate()` exposes
per-trade P&L, powering the new analytics.

**New analytics + real-time.**
```
GET   /api/trades/risk                 # margin used / buying power / heat / sector concentration
GET   /api/trades/stats                # portfolio ROI (funded) + (stock×strategy) edge metrics
GET   /api/configs                     # monitored stocks, each with its latest backtest snapshot
POST  /api/engine/run-walk-forward     # out-of-sample rolling folds
POST  /api/engine/run-monte-carlo      # bootstrapped ROI/drawdown distribution
WS    TRADE_UPDATE                      # CLOSED / PARTIAL / SL_UPDATED
```

**Capital model (authentic ₹1L account).** Sizing is 2%-risk per trade, capped to the
trade's buying power (`INITIAL_CAPITAL × leverage`; INTRADAY 5×, delivery 1×) so a tight-stop
stock can't size into an un-fundable notional. At entry a trade is **FUNDED** only if its
margin (`notional ÷ leverage`) fits remaining cash **and** total open risk (heat) stays ≤ 6%
(`MAX_HEAT_PCT`); otherwise it's a **SHADOW** trade — recorded and tracked for would-be P&L
but excluded from portfolio ROI (`Trade.fundingStatus`). Leverage never changes the per-trade
loss (the stop does) — only how much cash a position locks up. `GET /api/trades/risk` reports
`marginUsed / marginUsedPct / availableCash / notional / shadowPositions`;
`GET /api/trades/stats` returns `roiPct` (funded only) plus, per (stock×strategy) cell,
`expectancy / avgRMultiple / profitFactor / maxDrawdown / confidence / reliable` (research
uses funded+shadow). Constants live in `apps/api/src/common/risk.ts`
(`LEVERAGE_INTRADAY`, `LEVERAGE_DELIVERY`, `MAX_HEAT_PCT`, `MIN_TRADES_FOR_CONFIDENCE`).

**Scanner UX.** `/scanner` is split into two tabs: **Live Scanner** (connection status +
active signals) and **Monitored Stocks** (a table of each monitored stock×strategy with its
latest persisted `BacktestReport`, plus Re-run — recomputes via `POST /api/engine/run-backtest`,
which persists a fresh report — and Remove — `DELETE /api/configs/:id`).

**Fetch scheduler.** A standalone `scheduler` service (engine image,
`scheduler/fetch_scheduler.py`, profile `live`) runs a **daily after-close** fetch of every
active stock so the backtest dataset grows over time — intraday (15m/5m) accumulates past
yfinance's ~60-day-per-request cap because `upsert_ohlcv` never deletes. Daily cadence is
deliberate: backtests only use completed bars, whole only after the 15:30 IST close. Shares
the `fetch_and_store()` core with `POST /api/engine/fetch-history`. Env: `FETCH_RUN_HOUR_IST`,
`FETCH_RUN_MINUTE_IST`, `FETCH_TIMEFRAMES`, `FETCH_ON_START`.

**Isolated dev stack.** A parallel `smart-trading-v2` compose (ports 5471/3001/
8001/5174, own volume, cloned DB) runs alongside the live stack untouched. See
[v2-environment.md](v2-environment.md) and [roadmap-implementation.md](roadmap-implementation.md).
