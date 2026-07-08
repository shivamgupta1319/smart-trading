# Handoff / Resume Doc — Dhan Live Execution + v1 Hygiene

**Last updated:** 2026-07-08 (end of session, market closed)
**Branch:** `roadmap-v1` (all work committed here; not pushed to origin unless you push)
**Design reference:** [dhan-live-execution.md](dhan-live-execution.md) · [performance-review-2026-07.md](performance-review-2026-07.md)

---

## TL;DR — where we are

Two tracks in flight:
1. **Dhan real-money execution** — Stage 1 (**log mode**) is **live on work-pc and validated**. It logs the exact real orders it *would* place for EMA_RSI on HDFCBANK/ADANIENT, without touching money. Stages remaining: sandbox → live.
2. **v1 hygiene** — all 4 tasks (prune losers, symbol filter, swing time-stop, Telegram digest) are **done, deployed, and committed**. Prune + digest are verified live; the time-stop verifies at next market open.

**Nothing is trading real money.** `DHAN_TRADING_MODE=log` (no orders placed).

---

## System topology (how to touch things)

- **Live host:** `ssh work-pc` (user `work`). Compose project: `/home/work/workspace/smart-trading/infra` (NOT a git repo — pull-based).
- **Containers (v1):** `smart-trading-{api,engine,scanner,frontend,db}`. api→3000, engine→8000, db→5470.
- **DB access:** `ssh work-pc 'docker exec smart-trading-db psql -U trader -d smart_trading -c "…"'`
- **Deploy pipeline (FIXED this session):**
  - **Dev PC (here):** `./infra/scripts/build-and-push.sh [api|engine|frontend]` — builds + pushes as `shivam13gupta/*` via `DOCKER_CFG=$HOME/.docker-account2` (the default login `wisfluxp` can't push those repos).
  - **work-pc:** `cd /home/work/workspace/smart-trading/infra && docker compose pull <svc> && docker compose up -d <svc>` (scanner uses the engine image).

---

## Track 1 — Dhan real-money execution

### Deployed now (Stage 1, log mode)
- New `apps/api/src/dhan/dhan.service.ts` (+ `dhan.module.ts`), wired into `SignalsService.create()` (entry) and `closeWithPrice()`/`close()` (exit).
- Modes: `off | log | sandbox | live` (env `DHAN_TRADING_MODE`, currently **`log`**).
- Hard whitelist: **EMA_RSI only**, **HDFCBANK (securityId 1333) / ADANIENT (securityId 25)** only, qty ≤ 20, notional ≤ ₹12,500 (→ ~15 HDFC / ~4 ADANIENT). Independent of DB config.
- Sizing is **decoupled** from the sim `Trade.quantity` (sim keeps its ₹2k-risk sizing; adapter computes its own capped qty).
- Guardrails: daily order cap, daily-loss kill-switch (auto-reverts to `off` + Telegram), in-memory position tracking, dependency-free TOTP token manager.

### Verified
- Boot log: `DhanService mode=log | whitelist=EMA_RSI:{HDFCBANK,ADANIENT} …`
- One intended entry logged & cross-checked vs sim: `INTENDED ENTRY → BUY HDFCBANK ×15` for signal #599 (sim qty 1538 → capped to 15 ✅).

### Secrets (already set, DO NOT print/commit)
- Local: `/home/shivam/workspace/smart-trading/.env` (gitignored) — `DHAN_CLIENT_ID` (1106621718), `DHAN_PIN`, `DHAN_TOTP_SECRET`, `DHAN_ACCESS_TOKEN`.
- work-pc: `/home/work/workspace/smart-trading/infra/.env` — same keys + `DHAN_TRADING_MODE=log`.
- Token validated read-only (fundlimit → HTTP 200). **Account balance = ₹0** (fund before live).

### Stages remaining
- **Stage 2 (sandbox):** base URL `https://sandbox.dhan.co/v2/`. Caveats: mock (no real fills/quotes), likely needs **separate creds from `developer.dhanhq.co`** (not the live token). `generateAccessToken` bug fixed (query params, not JSON) but **not yet live-tested** (avoid PIN lockout — verify format once carefully).
- **Stage 3 (live):** fund ₹10–15K; confirm SEBI algo tagging w/ Dhan; flip `DHAN_TRADING_MODE=live`; reconcile fills vs sim ~1–2 weeks.
- **Hardening before live:** persist `openPositions` (currently in-memory → lost on api restart); poll exit fills; store actual fill prices.

### OPEN DECISION (for you)
Stage 2 path: **(a)** full sandbox (needs developer.dhanhq.co signup), or **(b)** skip sandbox → log → **live at 1-share min** once funded.

---

## Track 2 — v1 hygiene (DONE)

| Task | What | Status |
|---|---|---|
| Prune losers | Removed `Volume_Profile_POC`/`Fibonacci_Golden_Zone`/`VWAP_Supertrend` configs | **Live** (SQL applied; `infra/scripts/hygiene-prune-losers.sql`) |
| Symbol filter | `ADANIPOWER` `isActive=false` (scanner filters on it) | **Live** |
| Swing time-stop | `live_scanner.py` max-hold: SHORT_SWING 5d, MID_SWING 20d, INTRADAY/UNKNOWN 1d net | **Deployed** (verifies at open) |
| Telegram digest | Daily 15:45 IST + weekly Fri 15:50; dependency-free scheduler | **Deployed + verified** (message sent) |

---

## ▶ RESUME TOMORROW (2026-07-09, after 09:15 IST open)

1. **Confirm time-stop flushed the stale opens** (should auto-close on first cycle):
   ```
   ssh work-pc 'docker logs smart-trading-scanner 2>&1 | grep MAX_HOLD | tail'
   ssh work-pc 'docker exec smart-trading-db psql -U trader -d smart_trading -c "SELECT symbol,\"holdDuration\",\"entryTime\"::date FROM \"Trade\" WHERE status='"'"'OPEN'"'"' AND \"entryTime\" < CURRENT_DATE - 3;"'
   ```
   Expect VEDL (26d) + 2× ADANIPOWER (14–15d) → CLOSED with reason `MAX_HOLD time-stop`.
2. **Stage 1 Dhan — full entry+exit cycles** (log mode):
   ```
   ssh work-pc 'docker logs smart-trading-api 2>&1 | grep "\[dhan:LOG\]" | tail -30'
   ```
   Reconcile each `INTENDED ENTRY/EXIT` vs the sim `Trade` (side, symbol, qty=capped). This is the Stage-1 exit criterion.
3. **Digest** — confirm the daily digest lands ~15:45 IST (verify it fires at the scheduled time, not just on restart).
4. Then **decide Stage 2 path** (see OPEN DECISION above) and proceed.

---

## Key reference

**Commits (roadmap-v1, this session):**
```
7c355fe fix(dhan): generateAccessToken query params
36926b2 chore(db): prune losers + deactivate ADANIPOWER
cfa7183 feat(api): scheduled Telegram performance digest
a855ea5 feat(engine): swing/intraday max-hold time-stop
3e287cf chore(infra): build-and-push script (2nd docker account) + Dhan env
c03e7f7 feat(dhan): Dhan execution adapter (log/sandbox/live)
7029612 docs: v1 month-1 performance review
```

**Gotchas / notes:**
- **Docker push** must use `DOCKER_CFG=$HOME/.docker-account2` (shivam13gupta). Default login is `wisfluxp` → `denied`. `build-and-push.sh` handles this. Hub images are now current (safe to `docker compose pull`).
- `generateAccessToken` = **query params** on `https://auth.dhan.co/app/generateAccessToken`; token valid 24h.
- Security IDs (NSE_EQ): **HDFCBANK 1333**, **ADANIENT 25**.
- Dhan **Trading API is free**; the ₹499/mo Data API is NOT needed (candles come from yfinance).
- To disable real orders instantly: set `DHAN_TRADING_MODE=off` in work-pc `infra/.env` + `docker compose up -d api`.
- Deferred/none-blocking: rotate the previously-committed Telegram/Gemini secrets (out of scope).
