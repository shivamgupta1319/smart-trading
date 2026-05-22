# gemini.md — AI Assistant Context for Smart Trading Platform

> This file is the persistent memory for the AI assistant (Antigravity/Gemini) working on this project.
> Update this file at the end of every session with a summary of what was done, decisions made, and what's next.

---

## Project Identity

- **Name:** Zero-Cost Algorithmic Trading Scanner
- **Workspace:** `/home/shivam/workspace/smart-trading`
- **Conversation ID:** `773b36f1-c140-4ee5-bff1-7efcefb37c0b`
- **Started:** 2026-05-22

---

## Architecture Summary

```
smart-trading/ (Nx monorepo)
├── apps/
│   ├── frontend/      React + TypeScript + Vite (dark terminal UI)
│   ├── api/           NestJS + Socket.io + Prisma ORM
│   └── engine/        Python FastAPI + pandas-ta + yfinance
├── docs/              All project documentation
├── docker-compose.yml PostgreSQL + all services
└── gemini.md          This file
```

**Data Flow:**
```
yfinance (NSE) → Python Engine → PostgreSQL
                                      ↓
React Frontend ←── WebSocket ── NestJS Backend ←── Engine POST /api/signals/new
```

---

## Key Technical Decisions

| Decision | Choice | Reason |
|---|---|---|
| Data source (history + live) | `yfinance` (.NS suffix) | More reliable than nsepython/jugaad_data |
| Monorepo tool | Nx | Coordinated multi-app builds and deps |
| ORM | Prisma | Type-safe, excellent migration support |
| DB | PostgreSQL | Relational, good for time-series OHLCV |
| Engine language | Python 3.11 + FastAPI | pandas-ta for indicators, async ready |
| Styling | Vanilla CSS (dark terminal theme) | No framework dependency, full control |
| Live polling interval | 60 seconds | Rate limit friendly for free yfinance |
| Market hours | 09:15–15:30 IST | NSE trading hours |

---

## Strategies Implemented

### Intraday (5m, 15m)
1. **ORB 15m** — Opening Range Breakout: High/Low of first 15m candle, SL at midpoint, Target 1:2 RR
2. **VWAP + Supertrend(10,3)** — Price above/below VWAP + Supertrend direction
3. **9/15 EMA + RSI** — EMA crossover filtered by RSI > or < 50
4. **MACD Zero-Line Cross** — MACD/Signal cross with both below/above zero
5. **Inside Bar Breakout** — Engulfed candle breakout of mother bar

### Swing (1D)
6. **44 SMA Pullback** — Price > 200 SMA, touches 44 SMA, bullish reversal candle
7. **200 EMA + MACD** — Price > 200 EMA + MACD bullish crossover
8. **Bollinger Band Squeeze** — Bandwidth at 6-month low, then close above Upper Band
9. **RSI Divergence** — Price lower low + RSI higher low → first green candle
10. **50/200 Golden Cross** — 50 SMA crosses above 200 SMA

---

## Database Schema (Prisma)

- `Stock` — id, symbol, name, isActive
- `HistoricalData` — id, stockId, timestamp, open, high, low, close, volume, timeframe
- `BacktestReport` — id, stockId, strategyName, timeframe, winRate, totalTrades, maxDrawdown, expectancy
- `ActiveConfiguration` — id, stockId (unique), strategyName, timeframe
- `LiveSignal` — id, stockId, strategyName, signalType, entryPrice, stopLoss, target, timestamp, status

---

## API Contracts

### Python Engine (port 8000)
- `POST /api/engine/fetch-history` — `{ symbol, timeframes[] }` → fetches & stores OHLCV
- `POST /api/engine/run-backtest` — `{ symbol, strategy, timeframe }` → returns BacktestReport

### NestJS Backend (port 3000)
- `GET /api/stocks` — List all stocks
- `POST /api/stocks` — Add stock
- `GET /api/configs` — List active configurations
- `POST /api/configs` — Set active strategy for a stock
- `POST /api/signals/new` — Receive new signal from scanner (triggers WebSocket emit)
- `GET /api/signals` — List live signals
- `POST /api/engine/fetch-history` — Proxy to Python
- `POST /api/engine/run-backtest` — Proxy to Python

### WebSocket Events (Socket.io)
- `NEW_TRADE_ALERT` → `{ stockId, symbol, strategyName, signalType, entryPrice, stopLoss, target, timestamp }`

---

## Environment Variables

### apps/api/.env
```
DATABASE_URL=postgresql://trader:trader@localhost:5432/smart_trading
ENGINE_URL=http://localhost:8000
PORT=3000
```

### apps/engine/.env
```
DATABASE_URL=postgresql://trader:trader@localhost:5432/smart_trading
NESTJS_SIGNAL_URL=http://localhost:3000/api/signals/new
```

### Docker
- PostgreSQL: port 5432, user: trader, pass: trader, db: smart_trading
- API: port 3000
- Engine: port 8000
- Frontend: port 5173

---

## Session Log

### 2026-05-22 — Session 1
**Done:**
- Read and analyzed plan.md
- Created implementation plan and task tracker
- Confirmed: yfinance for all data, Nx monorepo, docker-compose for everything
- Initialized Nx workspace (apps preset)
- Created all 6 documentation files (understanding, architecture, progress, ui-ux-flow, edge-cases, gemini)
- Built PostgreSQL + Prisma schema (5 models)
- Implemented all 10 trading strategies in Python
- Built NestJS backend (stocks, configs, signals, WebSocket gateway, engine proxy)
- Built React frontend (dark terminal theme, Backtest Arena, Live Scanner)
- Created docker-compose.yml

**Next:**
- Run full integration test
- Verify WebSocket flow end-to-end
- Test with RELIANCE.NS live data during market hours

---

## Known Gotchas / Watch Out For

1. **yfinance rate limiting**: Add `time.sleep(1)` between batch downloads
2. **15m ORB**: Only valid during first 15 minutes of market (09:15–09:30 IST) — skip outside that window
3. **Backtest on 5m data**: yfinance only provides 60 days of 5m data — communicate this limit in UI
4. **NSE holidays**: yfinance returns empty data on market holidays — handle gracefully
5. **Supertrend**: `pandas-ta` supertrend returns `SUPERT_x_y` columns — check column names carefully
6. **Prisma + NestJS**: Use `PrismaService` with `onModuleInit` to connect, `enableShutdownHooks` for graceful shutdown
7. **Socket.io CORS**: Must configure `cors: { origin: 'http://localhost:5173' }` in gateway
