# SmartTrader — System Review & Diagnosis

**Date:** 2026-06-07
**Reviewer:** Codebase audit (read-only — no code changed)
**Scope:** `apps/engine` (Python/FastAPI), `apps/api` (NestJS/Prisma), `apps/frontend` (React/Vite), infra (`docker-compose*`, Prisma migrations)
**Branch reviewed:** `add-new-strategies-and-optimise-the-old-strategies`

---

> **🟢 RESOLUTION STATUS (branch `roadmap-v2`):** Most Critical/High findings below
> are **fixed and verified** in the isolated v2 worktree against a DB clone — see
> [roadmap-implementation.md](roadmap-implementation.md) for the per-finding record.
> Quick map: **C1/C5** secrets → env (you must still rotate); **C2** auth added
> (API + engine + socket); **C3/H4/H5/H6** backtest realism (intrabar fills, costs,
> risk sizing, no ROI-sort, IST tz); **C4/M1/M2/M5** P&L logic fixed; **H1** Decimal
> money; **H2** transactions + unique index; **H3** migration committed; **H7**
> frontend URL centralized; **H8** DB creds parameterized; **H9** 3-phase exit +
> reconciliation; **M6/M8/M9** cache, WS breadth, tests+CI. New analytics:
> walk-forward, Monte-Carlo, portfolio risk engine. Still open: broker integration,
> regime detection, 2nd data source, multi-user, strategy-builder UI.

## 1. Executive Summary

SmartTrader is a well-featured, ambitious zero-cost algorithmic trading scanner for NSE: 28 strategies, a backtesting suite, a 3-phase trailing/partial-exit engine, live scanning with Telegram + WebSocket alerts, AI market commentary, and a rich React dashboard. As a personal/research tool it is genuinely impressive in surface area.

However, the review surfaced issues that fall into three buckets that matter most:

1. **Security posture is effectively "open + leaked"** — no authentication anywhere, and a live Telegram bot token is committed in `docker-compose.yml` / `docker-compose.prod.yml` and is in git history. LLM API keys sit in plaintext in the engine working tree behind unauthenticated, paid endpoints.
2. **Backtest results are very likely optimistic / not trustworthy** — the backtest engine checks stop-loss/target against the bar **Close** (not intraday High/Low), models **no slippage or commission**, ignores **position sizing by risk**, and the all-stocks endpoint **sorts by ROI** (cherry-picking). Numbers shown in the UI should not be treated as realistic until these are fixed.
3. **Financial bookkeeping has silent correctness bugs** — money is stored as `Float`, multi-step signal/trade writes are non-transactional with a TOCTOU dedup race, the no-price `close()` path records **every such close as breakeven (₹0 P&L)**, and `manualClose` / `pnlPercent` semantics diverge between code paths.

None of these block a single-user, localhost, paper-trading use case — but every one of them blocks "trusting the numbers" or "exposing this beyond localhost." The rest of this document is the detailed diagnosis plus a prioritized improvement and feature roadmap.

**Overall maturity:** strong prototype / advanced personal project. Not production-grade for multi-user or real-capital use without the Critical/High items addressed.

---

## 2. System Overview (as-built)

```
React/Vite (5173)  ──REST + Socket.io──►  NestJS API (3000)  ──HTTP──►  Python FastAPI engine (8000)
                                                │                              │
                                                └────────► PostgreSQL (5470) ◄─┘  (SQLAlchemy)
                                          Telegram Bot ◄──┘
Standalone:  scanner/live_scanner.py  (polls yfinance every ~100s during market hours)
```

- **Engine** owns market data (yfinance → Postgres `HistoricalData`), backtests, AI commentary, and the live scanner loop / 3-phase exit logic. The scanner is a separate process that talks to the API over HTTP (not direct DB writes for trades).
- **API** owns signals → trades auto-sync, P&L, portfolio stats, risk sizing (2% rule), WebSocket broadcast, Telegram alerts, and proxies the engine.
- **Frontend** is page-per-feature, each page self-fetching over REST + one socket hook.

**Component verdicts:** Engine — feature-rich but the backtest math and timezone handling are suspect. API — clean structure but missing transactions/auth and has divergent P&L paths. Frontend — good UX surface, but hardcoded `localhost:3000` in 10+ files makes the production build non-functional against any non-local backend.

---

## 3. Findings by Severity

Severity = impact × likelihood for the intended use. `file:line` references included for traceability.

### 🔴 CRITICAL

| # | Finding | Location |
|---|---------|----------|
| C1 | **Live Telegram bot token committed** in compose files and in git history. Treat as fully compromised — rotate immediately. | `docker-compose.yml:32-33`, `docker-compose.prod.yml:30-31`, git commit `31666a8` |
| C2 | **No authentication / authorization anywhere** — every REST endpoint and the Socket.io gateway is open. Destructive ops (`DELETE /api/trades/:id`, `DELETE /api/stocks/:id`, signal injection via `POST /api/signals/new`) and **paid LLM endpoints** are callable by anyone who can reach the port. | `apps/api/src/**` (no guards), `engine/routers/analysis.py` |
| C3 | **Backtest SL/TP checked against `Close` only**, never intraday High/Low — exits are delayed/optimistic and disagree with the live `simulate_trailing.py` (which uses low/high). Combined with **no slippage/commission**, every `BacktestReport` is optimistically biased. | `engine/strategies/base.py:50-55` |
| C4 | **No-price `close()` always books breakeven (₹0 P&L).** Any trade closed without an explicit exit price is silently recorded as BREAKEVEN regardless of reality → corrupt P&L history. | `apps/api/src/signals/signals.service.ts:118-149` |
| C5 | **Plaintext live LLM keys** (OpenRouter + Gemini) in the engine working tree, used by unauthenticated endpoints that spend real credits (DoS-of-wallet). | `apps/engine/.env:3-4`, `engine/routers/analysis.py` |

### 🟠 HIGH

| # | Finding | Location |
|---|---------|----------|
| H1 | **Money stored as `Float`** (IEEE-754) across all price/P&L columns — should be `Decimal`/`NUMERIC`. Rounding error accumulates, especially over partial-exit sums. | `apps/api/prisma/schema.prisma:106-123` |
| H2 | **Non-transactional signal+trade creation + TOCTOU dedup race.** No DB unique constraint on active `(stockId, strategyName)`; concurrent POSTs create duplicate signals/trades; a trade-create failure orphans the signal with no rollback. | `signals.service.ts:33-89` |
| H3 | **Prisma migration drift.** No migration creates the `Trade` table; `LiveSignal.holdDuration` and the changed `ActiveConfiguration` unique constraint aren't migrated. DB was shaped via `db push`. Migrations are not a source of truth. | `apps/api/prisma/migrations/*` vs `schema.prisma` |
| H4 | **No position sizing by risk in the backtest.** SL distance is computed but unused; each trade deploys `min(capital, 100000)`, so "2R targets" don't map to consistent rupee risk. Backtest risk profile ≠ live (API sizes at 2%/₹2,000). | `engine/strategies/base.py:48`; cf. `signals.service.ts:58-66` |
| H5 | **`run-strategy-all-stocks` sorts results by ROI desc** — structurally encourages survivorship/overfitting (cherry-pick the best historical performer). Universe also only contains surviving listed names. | `engine/routers/backtest.py:147,167` |
| H6 | **Intraday timezone handling is unreliable.** yfinance intraday timestamps are stored naively (`strftime`), dropping tz; session-dependent strategies (ORB, VWAP, CPR) may use mis-aligned bars. Entry-bar location in `simulate_trailing.py` relies on brittle UTC-localize + price-match fallbacks. | `engine/routers/history.py:43`, `engine/scanner/simulate_trailing.py:158-179` |
| H7 | **Frontend hardcodes `http://localhost:3000` in 10+ files** (plus two files using a conflicting `VITE_API_URL`+`/api` convention). The Docker/nginx production build serves static JS that still points at localhost → **effectively broken off-localhost**. | `apps/frontend/src/**` (Dashboard, Portfolio, LiveScanner, useSocket, …) |
| H8 | **DB credentials are `trader:trader` hardcoded** in every compose file and committed README, including the prod compose. | `docker-compose*.yml`, `README.md:40,125` |
| H9 | **3-phase trailing exit can cascade INITIAL→PHASE2→PHASE3 in a single poll** (book ~70% at one price) and the partial-close PATCH is fire-and-forget (no failure reconciliation → scanner/DB state desync). The `qty >= 3` gate silently disables partials for small positions. | `engine/scanner/live_scanner.py:367-396` |

### 🟡 MEDIUM

| # | Finding | Location |
|---|---------|----------|
| M1 | **`pnlPercent` means different things in different paths** — "return on capital" (`signals.service`) vs "price move %" (`trades.service.manualClose`). Dashboard mixes semantics. | `signals.service.ts:140,269` vs `trades.service.ts:184` |
| M2 | **`manualClose` ignores partial exits** — uses full original `quantity`, ignores `realizedPnl`/`remainingQty` → double-counts shares. | `trades.service.ts:183` |
| M3 | **No-price-validation on mutating endpoints** — `@Body() body: any`, `Number(body.exitPrice)`, unclamped `percent`, untyped engine-proxy passthrough (SSRF-ish: unvalidated `symbol` interpolated into engine URLs). | `signals.controller.ts:61,92,129`, `engine.controller.ts` |
| M4 | **`signalType`/`holdDuration` unconstrained** in DTOs (anything not `"BUY"` is treated as SELL); trade `holdDuration` falls back to undocumented `"UNKNOWN"`. | `create-signal.dto.ts:11-13`, `signals.service.ts:75` |
| M5 | **Division-by-zero / NaN risks** — `pnlPercent` divides by `capitalUsed` (default 0); Telegram RR divides by `(entry - SL)` with no guard. Several strategies don't guard `target == entry` or `entry == 0`. | `signals.service.ts:140`, `telegram.service.ts:46-49`, `engine/strategies/base.py:54` |
| M6 | **Row-by-row OHLCV upsert** (thousands of single INSERTs per fetch) and **no yfinance caching** — `/sectors` makes 8 sequential Ticker calls, `/news` 5, every chart/indicator call re-hits yfinance live. | `engine/routers/history.py:42-56`, `engine/routers/analysis.py:256` |
| M7 | **Backtests run fully serial inside one request**, blocking the worker; `ProcessPoolExecutor` parallelism was explored in `test/` but never wired in. `load_historical` re-queried per strategy (N+1). | `engine/routers/backtest.py:105-150`, `engine/test/*` |
| M8 | **WebSocket emits only `NEW_TRADE_ALERT`.** Trade closes, partial exits, SL trails, and reversals go to Telegram but **not** the socket → the dashboard can't react in real time and must poll. | `signals.gateway.ts:38`, `signals.service.ts` |
| M9 | **No tests of correctness anywhere.** Engine `test/` are ad-hoc timing benchmarks with no assertions; frontend has zero tests; no CI. The most bug-prone code (3-phase exit, `detect_reversal`, `run_backtest`) is untested. | `engine/test/*`, repo-wide |
| M10 | **CORS / origins hardcoded to localhost**, no env-driven config; `credentials:true` is pointless without auth. | `apps/api/src/main.ts:8-11`, `engine/main.py:20` |
| M11 | ✅ **RESOLVED** — capital model now enforces a buying-power funding gate at entry: a trade is FUNDED only if its margin (`notional ÷ leverage`, INTRADAY 5× / delivery 1×) fits remaining cash **and** total open heat stays ≤ 6%; otherwise it's a SHADOW trade (tracked, excluded from portfolio ROI). `GET /api/trades/risk` reports margin used / available cash; portfolio ROI is funded-only. | `common/risk.ts`, `signals.service.ts:create`, `trades.service.ts:getRiskMetrics` |

### 🟢 LOW / Cleanup

- **Dead code:** `engine/scanner/live_scanner.py:34-41` trailing config (`BREAKEVEN_THRESHOLD`, `PROFIT_LOCK_*`, `trailing_state_cache`) defined, printed in the startup banner, but never used — and the banner describes a "Profit Lock 40%" system that **does not exist** in the code (docstring/code mismatch, `live_scanner.py:1-7`). Frontend `nx-welcome.tsx` (857 lines, never imported), `app.module.css` (orphaned), redundant `styles.css` `<link>`. API `app/` Hello controller not registered; `telegram.service.sendReversalAlert` never called.
- **Heavy duplication:** `detect_reversal`, `fetch_intraday_candles`, `get_stock_id`, `.NS` suffixing, yfinance period/interval maps duplicated across engine files; `isMarketOpen()` duplicated in `Navbar.tsx` and `LiveScanner.tsx`; `HOLD_LABELS`/badge maps re-declared in 4 pages and rebuilt inside `.map` per row (`LiveScanner.tsx:291-372`).
- **Broad exception swallowing:** `except: pass` in `backtest.py:121,163`, silent `.catch(() => {})` in `LiveScanner/Sectors/SectorDetail`, `remove()` ignoring delete errors (`trades.service.ts:209`).
- **A11y/UX gaps:** clickable `<div>`s with no keyboard/ARIA, modal without focus trap/Escape, no `*` 404 route, no error boundary, inconsistent destructive-action confirmations, dev instruction ("run `python … live_scanner.py`") leaking into production UI (`LiveScanner.tsx:256`).
- **Frontend `package.json` not self-describing** — imports `framer-motion`/`lucide-react` only declared in the root package.
- **No list virtualization** anywhere (Portfolio journal, SectorDetail grids of animated cards); 10s Portfolio price poll re-renders the whole un-memoized table.

---

## 4. "Odd Things" Worth Calling Out

These are the items most likely to surprise a new maintainer:

1. **The startup banner lies.** `live_scanner.py` prints a "Profit Lock 40% / Breakeven" framework that the actual loop never executes (it does breakeven + candle-low trail + reversal instead). README §"Live Alert Flow" repeats the 35%/40% framing. Documentation and code disagree about the core exit logic.
2. **Two backtest engines disagree.** `base.py` (SL/TP on Close) vs `simulate_trailing.py` (SL/TP on low/high). The "official" backtest is the more optimistic one.
3. **Closing a trade without a price erases its P&L** (records breakeven). Easy to trigger and silently corrupts portfolio stats.
4. **The all-stocks backtest sorts by ROI** — a built-in overfitting magnet presented as a feature.
5. **Migrations don't create the `Trade` table** that the entire portfolio depends on. The schema only exists because someone ran `db push`. A fresh `prisma migrate deploy` would produce a different DB than production.
6. **The "peak price" sent during trailing isn't a peak** — it's just the latest price (`live_scanner.py:373`), so the `peakPrice` column semantics are wrong.
7. **Frontend ships `localhost:3000` to the browser** — the nginx production image serves a bundle that calls the developer's localhost, not the server it's deployed on.
8. **`pandas_ta` imported in the middle of `analysis.py`** (after a route definition) — a tell of incremental hacking.
9. **`qty >= 3` magic gate** means 1–2 share positions silently never partial-exit, behaving differently from larger ones.

---

## 5. Suggestions (prioritized, non-feature)

### Now / this week (Critical & High)
1. **Rotate the Telegram bot token and both LLM keys.** Move all secrets to untracked env/secret store; strip them from `docker-compose*.yml` and purge from history (or accept rotation as the mitigation). Parameterize DB credentials.
2. **Add an auth layer** even if single-user: a static API key / bearer token guard on the NestJS API and a shared-secret header on the engine, plus socket auth. Rate-limit the LLM endpoints.
3. **Fix the backtest fill model:** evaluate SL/TP against bar High/Low, model slippage + Indian costs (STT, brokerage, exchange/SEBI fees, GST), and add risk-based position sizing so backtest matches the live 2% rule. Until then, **label existing `BacktestReport` numbers as "gross/optimistic" in the UI.**
4. **Fix `close()`** to compute a real exit (or require an exit price); reconcile `pnlPercent` and `manualClose` to one partial-aware formula. Add a regression test per close path.
5. **Wrap signal+trade writes in a Prisma `$transaction`** and add a partial unique index for active `(stockId, strategyName)` to kill the dedup race.
6. **Reconcile Prisma migrations** with the live schema (generate a baseline migration that includes `Trade`, `holdDuration`, and the `ActiveConfiguration` constraint). Add `datasource.url`.
7. **Centralize the frontend API/socket base URL** into one env-driven module; reconcile the `/api` path convention; make the nginx build read runtime config.

### Soon (Medium)
8. Convert money columns to `Decimal`; round only at display; guard all divide-by-zero.
9. Add a yfinance caching layer (TTL) and batch the OHLCV upsert (`executemany`/`COPY`); load each timeframe once per backtest run.
10. Normalize all timestamps to IST (or store UTC consistently) at ingestion; add a test asserting ORB/VWAP bars align to NSE session.
11. Broaden WebSocket events (close/partial/trail/reversal) so the dashboard is fully real-time and can drop polling.
12. Harden the 3-phase exit: idempotent phase transitions, verify PATCH success before mutating in-memory state, make the `qty` gate and thresholds configurable, and dedupe per-symbol fetches within a cycle.
13. Validate all mutating DTOs (`@IsIn`, numeric bounds, clamp `percent ≤ 1`); validate `symbol` before interpolating into engine URLs.

### Hygiene (Low)
14. Delete dead code (`nx-welcome.tsx`, unused trailing config, Hello controller, orphan CSS); extract the duplicated helpers (`detect_reversal`, `.NS` suffix, market-open, hold-label maps) into shared modules.
15. Replace silent catches with surfaced errors; add an error boundary + `*` route; add ARIA/keyboard support to clickable cards and the modal.
16. Stand up minimal CI: pytest for engine SL/TP invariants + trailing state machine, Jest for API P&L math, vitest smoke tests for the frontend.

---

## 6. New Feature Ideas — "Next Level"

Grouped by theme; ordered roughly by leverage. These assume the Critical/High correctness items above are addressed first (otherwise features build on untrustworthy numbers).

### A. Make the numbers trustworthy & explainable
- **Realistic cost & slippage model** as a first-class, configurable layer (per-broker fee schedules, bid/ask slippage, partial-fill probability). Show "gross vs net" everywhere.
- **Walk-forward & out-of-sample backtesting** — split train/validate windows, rolling re-optimization, and report degradation. Directly counters the current ROI-sort overfitting.
- **Monte Carlo / bootstrap on the trade sequence** — distribution of drawdowns and ROI, not a single number; show 5th/50th/95th percentile equity curves.
- **Per-trade "why" panel** — render the exact indicator values and the candle that triggered each signal (audit trail), so signals are explainable and debuggable.

### B. Risk & portfolio intelligence
- **Portfolio-level risk engine** — max concurrent exposure, max heat (sum of open risk), per-sector concentration caps, correlation-aware sizing, daily loss-limit kill-switch.
- **Regime detection** — tag the market (trending/range/high-vol via ADX/VIX-India) and auto-enable/disable strategies per regime; show which strategies historically work in the current regime.
- **Strategy allocator / meta-model** — rank strategies by recent rolling performance and route capital dynamically (a simple bandit/score-weighted allocator).

### C. Execution & broker integration
- **Broker API integration** (Zerodha Kite / Dhan / Upstox) — start with **paper-trading parity** (mirror live signals into a simulated broker account), then optional real order placement behind explicit confirmation + 2FA. This is the single biggest "next level" jump.
- **Order management layer** — bracket/OCO orders, retry/idempotency, reconciliation between intended trades and broker fills.
- **Pre-market & post-market workflows** — auto square-off for INTRADAY at 15:15, EOD reconciliation report.

### D. Data & signal quality
- **Second data source + cross-validation** (NSE bhavcopy / a paid feed) to reduce yfinance dependency, fix tz reliability, and handle corporate actions (splits/bonus) and survivorship (historical constituents).
- **Adjusted-price handling** for splits/dividends so backtests don't show fake gaps.
- **Alternative-data signals** — options OI / PCR, FII-DII flows, delivery %, India VIX as features/filters.

### E. Observability & ops
- **Structured logging + metrics dashboard** for the scanner (cycle time, fetch failures, signals/hour, PATCH failures) — currently failures are swallowed and invisible.
- **Health/heartbeat + alerting** — Telegram alert if the scanner stalls, yfinance rate-limits, or a poll exceeds the interval.
- **Audit log** of every trade-state transition (immutable), so portfolio history is reconstructible.

### F. UX & product
- **Multi-user with auth + per-user portfolios** (depends on auth + rooms in the gateway).
- **Strategy builder UI** — compose/parameterize strategies (indicator + condition blocks) without code; persist as `ActiveConfiguration` variants.
- **Backtest comparison & leaderboard with guardrails** — compare strategies on risk-adjusted metrics (Sharpe, Sortino, Calmar, expectancy, max DD) rather than raw ROI; flag overfit candidates.
- **Mobile-responsive + PWA push** so alerts reach the phone without Telegram.
- **Trade journal enrichment** — screenshots of the setup chart, tags, notes, and a post-mortem "would this have hit SL intrabar?" replay.

### G. Intelligence layer (build on the existing AI commentary)
- **Signal-quality scoring with an LLM/ML model** that incorporates the explainability panel + regime + recent performance to assign a confidence score per alert.
- **Natural-language portfolio Q&A** ("why did strategy X underperform last month?") over the structured trade data.

---

## 7. Suggested Roadmap

| Phase | Theme | Items |
|-------|-------|-------|
| **0 — Stop the bleeding** | Security & trust | Rotate secrets; add auth + rate limits; parameterize DB creds |
| **1 — Trust the numbers** | Backtest correctness | High/Low SL-TP, costs/slippage, risk sizing, drop ROI-sort, label gross/net, tz normalization |
| **2 — Trust the books** | Financial integrity | Decimal money, transactions + unique index, fix `close()`/`manualClose`/`pnlPercent`, migration baseline |
| **3 — Harden ops** | Reliability | Idempotent 3-phase exit, PATCH reconciliation, broaden WS events, yfinance cache/batch, structured logging + heartbeat, tests + CI |
| **4 — Level up** | Features | Walk-forward/Monte-Carlo, portfolio risk engine, broker paper-trading parity, regime detection, second data source |
| **5 — Product** | Scale & polish | Multi-user, strategy builder UI, risk-adjusted leaderboard, PWA push, a11y |

---

*This document is diagnosis and recommendation only. No application code was modified during this review. `file:line` references reflect the state of branch `add-new-strategies-and-optimise-the-old-strategies` as of 2026-06-07.*
