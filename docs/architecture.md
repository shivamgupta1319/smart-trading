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
