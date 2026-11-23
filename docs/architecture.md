# Smart Trading: architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      Docker Compose                         │
│  scanner and scheduler run the engine image as two more     │
│  containers; they talk to the api and the database.         │
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
- Pages: Dashboard, Live Scanner, Portfolio, Scorecard, News, Sectors, Backtesting, Builder, Settings

### NestJS Backend (`apps/api`) — Port 3000
- Prisma ORM, Socket.io WebSocket gateway
- Modules: Stocks, Configs (with the cell lifecycle), Signals, Trades, Reports (Telegram digests), Dhan (real money, off by default), Telegram, Engine proxy, Prisma

### Python Engine (`apps/engine`) — Port 8000
- FastAPI, pandas-ta, yfinance, SQLAlchemy
- Handles data fetching, backtesting, live scanning

### PostgreSQL — Port 5470
- Schema: Stock, HistoricalData, BacktestReport, ActiveConfiguration, LiveSignal, Trade, SentDigest, DhanPosition, DhanDailyState, DhanToken
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
PATCH      /api/signals/:id/close        # needs a real price: the one sent, or the live quote
GET        /api/configs/scorecard        # every cell: status, live record, books, backtest
POST       /api/configs/:id/live         # the owner's real-money switch for a Proven cell
GET        /api/dhan/status              # real-money mode and today's counters
GET        /api/reports/digest-preview   # what the Telegram digest would say
```

## Nx Workspace Layout

```
smart-trading/
├── apps/
│   ├── frontend/     React + Vite
│   ├── api/          NestJS + Prisma
│   └── engine/       Python FastAPI
├── config/           trading.json (shared settings), known_price_actions.json
├── infra/            docker-compose.yml used on work-pc, nginx, landing page, scripts
├── docs/
├── docker-compose.yml   local development only
└── nx.json
```

---

## How it works

**Security layer.** Every HTTP request and socket handshake passes an opt-in
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
by a per-trade risk cap of `cellCapital × leverage × RISK_PER_TRADE_PCT`: 2% of what the
trade may deploy, so ₹200 for swing and ₹1,000 for intraday on a ₹10k fund (the owner's rule
since 2026-11-19; before that it was 2% of the fund for both). Real-money orders keep their own, separate limit (`DHAN_MAX_RISK`, ₹200):
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
open, costs and slippage charged (per share and side: the larger of one ₹0.05 tick and 5 basis points). Live: entry at the live quote when the signal is
found, stop-outs at the worse of stop and live price, P&L booked after costs. Entry limits
(`apps/engine/entry_limits.py`) and intraday exit rules (`apps/engine/intraday_exits.py`) are
single modules imported by both paths. INTRADAY entries are opened only between 09:30 and
15:00 and never on a candle from an earlier day (`intraday_entry_time_ok`, also in
`entry_limits.py`).

**Replay test.** `apps/engine/test/test_replay_parity.py` runs the scanner's own entry and
exit functions over a candle series (network, clock and API replaced by `test/replay.py`)
and compares the trades with `simulate()` on the same candles. Entries must be identical.
Exits must land on the same candle in at least 80% of trades and within one candle in 90%
(today: about 90% and 95%). It covers 15-minute and 5-minute strategies. When it was
written it found five rules that only one side had: the backtest opened trades at 15:00 and
15:15 that the scanner never takes; the scanner could act next morning on a signal from
yesterday's last candles; the scanner could enter at 09:30 on a 5-minute candle that had
completed at 09:20; the cost rule was judged on slightly different prices, so borderline
trades were dropped on one side only; and the 30-minute cooldown was counted from the exit
candle's start in the backtest, which let it re-enter a candle before live. All five are
fixed.

**One default for the swing time-stop.** The time-stop (exit a swing flat after 10, 20 or
40 days) is off. Until 2026-11-19 it was off only in the live containers' settings while
the code default was on, so a backtest run outside those containers used a rule live does
not have. The code default is now off as well.

Known remaining differences: live polls every 100 seconds, so a stop can be noticed late
(the backtest books the stop level); live moves through at most one exit phase per poll and
books partial exits at the price it sees, the backtest books them at the 50% and 75%
levels; a position of one or two shares still gets the breakeven stop and the trail live,
but not in the backtest.

**Cell lifecycle.** Every cell (`ActiveConfiguration`) has a `status` that the API sets from
the cell's own closed paper trades, after costs, measured in R (`common/lifecycle.ts`,
applied by `configs/lifecycle.service.ts` after every close and on
`POST /api/configs/evaluate`):

| Status | Meaning | Rule (defaults in `config/trading.json` → `lifecycle`) |
|---|---|---|
| `TESTING` | Collecting evidence | Default |
| `PAUSED` | Kept losing | Last 20 trades average below −0.15R, or the cell's fund (₹10,000 plus the result of all its closed trades) has fallen to ₹5,000. The fund rule acts on the trade that crosses it |
| `PROVEN` | Has earned trust | 40+ trades, average above +0.10R, profit factor 1.3+, positive in both halves |

A paused cell keeps paper-trading so it can recover; those trades are stamped
`Trade.cellStatusAtEntry = 'PAUSED'` (the test book) and it returns to `TESTING` after a full
window of new trades averaging above +0.05R. `GET /api/configs/scorecard` returns, per cell,
the status and reason, the live record, main-book and test-book totals, and the latest
backtest. `infra/scripts/e2e-smoke.sh` exercises all of this against a throwaway database.

**Real money (Dhan).** `apps/api/src/dhan/dhan.service.ts` places real intraday orders at the
Dhan broker. It is off by default (`DHAN_TRADING_MODE`). An entry needs two locks: the cell is
`PROVEN` and the owner switched it on (`ActiveConfiguration.liveEnabled`, set through
`POST /api/configs/:id/live`), and the stock has a broker id (`Stock.dhanSecurityId`). The
service sizes its own order, rests a stop at the broker, exits when the paper trade closes
and closes anything left at 15:12 IST. Entries and exits are separate: mode `off`, the
daily-loss limit or a cell leaving `PROVEN` stop new entries only. Positions, the day's
counters and the login token live in `DhanPosition`, `DhanDailyState` and `DhanToken`.
`signals.service.ts` calls it after a paper trade is created and after it is closed; a failure
there never affects the paper trade. See `docs/real-money-trading.md`.

**Market condition.** Every trade records the market's condition when it was opened
(`apps/engine/market_condition.py`): `regimeAtEntry` (NIFTY on daily bars: trending up,
trending down, ranging or volatile), `marketDirectionAtEntry` (the median roster stock's move
from its day open: UP above +0.15%, DOWN below −0.15%, else FLAT), `breadthAtEntry` (share of
stocks above their open) and `alignedWithMarket` (a buy in UP or a sell in DOWN). The scanner
reads the direction from the candles each scan already downloads and sends the labels with
the signal. Nothing is blocked on them yet: they exist so results can be compared by
condition before any switching rule is trusted.

**Data checks.** `apps/engine/data_checks.py` guards the candles everything else is built on.
- *When candles are stored* (`routers/history.py::fetch_and_store`): rows that cannot be real
  (missing values, zero or negative prices, a high below the open or close, intraday bars
  outside 09:15–15:30, repeated timestamps) are left out and counted in the fetch result.
- *Re-scaled history:* if re-fetched closes no longer line up with stored ones, the source has
  adjusted its history for a split or dividend; the stored series is replaced in full instead
  of being stitched across two scales.
- *Price jumps:* a daily move above 20% must be listed in `config/known_price_actions.json` as
  a `real_move`, a `demerger` or a `bonus`. A stock with an unlisted move gets `Stock.dataFlag`.
- *Demergers and bonus steps:* where the data source did not adjust its history, earlier
  prices are scaled by the size of the step whenever history is loaded (backtests and the
  live scanner).
`python tools/check_data.py` reports on every stock and refreshes the flags.

**Stock lists.** `apps/engine/universe.py` defines who is tested for what. Every active
stock is on the swing list and gets daily candles. Stocks with `Stock.intraday` set are also
on the intraday list: only they get 5- and 15-minute candles, and only on them are intraday
strategies tested and traded. Since 2026-11-23 the swing list is the NIFTY 500
(`config/universe/`) above a floor on the value traded per day; the intraday list is the
liquid stocks that move the most in a day. Both come from measurements of stored daily
candles (`Stock.tradedValueCr`, `dayRangePct`, `lastClose`), set by `tools/universe.py`
(`add`, `fetch-daily`, `measure`, `floor`, `intraday`). The scheduler, the luck check,
auto-select, the backtest tool and the per-strategy results all read the lists from there.
The scanner fetches intraday candles every pass but keeps a stock's daily candles for 30
minutes (), so a large swing roster does not slow the checks on open trades.

**Strategy map.** `apps/engine/strategy_map.py` answers "where does each strategy work?"
from the stored backtest of every cell. The daily luck check now stores every cell's
backtest (`BacktestReport`, with the average R of each half), so the map, the Scorecard and
the luck check read the same run. Per strategy: stocks tested, stocks profitable, the stocks
that meet the live rule, and a verdict: works broadly (profitable on 60% or more of the
stocks tested), works on some stocks, or no stock meets the rule.
`GET /api/engine/strategy-map`; shown on the Backtesting page with a per-stock lookup.

**The live rule.** `apps/engine/selection_rule.py` is the one rule that decides whether a
cell's backtest is good enough to go live (paper). On the backtest after costs: average per
trade above +0.10R; positive in both halves; at least 30 trades (intraday), 10 (swing) or 4 (long-hold strategies);
profit factor of 1.5; net profit at least twice the worst drawdown; total return of at least
10% of the fund; and, for swing, a strategy that passes the first luck test. Thresholds are in
`config/trading.json` under `selection`. Auto-select adds every cell that passes;
`run-strategy-all-stocks` returns each row's verdict and what it misses; the Set Live button
asks before putting a failing row live. A passing backtest only earns a place on the roster:
the cell's own paper trades decide whether it stays.

**Luck check.** `apps/engine/luck_check.py` backtests every strategy on every active stock,
pools each strategy's trades and works out the chance its result is luck, corrected for the
number tested, plus a stricter test against every try on record
(`config/research_trials_seed.jsonl` plus stored runs; the same strategy on the same engine
version counts once). The scheduler runs it after the daily fetch and stores it in
`LuckCheckRun`; `GET /api/engine/luck-check` returns the latest and
`POST /api/engine/luck-check/run` recomputes it (about a minute). The Backtesting page shows
it. `tools/backtest_all.py` uses the same `strategy_table`.

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
`scheduler/fetch_scheduler.py`) runs a **daily after-close** fetch of every
active stock so the backtest dataset grows over time — intraday (15m/5m) accumulates past
yfinance's ~60-day-per-request cap because `upsert_ohlcv` never deletes. Daily cadence is
deliberate: backtests only use completed bars, whole only after the 15:30 IST close. Shares
the `fetch_and_store()` core with `POST /api/engine/fetch-history`. Env: `FETCH_RUN_HOUR_IST`,
`FETCH_RUN_MINUTE_IST`, `FETCH_TIMEFRAMES`, `FETCH_ON_START`.
