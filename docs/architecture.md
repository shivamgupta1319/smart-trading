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
live_scanner.py (every 100s, new setups 09:30–15:00/15:15 IST)
→ 1. Open trades: trailing stop, partial exits (35% + 35%), reversal exit (80%+), 15:15 square-off
     stop-out booked at the WORSE of stop and live price; target booked at the target
→ 2. fetch yfinance candles → run strategy on the last completed candle
     strategy returned no signal column → "CANNOT EVALUATE" warning (not "no signal")
→ 3. signal found → entry limits (INTRADAY: max 2 per cell per day, 30 min cooldown after an exit)
     → entry priced at the LIVE quote; dropped if that is already outside stop..target
→ 4. POST /api/signals/new (NestJS) → size the trade (see Capital model); 400 if one share cannot fit
→ save LiveSignal → Create Trade
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

**Capital model (per-cell testing lab).** Each (stock × strategy) cell owns its own ₹10k
fund (`BASE_CELL_CAPITAL`) that COMPOUNDS with that cell's realized P&L. A trade deploys
`cellCapital × leverage` of notional (INTRADAY 5×, delivery/swing 1×), and is also bounded
by a per-trade risk cap of `cellCapital × RISK_PER_TRADE_PCT` (2%):
`qty = min(floor(notional / entry), floor(riskBudget / |entry − stop|))`. If that is 0 (one
share already breaks a bound) the signal is rejected and the backtest skips it too
(`position_qty` in the engine, `sizePosition` in the API). There is **no funding gate** — every
selected-strategy signal is a real mock-money trade (the old FUNDED/SHADOW split and
`Trade.fundingStatus` were removed). Leverage never changes the per-trade loss (the stop
does) — only the deployed notional. `GET /api/trades/risk` reports
`marginUsed / marginUsedPct / notional / totalHeat / heatPct` against the deployed base
(₹10k × open cells); `GET /api/trades/stats?window=<days>` returns `netPnl / investedNow /
roiPct` plus, per (stock×strategy) cell, `cellCapital / cellRoiPct / expectancy /
avgRMultiple / profitFactor / maxDrawdown / confidence / reliable`, and a `leaderboard` /
`bestCell` ranked by fund growth.

**Shared settings.** `config/trading.json` is the one place the values both runtimes must
agree on are defined: `BASE_CELL_CAPITAL`, `LEVERAGE_INTRADAY`, `LEVERAGE_DELIVERY`,
`RISK_PER_TRADE_PCT` (a fraction: 0.02 = 2%) and every transaction-cost rate. The engine reads
it through `apps/engine/shared_config.py`, the API through
`apps/api/src/common/shared-config.ts`. An environment variable of the same name overrides a
value; a missing key stops the service at start-up. Both images copy the file in, so the
engine image builds from the repo root. Tests on each side assert the same golden cost
figures. API-only constants (`MAX_HEAT_PCT`, `MIN_TRADES_FOR_CONFIDENCE`) stay in
`apps/api/src/common/risk.ts`.

**Fill model (backtest and live).** Backtest: entry at the next bar's open, stops and
targets checked against each bar's high/low, a bar that opens beyond the stop fills at that
open, costs and 5 bps slippage charged. Live: entry at the live quote when the signal is
found, stop-outs at the worse of stop and live price, P&L booked after costs. Entry limits
(`apps/engine/entry_limits.py`) and intraday exit rules (`apps/engine/intraday_exits.py`) are
single modules imported by both paths. Known remaining difference: live polls every 100
seconds, so a stop can be noticed late; the backtest books the stop level.

**Cell lifecycle.** Every cell (`ActiveConfiguration`) has a `status` that the API sets from
the cell's own closed paper trades, after costs, measured in R (`common/lifecycle.ts`,
applied by `configs/lifecycle.service.ts` after every close and on
`POST /api/configs/evaluate`):

| Status | Meaning | Rule (defaults in `config/trading.json` → `lifecycle`) |
|---|---|---|
| `TESTING` | Collecting evidence | Default |
| `PAUSED` | Kept losing | Last 20 trades average below −0.15R, or lost more than 15% of the cell's starting fund |
| `PROVEN` | Has earned trust | 40+ trades, average above +0.10R, profit factor 1.3+, positive in both halves |

A paused cell keeps paper-trading so it can recover; those trades are stamped
`Trade.cellStatusAtEntry = 'PAUSED'` (the test book) and it returns to `TESTING` after a full
window of new trades averaging above +0.05R. `GET /api/configs/scorecard` returns, per cell,
the status and reason, the live record, main-book and test-book totals, and the latest
backtest. `infra/scripts/e2e-smoke.sh` exercises all of this against a throwaway database.

**Data checks.** `apps/engine/data_checks.py` guards the candles everything else is built on.
- *When candles are stored* (`routers/history.py::fetch_and_store`): rows that cannot be real
  (missing values, zero or negative prices, a high below the open or close, intraday bars
  outside 09:15–15:30, repeated timestamps) are left out and counted in the fetch result.
- *Re-scaled history:* if re-fetched closes no longer line up with stored ones, the source has
  adjusted its history for a split or dividend; the stored series is replaced in full instead
  of being stitched across two scales.
- *Price jumps:* a daily move above 20% must be listed in `config/known_price_actions.json` as
  a `real_move` or a `demerger`. A stock with an unlisted move gets `Stock.dataFlag`.
- *Demergers:* the data source does not adjust for them, so earlier prices are scaled by the
  size of the step whenever history is loaded (backtests and the live scanner).
`python tools/check_data.py` reports on every stock and refreshes the flags.

**AI analysis.** Every AI call (market overview, stock, sector and indicator write-ups) goes
through the owner's AI router, an OpenAI-compatible gateway on work-pc that tracks which free
models are answering. The engine's only AI code is `apps/engine/ai_client.py`: it posts to
`AI_ROUTER_URL` with `AI_ROUTER_KEY` and model `auto`, and turns every failure into a
plain-words notice. There are no provider keys or fallback loops in this app.

**Telegram digests.** `apps/api/src/reports/` sends a daily digest at 15:45 IST on weekdays
and, on Fridays, the week (15:50) and everything since the start (15:55). Figures are after
costs; trades opened while a cell was paused are reported as the test book, apart from the
main book; the period's status changes are listed. Each digest is claimed in the
`SentDigest` table before sending, so a restart cannot send a second copy.
`GET /api/reports/digest-preview?period=…` returns what would be sent without sending it.
The pure logic (when a digest is due, the period, the wording) is in `reports/digest.ts`.

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
