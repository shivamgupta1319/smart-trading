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
- **Gate B — 🟢 RESOLVED 2026-07-10 (~16:10 IST) via TrueIP static IPv6.** Was confirmed-failed at 12:27 IST (signal #622 HDFCBANK SELL rejected `DH-905 Invalid IP`, clean — no fill/position/P&L). Fixed by routing the api's Dhan egress through **TrueIP.in** (free dedicated static IPv6 `2600:3c16:e001:3d::2a8`, Mumbai). `setIP` PRIMARY done; `getIP` → `detectedIP==primaryIP`, `ipMatchStatus=PRIMARY_MATCH`, **`ordersAllowed:true`**. IP locked until 2026-07-16. Details ↓
  - *Tagging:* we run ~2–4 orders/**day**; SEBI threshold is 10 orders/**second**. Below-threshold → no algo registration, orders auto-tagged with a generic Algo-ID exchange/broker-side. No payload change. ✅
  - *Static IP:* 🔴 Dhan v2.4 (SEBI, in force since Apr 1 2026): **"Static IP is required for all Order APIs."** `getIP` → error (none configured). work-pc egress = **103.59.75.14 (TATA Play consumer broadband → dynamic)**. `POST /v2/ip/setIP` **locks the IP for 7 days** → do NOT set a dynamic IP. IP APIs: `GET/POST /v2/ip/getIP|setIP|modifyIP`.
  - *Also:* container→Dhan calls intermittently time out (flaky broadband) — reliability concern.
  - **Plan:** (1) verify enforcement empirically — next live signal either rejects for IP (→ need static IP) or fills. (2) If reject → route order egress via a **VPS static IP** and `setIP` that. Chosen because robust + fixes flaky link; need to know user's cloud provider.

**Sizing decision (2026-07-09):** validate Thu+Fri at the EXISTING `maxNotional=₹12,500/order` (~2.5x, half/half: ~15 HDFC + ~4 ADANIENT ≈ ₹24.5k both legs). Scale toward full ~5x Monday if clean. Drop the `DHAN_MAX_QTY=1` idea — the current config is already the right validation size. Pre-flight helper: `scratchpad/dhan-preflight.js` (one-shot token+fundlimit check inside the api container).

**Go-live runbook (once A+B clear).** On work-pc `infra/.env`:
```
DHAN_MAX_QTY=1
DHAN_TRADING_MODE=live
```
then `docker compose up -d api`. First real order = 1 share (~₹150–200 risk/order), MIS/MARKET, EMA_RSI on HDFCBANK/ADANIENT only. Kill-switch at −₹1,000/day → auto-reverts to `off` + Telegram.

**Residual risk accepted at 1-share scale:** `openPositions` is in-memory → api restart between entry & exit orphans the position (no exit order). Mitigant: MIS auto-squares at EOD (~15:20 IST); worst case ~₹200. **Defer DB persistence until qty > 1.**

---

## Track 3 — Long-only swing rule (fixed 2026-07-09)

**Bug:** hold duration was assigned per-strategy, direction-blind → a swing strategy (e.g. `Bollinger_Mean_Reversion`) could emit a SELL and get stamped MID_SWING = an overnight short, which is **not executable in cash equity**. Found via open trade #581 (HDFCBANK SELL/MID_SWING). Scope was tiny (1 such trade ever, ₹0 realized) and **never touched real money** (Dhan whitelist = EMA_RSI intraday only).

**Rule enforced:** only INTRADAY strategies may short; swing/positional are **long-only**.
- `strategies/__init__.py`: `STRATEGY_LONG_ONLY[name] = holdDuration != "INTRADAY"`; sets `inst.long_only` on each registry instance.
- `strategies/base.py`: `run_backtest` drops `signal==-1` when `long_only` (metrics stay executable). Verified: short-emitting strategy 1 trade → 0.
- `scanner/live_scanner.py`: suppresses SELL when `hold_duration != "INTRADAY"`.
- Deployed: rebuilt+pushed engine image, `docker compose up -d engine scanner`. Containers healthy.
- Cleanup: #581 closed at entry (₹0 P&L) with audit note.

**Deferred (Slice 2, dormant):** Dhan CNC (delivery, no leverage) vs MIS (intraday) product selection. Not needed yet — sim has no leverage; swing not whitelisted for live. When a swing strategy IS whitelisted: pass `holdDuration` to `dhan.placeEntry` (available at `signals.service.ts:105`) and set `productType='CNC'` for non-INTRADAY (currently hardcoded `'INTRADAY'` in `dhan.service.ts` postOrder).

**Follow-up (optional):** stored `BacktestReport` metrics for swing strategies were computed with phantom shorts — re-run backtests to refresh (likely small effect).

**Uncommitted:** engine code changes are deployed (built from working tree) but not yet git-committed on `roadmap-v1`.

## Track 2 — v1 hygiene (DONE)

| Task | What | Status |
|---|---|---|
| Prune losers | Removed `Volume_Profile_POC`/`Fibonacci_Golden_Zone`/`VWAP_Supertrend` configs | **Live** (SQL applied; `infra/scripts/hygiene-prune-losers.sql`) |
| Symbol filter | `ADANIPOWER` `isActive=false` (scanner filters on it) | **Live** |
| Swing time-stop | `live_scanner.py` max-hold: SHORT_SWING 5d, MID_SWING 20d, INTRADAY/UNKNOWN 1d net | **✅ VERIFIED LIVE 2026-07-09** — flushed VEDL (26.9d, −₹1,452), 2× ADANIPOWER (15/16d, −₹905/−₹1,291) at 09:15 IST; 0 stale opens remain. (reason logged, not persisted to `Trade.notes`) |
| Telegram digest | Daily 15:45 IST + weekly Fri 15:50; dependency-free scheduler | **Deployed + verified** (message sent) |

---

## ▶ FRIDAY 2026-07-10 CLOSE — Gate B RESOLVED via TrueIP static IPv6 🟢

**Arc of the day:** live mode fired its first real order at **12:27 IST** (signal #622, HDFCBANK EMA_RSI SELL; sim #619, sim qty 930 → Dhan-capped 15 ✅) → Dhan **rejected `DH-905 Invalid IP`** (benign: no fill/position/P&L). Confirmed Gate B (SEBI static-IP mandate, all brokers, since Apr 1 2026 — switching broker does NOT help). Solved same day.

**Solution shipped: static-IP egress via TrueIP.in (free dedicated static IPv6).**
- **Why TrueIP:** ruled out company boxes (off-limits), router/ISP static IP (TATA Play consumer = dynamic public IP; router only sets LAN), paid UPI VPS (₹700/mo too heavy vs ₹10k), Cloudflare (dedicated egress = Enterprise-paid; WARP rotates), **Oracle Free Tier (blocked on card-AVS "max attempts" lock)**. Discovery: Dhan whitelists **IPv6** + its endpoints are dual-stack → TrueIP gives a free dedicated static IPv6 in Mumbai as an HTTP CONNECT proxy.
- **TrueIP acct (Shivam):** portal.trueip.in · egress IPv6 **`2600:3c16:e001:3d::2a8`** · proxy `ipv6-mumbai.trueip.in:10680` · free, "never rotated", valid to 2126.
- **Code (committed? NO — uncommitted on roadmap-v1):** `apps/api/src/dhan/dhan.service.ts` now routes ALL Dhan calls (token-gen + order + fill-read) through a shared axios instance bound to `HttpsProxyAgent` when **`DHAN_HTTP_PROXY`** is set (gated; no-op if unset). Added dep `https-proxy-agent@^7`. Added `DHAN_HTTP_PROXY` passthrough to `infra/docker-compose.yml` (repo + work-pc, `.bak` saved).
- **Secret:** `DHAN_HTTP_PROXY=http://u680_b1eaa181:<pass>@ipv6-mumbai.trueip.in:10680` set in work-pc `infra/.env` (and local `.env`). NOT committed.
- **Deployed & verified 16:04 IST:** boot log `[dhan] egress via static-IP proxy → …trueip.in:10680`; in-container egress test → `EGRESS_IP 2600:3c16:e001:3d::2a8`; **`setIP` PRIMARY = SUCCESS**; `getIP` → `ordersAllowed:true`, `PRIMARY_MATCH`, IP locked until **2026-07-16**.

**▶ NEXT ACTION (Monday 07-13):** re-arm the order watcher at 09:15 IST open — the first EMA_RSI HDFCBANK/ADANIENT signal is now the **first real fill** (no more DH-905):
```
ssh work-pc 'timeout 21600 docker logs -f --since 1m smart-trading-api 2>&1 | grep -m1 -E "\[dhan:live\] (ENTRY|EXIT) (placed|FAILED)"'
```
`ENTRY placed` = 🎉 first real trade → reconcile fill vs sim. `ENTRY FAILED` → read error (if TrueIP proxy down: orders fail *safe*, no bypass; check TrueIP dashboard / `docker logs` for proxy errors). Watch kill-switch (−₹1,000/day → auto-off + Telegram).

**Resilience notes:** if TrueIP dies, orders fail safe (app only egresses via proxy — no silent bypass). Recovery options: (a) fix/replace proxy creds in `.env`; (b) after 2026-07-16, `setIP` a new IP. SECONDARY slot is free — could later register a fallback IP. `openPositions` still in-memory (api restart between entry/exit orphans a position; MIS auto-squares EOD; defer DB persistence until qty>1). [dhan-static-ip-oracle-runbook.md](dhan-static-ip-oracle-runbook.md) is now SUPERSEDED (Oracle abandoned).

## ▶ FRIDAY 2026-07-10 RESUME (end of Thu 07-09)

- **Live mode armed, but NO live order fired Thu** — EMA_RSI on HDFCBANK/ADANIENT only signalled in the early burst (09:31–10:17 IST), all *before* go-live (10:21 IST); quiet all afternoon. **Gate B static-IP test still unrun.**
- **Friday is hands-off on tokens:** TOTP auto-refresh works (fixed Thu), so the app self-mints a fresh token on the first order — no manual rotation needed even though the manual token expires ~midday Fri.
- **Friday first action:** re-arm the order watcher at/after 09:15 IST open:
  ```
  ssh work-pc 'timeout 21600 docker logs -f --since 1m smart-trading-api 2>&1 | grep -m1 -E "\[dhan:live\] (ENTRY|EXIT) (placed|FAILED)"'
  ```
  First EMA_RSI signal → real order. `ENTRY placed` = IP not enforced (we're good); `ENTRY FAILED` + IP error = need the VPS static IP (Gate B path A).
- Backtest fixes (Track 4) done + committed (`826e95f`). Long-only swing fix (Track 3) done (`758f4a8`).

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
