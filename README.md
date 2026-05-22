# ⚡ SmartTrader — Zero-Cost Algorithmic Trading Scanner

A full-stack local platform for Indian stock market (NSE) algorithmic trading. Backtests 13 strategies, allows assigning multiple strategies to a stock, and monitors live markets every 60 seconds to fire WebSocket alerts.

## Architecture

```
apps/
├── frontend/   React + TypeScript + Vite    (port 5173)
├── api/        NestJS + Prisma + Socket.io  (port 3000)
└── engine/     Python FastAPI + pandas-ta   (port 8000)
```

## Quick Start (Docker — Recommended)

```bash
# Start everything
docker-compose up -d

# Apply database migrations (or push schema)
docker exec smart-trading-api npx prisma db push --accept-data-loss

# Start live scanner (separate terminal)
docker exec -it smart-trading-engine python scanner/live_scanner.py
```

Then open http://localhost:5173

## Quick Start (Local Development)

### 1. Start PostgreSQL
```bash
docker-compose up postgres -d
```

### 2. Push Prisma Schema
```bash
DATABASE_URL=postgresql://trader:trader@localhost:5470/smart_trading \
  npx prisma db push --accept-data-loss
```

### 3. Start NestJS API
```bash
npx nx serve api
```

### 4. Start Python Engine
```bash
cd apps/engine
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 5. Start React Frontend
```bash
npx nx serve frontend
```

### 6. Start Live Scanner (during market hours)
```bash
cd apps/engine
python scanner/live_scanner.py
```

## The 13 Strategies

### Intraday (5m / 15m)
1. **15m ORB** — Opening Range Breakout
2. **VWAP + Supertrend(10,3)** — Trend confirmation with VWAP filter
3. **9/15 EMA + RSI** — EMA crossover with RSI momentum filter
4. **MACD Zero-Line Cross** — MACD crossover below/above zero
5. **Inside Bar Breakout** — Mother bar breakout entry

### Swing (1D)
6. **44 SMA Pullback** — Price > 200 SMA, pullback to 44 SMA
7. **200 EMA + MACD** — Trend + momentum confluence
8. **Bollinger Band Squeeze** — Squeeze breakout
9. **RSI Divergence** — Bullish hidden divergence
10. **50/200 Golden Cross** — Classic trend-change signal
11. **SuperTrend EMA** — Supertrend + EMA filter
12. **Bollinger Mean Reversion** — Mean reversion inside bands
13. **Price Action** — Simple support/resistance breakout

## Documentation

| File | Purpose |
|---|---|
| `docs/understanding.md` | Domain knowledge, strategy logic, NSE market context |
| `docs/architecture.md` | System architecture, data flows, API contracts |
| `docs/progress.md` | Build phase tracker |
| `docs/ui-ux-flow.md` | UI screen designs and user journey maps |
| `docs/edge-cases-and-verification.md` | Edge cases and verification checklist |
| `gemini.md` | AI assistant context and session log |

## Environment Variables

**apps/api/.env**
```
DATABASE_URL=postgresql://trader:trader@localhost:5470/smart_trading
ENGINE_URL=http://smart-trading-engine:8000
PORT=3000
```

**apps/engine/.env**
```
DATABASE_URL=postgresql://trader:trader@localhost:5470/smart_trading
NESTJS_SIGNAL_URL=http://smart-trading-api:3000/api/signals/new
```
