# Roadmap Implementation Record (branch `roadmap-v2`)

This documents what was actually built against the [system review](system-review-2026-06.md),
phase by phase, with verification status. All work was done in the **isolated v2
worktree** against a **clone of the live database** so the running stack was never
touched (see [v2-environment.md](v2-environment.md)).

**Verified live:** every "✅ verified" item below was exercised end-to-end against
the cloned DB on the running v2 stack (API :3001, engine :8001, DB :5471).

---

## Phase 0 — Security ✅

| Item | What changed | Status |
|------|--------------|--------|
| Secrets out of compose | `docker-compose.yml` / `docker-compose.prod.yml` now read all secrets from a gitignored root `.env` (template: `.env.example`). DB creds parameterized. | ✅ |
| API auth | Global `ApiKeyGuard` on NestJS (header `x-api-key` / `Bearer`), opt-in via `API_KEY` (no-op when unset). `Public()` decorator for exceptions. | ✅ 401 without key, 200 with key |
| Engine auth | FastAPI `require_api_key` dependency on all routers; `/health` stays public. | ✅ 401/200 verified |
| Rate limiting | In-memory `ThrottleGuard` (API) + per-IP `RateLimiter` on the paid LLM routes (engine). | ✅ |
| Service-to-service keys | Engine proxy, scanner→API, frontend→API all forward the key. | ✅ |
| Frontend API URL | 10+ hardcoded `localhost:3000` centralized into one env-driven `config.ts`; Docker bakes `VITE_API_URL`/`VITE_API_KEY`. | ✅ |
| CORS | Env-driven (`CORS_ORIGINS`) on API, gateway, engine. | ✅ |
| Telegram kill-switch | `TELEGRAM_ENABLED=false` so the clone can't double-alert. | ✅ |

> **User action still required:** rotate the leaked Telegram + LLM keys (they're in
> git history). Code no longer hard-codes them. *(Gemini key already rotated.)*

## Phase 1 — Backtest correctness ✅

| Item | What changed | Status |
|------|--------------|--------|
| Intrabar fills | `strategies/base.py` now checks SL/TP against each bar's **High/Low**, not close; entry on **next bar open**; pessimistic tie-break when a bar straddles both. | ✅ unit-tested |
| Costs + slippage | New `backtest_config.py` models Indian costs (brokerage, STT, exchange, SEBI, stamp, GST) per intraday/delivery profile + slippage bps. Reports **gross vs net**. | ✅ |
| Risk-based sizing | Each trade sized so SL distance risks a fixed % of capital (matches the live 2% rule), capped no-leverage. | ✅ |
| Drop ROI cherry-pick | `run-strategy-all-stocks` no longer ranks by raw ROI; sorts by profit factor + ships a disclaimer. | ✅ |
| Richer metrics | profitFactor, expectancy, avgWin/Loss, maxDrawdownPct, skippedInvalid. | ✅ |
| Timezone | yfinance timestamps normalized to **IST** at ingestion (`history.py`); fixes session-aware strategies (ORB/VWAP/CPR). | ✅ |
| Batched upsert | Row-by-row OHLCV insert replaced with a single batched `executemany`. | ✅ |

*Effect:* backtests are now appropriately less rosy. Golden_Cross/VCP on ADANIENT
show net losses after realistic fills+costs.

## Phase 2 — Financial integrity ✅

| Item | What changed | Status |
|------|--------------|--------|
| Decimal money | Ledger columns (LiveSignal + Trade prices/P&L) migrated `Float → NUMERIC(18,4)`. Migration SQL committed; applied to the clone. | ✅ |
| Decimal serialization | Global interceptor coerces Prisma `Decimal` → `number` in all responses (frontend untouched). | ✅ numbers, not strings |
| `close()` bug | No longer books silent breakeven — fetches the live price and computes real P&L; loud fallback only if the quote genuinely fails. | ✅ real exit price + WIN/LOSS |
| `manualClose()` | Now partial-exit aware (uses realizedPnl + remainingQty) and uses the same `% of capital` semantics as `closeWithPrice`. | ✅ |
| Transactions | Signal+Trade create, closes, SL updates wrapped in `$transaction`. | ✅ |
| Race fix | Partial-unique index `(stockId, strategyName) WHERE status='ACTIVE'`; create() handles P2002. | ✅ duplicate POST → 1 row |
| DTO validation | `signalType`/`holdDuration` constrained with `@IsIn`. | ✅ |
| Div-by-zero | `safePct` helper; Telegram RR guarded. | ✅ |

## Phase 3 — Ops hardening ✅

| Item | What changed | Status |
|------|--------------|--------|
| 3-phase exit fix | Transitions gated on the poll's *original* state with `elif` — a poll advances **at most one phase** (was cascading 70% out at one price). | ✅ |
| PATCH reconciliation | `book_partial`/`close_trade` check the HTTP result; SL/state only advance if the partial actually succeeded (else retried next poll). | ✅ |
| WebSocket breadth | Gateway emits `TRADE_UPDATE` (CLOSED / PARTIAL / SL_UPDATED) — previously only NEW_TRADE_ALERT. | ✅ |
| yfinance cache | TTL cache for live-prices (20s) + chart-data (60s). | ✅ 1464ms → 0ms |
| Heartbeat | Scanner logs per-cycle timing + stall warning; misleading "Profit Lock" banner corrected to the real 3-phase system. | ✅ |
| Tests + CI | `test/test_backtest_engine.py` (5 passing) + GitHub Actions CI (engine pytest, API build, frontend build). | ✅ 5 passed |

## Phase 4 — Features (core delivered) 🟡

| Item | What changed | Status |
|------|--------------|--------|
| Walk-forward | `POST /api/engine/run-walk-forward` — rolling out-of-sample folds, % profitable folds, OOS ROI mean/std, consistency flag. | ✅ verified |
| Monte-Carlo | `POST /api/engine/run-monte-carlo` — bootstraps the trade sequence; ROI & max-drawdown percentiles + probability of profit. | ✅ verified |
| Portfolio risk engine | `GET /api/trades/risk` — open exposure, total heat, per-sector concentration, over-exposure flags. | ✅ verified |
| Broker paper-trading parity | **Built (data layer).** Free **DhanHQ** adapter (`brokers/dhan.py`) + Upstox alternative (`brokers/upstox.py`) behind a facade (`brokers/__init__.py`) with **automatic yfinance fallback**. Wired into `/live-prices` + the scanner; diagnostics at `/api/engine/broker/status` & `/probe/{symbol}`. Paper fills stay simulated (no real orders). Setup: [dhan-paper-trading.md](dhan-paper-trading.md). | ✅ facade + fallback verified (Dhan calls need your token to test) |
| Regime detection | **Not built** — ADX/India-VIX regime tagging + per-regime strategy gating. Designed as next step. | ⬜ |
| Second data source | **Not built** — NSE bhavcopy / paid feed + corporate-action adjustment. Designed as next step. | ⬜ |

## Phase 5 — Product ✅ (multi-user intentionally swapped for single-user PIN)

| Item | Status |
|------|--------|
| **App PIN auth** (replaces multi-user) — `POST /api/auth/login` exchanges the PIN for the API key; the key is **never baked into the bundle** (verified 0 occurrences); `AuthGate` lock screen wraps the app. Set `APP_PIN`. | ✅ verified |
| **Analytics UI panels** — `🔬 Validate` modal (walk-forward + Monte-Carlo per stock) on the strategy page; **Risk Engine** tab on Portfolio (exposure/heat/sector concentration/flags). | ✅ verified |
| **Risk-adjusted leaderboard** — `GET /api/engine/leaderboard` (ROI ÷ drawdown × confidence) + 🏆 table on the Backtesting page. | ✅ verified |
| **Regime detection** — `GET /api/engine/regime[/symbol]` (ADX/ATR → TRENDING/RANGING/VOLATILE + playbook) + navbar regime chip. | ✅ verified |
| **Strategy Builder** — `🧩 Builder` page: compose indicator/condition rule blocks → `POST /api/engine/custom-backtest` runs them through the realistic engine; specs saved to localStorage. | ✅ verified |
| **Settings UI** — `⚙️ Settings`: data-source status + paste-to-refresh Dhan token (no restart). | ✅ verified |
| **PWA** — installable manifest + service worker (offline shell; API never cached) + in-app browser notifications on new trade alerts. | ✅ built |
| **a11y / robustness** — error boundary, `*` 404 route, keyboard-accessible cards, ARIA labels (representative pass; not exhaustive). | ✅ built |
| Multi-user auth | ⬜ intentionally skipped — single-user app, replaced by the PIN gate above. |

## Second data source / corporate actions

- **Live** market data now has a real second source: **DhanHQ** (free) replaces
  unofficial yfinance for live quotes when a token is set, with yfinance fallback.
- **Historical** stays on yfinance, which returns **split/dividend-adjusted**
  candles (auto-adjust), so backtests don't show fake gaps on corporate actions.
- Remaining (future): a survivorship-bias-free historical source (NSE bhavcopy /
  paid feed incl. delisted names). Dhan historical is paid, so it's left off.

---

## What remains (honest next steps)

1. **Wire the new analytics into the UI** — a Backtesting tab panel for walk-forward
   + Monte-Carlo, and a Portfolio "Risk" panel for `GET /api/trades/risk`. The
   APIs exist; only the React views are missing.
2. **Broker paper-trading parity** — mirror live signals into a simulated broker
   account first; real order placement behind explicit confirmation later.
3. **Regime detection + second data source** — the highest-value remaining
   "trust" features after walk-forward/Monte-Carlo.
4. **Phase 5 product layer** — multi-user, strategy builder, PWA, a11y.

## How to run / promote

See [v2-environment.md](v2-environment.md). To promote: validate, merge `roadmap-v2`,
rebuild the live stack, and `git worktree remove ../smart-trading-v2`. Before
exposing beyond localhost, rotate secrets and set a strong `API_KEY`.
