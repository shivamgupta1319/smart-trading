# Progress Tracker

## Phase 0 — Setup & Documentation ✅
- [x] plan.md analyzed
- [x] implementation_plan.md created
- [x] gemini.md created (at workspace root)
- [x] docs/understanding.md created
- [x] docs/architecture.md created
- [x] docs/progress.md (this file)
- [x] docs/ui-ux-flow.md created
- [x] docs/edge-cases-and-verification.md created
- [x] Nx monorepo initialized (`nx init`)
- [x] NestJS API app generated (`apps/api`)
- [x] React Frontend app generated (`apps/frontend`)
- [x] docker-compose.yml created (postgres + api + engine + frontend)

## Phase 1 — Database ✅
- [x] Prisma schema (5 models: Stock, HistoricalData, BacktestReport, ActiveConfiguration, LiveSignal)
- [x] Prisma v7 config (prisma.config.ts with pg adapter)
- [x] Prisma client generated successfully
- [ ] Run `prisma migrate dev` against live PostgreSQL (requires DB running)

## Phase 2 — Python Engine ✅
- [x] FastAPI app (main.py) with CORS
- [x] requirements.txt (fastapi, uvicorn, pandas, pandas-ta, yfinance, sqlalchemy)
- [x] db/client.py — SQLAlchemy sync engine
- [x] routers/history.py — POST /api/engine/fetch-history (yfinance + upsert to DB)
- [x] routers/backtest.py — POST /api/engine/run-backtest (load historical + run + save)
- [x] strategies/base.py — Abstract strategy + backtest runner (equity curve simulation)
- [x] Strategy 1: ORB 15m
- [x] Strategy 2: VWAP + Supertrend (10,3)
- [x] Strategy 3: 9/15 EMA + RSI
- [x] Strategy 4: MACD Zero-Line Cross
- [x] Strategy 5: Inside Bar Breakout
- [x] Strategy 6: 44 SMA Pullback (Swing)
- [x] Strategy 7: 200 EMA + MACD Golden Trend (Swing)
- [x] Strategy 8: Bollinger Band Squeeze (Swing)
- [x] Strategy 9: RSI Divergence (Swing)
- [x] Strategy 10: 50/200 Golden Cross (Swing)
- [x] scanner/live_scanner.py — 60s polling loop with IST market hours
- [x] strategies/__init__.py — STRATEGY_REGISTRY and STRATEGY_TIMEFRAMES

## Phase 3 — NestJS Backend ✅
- [x] prisma/prisma.service.ts (with Prisma v7 pg adapter)
- [x] prisma/prisma.module.ts
- [x] stocks/ (CRUD — GET, POST, DELETE)
- [x] configs/ (Upsert ActiveConfiguration)
- [x] signals/signals.service.ts (with deduplication)
- [x] signals/signals.controller.ts (POST /api/signals/new)
- [x] signals/signals.gateway.ts (@WebSocketGateway — emits NEW_TRADE_ALERT)
- [x] engine/engine.controller.ts (HTTP proxy to Python)
- [x] app/app.module.ts (wires all modules)
- [x] main.ts (CORS + ValidationPipe)
- [x] **Build: ✅ NestJS compiles successfully**

## Phase 4 — React Frontend ✅
- [x] styles/index.css — Dark terminal theme (Inter + JetBrains Mono)
- [x] components/Navbar.tsx — With market status dot
- [x] components/ToastNotification.tsx — Slide-in toast with BUY/SELL styling
- [x] hooks/useSocket.ts — Socket.io client hook
- [x] pages/BacktestArena.tsx — Stock management + history fetch + backtest + set active
- [x] pages/LiveScanner.tsx — WebSocket feed + audio chime + toast + signals table
- [x] app/app.tsx — React Router with Navbar
- [x] **Build: ✅ React/Vite builds successfully (315KB JS, 10.37KB CSS)**

- [x] Resolve PostgreSQL port mapping and initialize schema
- [x] Start PostgreSQL: `docker compose up postgres -d`
- [x] Run migrations: `prisma db push`
- [x] Start API + Engine + Frontend (`docker compose up`)
- [x] Test end-to-end data flow (Database -> Engine -> API -> Frontend)
- [x] Fetch history, run backtest
- [x] Set active strategy, start live scanner
- [x] Verify WebSocket alert flow end-to-end

## Phase 5 — Enhancements & Optimizations ✅
- [x] Fix Pandas-TA column name mismatches in Bollinger Bands and Supertrend
- [x] Optimize Dockerfile build sizes (Frontend < 100MB, API ~800MB, Engine ~700MB)
- [x] Convert ActiveConfiguration to support multiple live strategies per stock
- [x] Seed NSE Stocks into Database for auto-complete
- [x] Update UI flows to remove unnecessary forms and optimize UX

## Phase 6 — Advanced Features ✅
- [x] Integrate `lightweight-charts` for Interactive Candlestick Charts with Indicators (EMA, BB, Volume)
- [x] Add `/api/engine/chart-data/{symbol}` endpoint to stream chart history & indicators
- [x] Auto-position sizing & 2% risk management model implemented in SignalsService
- [x] Full Portfolio Tracking & Trade Journal implementation (Trades and P&L Tracking)
- [x] Trade classification by `holdDuration` (`INTRADAY`, `SHORT_SWING`, `MID_SWING`, `LONG_POSITIONAL`)
- [x] Global Telegram Bot Alert system integration for Signals and Exits
- [x] Fix TypeScript compilation errors (Strict Property Init & lightweight-charts v5 migration)

## Phase 7 — Stabilization & Risk Framework ✅
- [x] 3-Phase Partial Exit Framework Integration (Breakeven -> 35% at 50% -> 40% at 75%)
- [x] Quantity restrictions on partial exits (Minimum 3 shares required)
- [x] Layer 3 Reversal Detection Engine (Pin bar, Engulfing, Volume, RSI divergence after 80% progress)
- [x] Market Time-Gate Enforcement (9:30 AM Setup Block, 3:00 PM Intraday Block, 3:15 PM Square-off)
- [x] Zombie Trade Prevention (Cascading partial close to full close on 0 remaining shares)
- [x] Exact P&L Calculation Fixes (incorporating `realizedPnl` and `remainingQty`)
- [x] Telegram Notifications for all lifecycles (Trailing SL, Partial Close, Reversal, Trade Closed)

## Phase 8 — Trust & correctness audit + auto-select hardening ✅ (2026-07-13)
> Full report: [agent-reports/2026-07-13-trust-and-correctness-audit.md](agent-reports/2026-07-13-trust-and-correctness-audit.md)
- [x] Audited docs + live data (174 closed trades) + engine/API code for trust & correctness
- [x] Pruned chronic losers from live scanning — DMA20_Pullback, Fibonacci_Golden_Zone, Volume_Profile_POC (9 cells, 77→68 active); recorded in `infra/scripts/hygiene-prune-losers.sql`
- [x] Backtest de-inflation: `BT_CAP_POSITION_VALUE` caps position notional so compounding no longer inflates ROI (2458%→358% on a test cell); NET `avgRMultiple` added to metrics
- [x] Auto-select hardened: rank by NET avg-R (not ROI/DD); gates tightened (maxDD 40→25%, PF 1.05→1.3, OOS folds 40→60%, walk-forward consistency ON, new min-avg-R gate); drops forming tail bar for determinism
- [x] Persistent `AUTOSELECT_DENYLIST` so manually-pruned losers are never re-promoted (wired through compose env)
- [x] Portfolio "Invested Now" now shows deployed **margin**, not leveraged notional
- [x] Verified via read-only dry-run auto-select (6 quality picks / 31 strategies) + `/api/trades/stats`
- [ ] **Phase C (open):** backtest↔live exit parity — fix dead live swing trail (daily candles), book live P&L net of costs, reconcile intraday exits. Until done, auto-select undervalues intraday winners.
- [ ] **FEAT-002 (open):** BREAKEVEN band (scratches booked WIN), `realizedPnl` column gap, per-trade `pnlPercent` uses notional not margin.

> ⚠️ **Phases 0–7 above describe the original v1 prototype** and are partly stale (ports 3000/8000/5173,
> the "3-phase partial exit" framing — the live intraday loop actually does breakeven + candle-trail +
> reversal + 15:15 square-off; ₹1L/2%-risk model replaced by the per-cell ₹10k compounding fund).
> For the **current** system see [architecture.md](architecture.md) and [work-pc-deployment.md](work-pc-deployment.md).

## What's Running (current — v2 on work-pc)
- **v2 host ports:** frontend `5174`, api `3001`, engine `8001`, postgres `5471` (v1 holds 3000/8000/5173/5470)
- **Deploy:** build+push on dev PC (`infra/scripts/build-and-push.sh`), pull+run on work-pc (`infra/scripts/deploy.sh`)
- **6 services:** db, api, engine, frontend, scanner, scheduler (scanner+scheduler share the engine image)
- Public: `https://trading-v2.pseo.cloud` (basic-auth) — see [work-pc-deployment.md](work-pc-deployment.md)

### Historical dev commands (v1 prototype)
- **NestJS**: `npx nx serve api` (port 3000)
- **Python Engine**: `uvicorn main:app --reload` in apps/engine (port 8000)
- **React**: `npx nx serve frontend` (port 5173)
- **Live Scanner**: `python apps/engine/scanner/live_scanner.py`
- **All Docker**: `docker-compose up`
