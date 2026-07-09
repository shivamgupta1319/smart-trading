# Handoff / Resume Doc — Dhan Live Execution + v1 Hygiene

**Last updated:** 2026-07-09 (market open ~09:20 IST)
**Branch:** `roadmap-v1` (all work committed here; not pushed to origin unless you push)
**Design reference:** [dhan-live-execution.md](dhan-live-execution.md) · [performance-review-2026-07.md](performance-review-2026-07.md)

---

## TL;DR — where we are

Two tracks in flight:
1. **Dhan real-money execution** — Stage 1 (**log mode**) is **live on work-pc and validated**. It logs the exact real orders it *would* place for EMA_RSI on HDFCBANK/ADANIENT, without touching money. Stages remaining: sandbox → live.
2. **v1 hygiene** — all 4 tasks (prune losers, symbol filter, swing time-stop, Telegram digest) are **done, deployed, and committed**. Prune + digest are verified live; the time-stop verifies at next market open.

**🟢 LIVE (real money) since 2026-07-09 ~10:21 IST.** `DHAN_TRADING_MODE=live`, ₹10k funded (`availabelBalance:10000` confirmed), validating at ₹12,500/order (~2.5x, half/half). **Token auto-refresh WORKS** — TOTP seed was correct all along; the earlier "Invalid TOTP" was a stale 17h-old container holding the pre-update secret. App auto-mints a 24h token via TOTP + caches ~24h (**no daily manual rotation**); manual `DHAN_ACCESS_TOKEN` remains as fallback. Note: Dhan throttles token gen to once/2min (fine — cached 24h). Instant kill: set `DHAN_TRADING_MODE=off` + `docker compose up -d api`.

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

### DECISION MADE (2026-07-09): skip sandbox → live @ 1 share
Chosen path **(b)**. Log mode already validated order construction (#599: sim 1538 → capped 15 ✅); sandbox only gives mock fills, so it's low added value. Go live at **1-share min qty** once funded.

**No code change needed for 1-share:** `computeQty()` = `min(floor(maxNotional/price), maxQty)`, so `DHAN_MAX_QTY=1` caps every order at 1 share.

**✅ TOTP AUTO-REFRESH FIXED (2026-07-09).** Initial "Invalid TOTP" was a red herring: the seed was correct (confirmed — our computed code matched the user's authenticator app), but the 17h-old container held the *pre-update* secret in memory. Re-testing `generateAccessToken` with the seed read straight from `.env` → HTTP 200, token minted (len 280). Restarted the container so it loads the correct seed; in-container gen now returns rate-limit ("once every 2 minutes"), i.e. TOTP accepted. **No daily token rotation needed.** `getToken()` order: cached (24h) → TOTP-generate → manual `DHAN_ACCESS_TOKEN` fallback. Our TOTP math verified vs RFC 6238 vector (287082); clock NTP-synced.

**Gates:**
- **Gate A — valid token + funds. ✅ CLEARED 2026-07-09.** `fundlimit` → HTTP 200, `availabelBalance:10000`. Token auto-refreshes via TOTP (no manual rotation); manual token is fallback only.
- **Gate B — SEBI algo tagging. ⏳ NOT formally confirmed — proceeded anyway.** Judged low-risk at this scale (own account, official personal DhanHQ API, few orders/day; tagging is largely broker-side). Confirm with Dhan as a follow-up; revisit before scaling frequency/size.

**Sizing decision (2026-07-09):** validate Thu+Fri at the EXISTING `maxNotional=₹12,500/order` (~2.5x, half/half: ~15 HDFC + ~4 ADANIENT ≈ ₹24.5k both legs). Scale toward full ~5x Monday if clean. Drop the `DHAN_MAX_QTY=1` idea — the current config is already the right validation size. Pre-flight helper: `scratchpad/dhan-preflight.js` (one-shot token+fundlimit check inside the api container).

**Go-live runbook (once A+B clear).** On work-pc `infra/.env`:
```
DHAN_MAX_QTY=1
DHAN_TRADING_MODE=live
```
then `docker compose up -d api`. First real order = 1 share (~₹150–200 risk/order), MIS/MARKET, EMA_RSI on HDFCBANK/ADANIENT only. Kill-switch at −₹1,000/day → auto-reverts to `off` + Telegram.

**Residual risk accepted at 1-share scale:** `openPositions` is in-memory → api restart between entry & exit orphans the position (no exit order). Mitigant: MIS auto-squares at EOD (~15:20 IST); worst case ~₹200. **Defer DB persistence until qty > 1.**

---

## Track 2 — v1 hygiene (DONE)

| Task | What | Status |
|---|---|---|
| Prune losers | Removed `Volume_Profile_POC`/`Fibonacci_Golden_Zone`/`VWAP_Supertrend` configs | **Live** (SQL applied; `infra/scripts/hygiene-prune-losers.sql`) |
| Symbol filter | `ADANIPOWER` `isActive=false` (scanner filters on it) | **Live** |
| Swing time-stop | `live_scanner.py` max-hold: SHORT_SWING 5d, MID_SWING 20d, INTRADAY/UNKNOWN 1d net | **✅ VERIFIED LIVE 2026-07-09** — flushed VEDL (26.9d, −₹1,452), 2× ADANIPOWER (15/16d, −₹905/−₹1,291) at 09:15 IST; 0 stale opens remain. (reason logged, not persisted to `Trade.notes`) |
| Telegram digest | Daily 15:45 IST + weekly Fri 15:50; dependency-free scheduler | **Deployed + verified** (message sent) |

---

## ▶ STATUS (2026-07-09 ~09:20 IST) & NEXT

1. ✅ **Time-stop verified** — see hygiene table. 0 stale opens remain.
2. ⏳ **Stage-1 Dhan reconciliation — awaiting today's first whitelisted signal.** No `[dhan:LOG]` entries yet because no EMA_RSI HDFCBANK/ADANIENT signal has fired since the api restarted (~16:18 IST 2026-07-08, post-close). Those symbols fire ~2–4 signals/day, so data should accumulate today. Check:
   ```
   ssh work-pc 'docker logs smart-trading-api 2>&1 | grep "\[dhan:LOG\]" | tail -30'
   ```
   Reconcile each `INTENDED ENTRY/EXIT` vs the sim `Trade` (side, symbol, qty=capped). Full entry+exit pair = Stage-1 exit criterion.
3. ⏳ **Digest** — confirm daily digest lands ~15:45 IST (fires at scheduled time, not just on restart).
4. ⛳ **Go live (decided: skip sandbox → live @ 1 share)** — blocked on **Gate A (fund ₹10–15K, balance=₹0)** + **Gate B (SEBI algo tagging w/ Dhan)**. Then run the go-live runbook above. Both gates are user actions.

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
