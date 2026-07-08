# Dhan Live Execution — EMA_RSI Real-Money Test

**Status:** Planned (not yet built)
**Created:** 2026-07-08
**Scope:** First real-money validation of the v1 paper system via the Dhan broker API.
**Owner:** shivamgupta1319

---

## 1. Goal

v1 has run profitably **on paper** for a month (+₹84,670, PF 1.30). This feature adds a thin,
heavily-guarded **Dhan execution adapter** so a single validated strategy can place **real orders**,
starting at small size, to confirm that live execution behaves as the simulation predicts before
scaling.

**Test scope:** one strategy (**EMA_RSI**) on two symbols (**HDFCBANK**, **ADANIENT**), ~₹10–15K
capital, small fixed rupee-risk per trade. Everything else stays simulated.

**What this test is and isn't:** it is a **correctness + execution validation** with a real-but-small
money read. It is *not* a scale-up. The per-share edge is thin (see §2), so real net will trail the
simulation once slippage and costs bite — that is expected and is itself a thing we're measuring.

---

## 2. Pre-build validation (EMA_RSI · HDFCBANK + ADANIENT · past month)

Before committing capital, all 67 EMA_RSI trades on the two symbols (66 closed + 1 open) were
reviewed directly in the live DB.

| Check | Result |
|---|---|
| P&L arithmetic | **Exact** — e.g. #78 BUY 61 @ 3031.70 → 2999.00 = −₹1,994.7 ✓ |
| Outcome sign consistency | 0 mismatches |
| Null exits / orphans | None |
| Closed trades | 66 (32 HDFCBANK, 34 ADANIENT) |
| Win rate | 58% (38/66) |
| **P&L as-sized** | **+₹47,624** (HDFCBANK +₹25,146 / ADANIENT +₹22,479) |

**Critical caveat — the return only exists at scale.** The +₹47,624 was earned risking ₹2,000/trade
on ~₹8L notional/trade (~8x leverage on a ₹1L base). The **per-share edge is only ₹3.67/trade** →
the whole month at 1 share = **+₹242 gross**, ~breakeven after costs. Hence the test is sized to
~₹10–15K, not 1 share.

**Idealizations to watch during reconciliation (why real < sim):**
- 30/66 exits land *exactly* on the stop-loss price and 7 exactly on target — **zero slippage modeled**.
- Entry price recorded = **previous candle close**, not a live market fill.
- **No costs modeled** (brokerage, STT, exchange, GST, stamp).

Expect real net below simulation, most visibly on the stop-loss exits.

---

## 3. Design decisions

- **Product = MIS intraday (forced).** EMA_RSI is INTRADAY and emits **short (SELL) signals**;
  shorting equity in India is legal only as intraday MIS. The existing 15:15 IST square-off fits MIS.
- **Capital ≈ ₹10–15K; sizing = small fixed ₹-risk/trade (~₹200–300).** A configurable `DHAN_TEST_RISK`
  (default ₹250) replaces the ₹2,000 risk constant → ~10–15 HDFCBANK or ~3–5 ADANIENT shares. Per-order
  and total-open notional are hard-capped to the MIS margin ₹10–15K supports.
- **Token = TOTP auto-refresh.** Dhan access tokens expire every 24h (SEBI rule); the bot self-generates
  a fresh token daily from `dhanClientId + PIN + TOTP`.
- **Rollout = log → sandbox → live** (staged, see §7).

---

## 4. Architecture & injection points

The adapter lives **API-side** (NestJS) — the single choke-point that owns quantity and DB state.
All injection points are in `apps/api/src/signals/signals.service.ts`:

| # | Purpose | Location |
|---|---|---|
| A | Place ENTRY order (BUY-to-open long / SELL-to-open short, MIS) | end of `create()`, after `prisma.trade.create` (~:89), gated on `isNew` |
| B | Size to small fixed ₹-risk + notional caps | constants `:5-8` + quantity calc `:61-66` |
| C | Place FULL EXIT order (square off `remainingQty`; flip BUY↔SELL) | `closeWithPrice()` `:250-293` |
| F | New `DhanService` + secrets + mode flag | mirror `apps/api/src/telegram/telegram.service.ts`; register in `app/app.module.ts` |

Partial closes (`partialClose`) and SL-modify (`updateStopLoss`) are **out of scope** for the test —
only entry + full exit are needed.

### `DhanService` (new `apps/api/src/dhan/`)
- **Mode flag** `DHAN_TRADING_MODE = off | log | sandbox | live` (default **off** = today's pure sim).
- **Token manager:** on first use / on 401 / daily, POST `generateAccessToken`; cache token + expiry
  in memory; TOTP from `DHAN_TOTP_SECRET` via a Node TOTP lib.
- **`placeEntry({symbol, signalType, quantity})`** / **`placeExit({symbol, originalSide, quantity})`**
  (exit flips BUY↔SELL). Both MIS / MARKET / NSE_EQ / DAY. `log` → log only; `sandbox` → sandbox URL;
  `live` → real endpoint.
- **`getFillPrice(orderId)`** → actual executed price for reconciliation.
- **securityId map** for the two whitelisted symbols (resolved from Dhan's scrip master).

---

## 5. Dhan API reference (v2, free for all users)

- **Place order:** `POST https://api.dhan.co/v2/orders`, header `access-token: <JWT>`, body:
  ```json
  { "dhanClientId": "...", "transactionType": "BUY|SELL", "exchangeSegment": "NSE_EQ",
    "productType": "INTRADAY", "orderType": "MARKET", "validity": "DAY",
    "securityId": "<instrument id>", "quantity": "<n>" }
  ```
- **Order status / fills:** `GET /v2/orders/{order-id}` → executed price for real P&L.
- **Token (TOTP):** `POST https://auth.dhan.co/app/generateAccessToken` with `dhanClientId + PIN + TOTP`
  → 24h JWT (no app_id). Verify exact param encoding at build time.
- **Sandbox** available for pre-live testing.
- `securityId` is Dhan's instrument id, **not** the symbol. Confirmed from Dhan's scrip master
  (both the NSE_EQ cash row and the derivatives `UNDERLYING_SECURITY_ID`):

  | Symbol | `exchangeSegment` | `securityId` | ISIN | Series |
  |---|---|---|---|---|
  | HDFCBANK | `NSE_EQ` | **1333** | INE040A01034 | EQ |
  | ADANIENT | `NSE_EQ` | **25** | INE423A01024 | EQ |

- **Cost:** the **Trading API is free** for all Dhan users — that's all this test needs (order
  placement). The paid **Data API** (₹499/mo) is **not required**: price/candles come from yfinance in
  the engine, not from Dhan.
- Docs: [Authentication](https://dhanhq.co/docs/v2/authentication/) ·
  [Place Order](https://docs.dhanhq.co/api/v2/orders/place-order) ·
  scrip master `https://images.dhan.co/api-data/api-scrip-master-detailed.csv`

---

## 6. Guardrails (non-negotiable — defense in depth)

- **Global default OFF** — no real order unless `DHAN_TRADING_MODE` is explicitly `sandbox`/`live`.
- **Strict whitelist inside the adapter** — refuse any order not `EMA_RSI` AND symbol ∈ {HDFCBANK,
  ADANIENT} AND `quantity ≤ DHAN_MAX_QTY` (e.g. 20) AND per-order notional ≤ cap. Independent of
  `ActiveConfiguration`, so a stray/misconfigured signal can never place an off-list or oversized order.
- **Notional / margin cap** — total open real-position notional ≤ MIS margin the ₹10–15K supports;
  reject entries that would breach it.
- **One open position per (symbol,strategy)** — `create()` is already idempotent (`:33-41`); keep it.
- **Daily kill-switch** — max real orders/day and a max-daily-loss threshold → auto-revert to `off` +
  Telegram alert.
- **Exit safety** — verify each exit order actually fills (poll status); alert if any OPEN real position
  survives past 15:15 square-off (Dhan auto-squares MIS ~15:20 as backstop).
- **Reconciliation** — store actual Dhan fill price + order id; compute real P&L vs simulated `entryPrice`.
- **Secrets** — `DHAN_CLIENT_ID`, `DHAN_PIN`, `DHAN_TOTP_SECRET`, `DHAN_TRADING_MODE` via `@nestjs/config`
  in a **gitignored** `.env` (the `infra/.env.example` template pattern). ⚠️ The repo currently commits
  live secrets in `apps/api/.env` and `docker-compose.yml` — do **not** add Dhan creds that way. Rotating
  the already-exposed Telegram/Gemini keys is recommended (separate task).
- **SEBI retail-algo tagging** — send Dhan's `correlationId`; confirm with Dhan whether API-order
  tagging/registration applies (low-frequency here — generally the permitted zone). Confirm before `live`.

---

## 7. Phased rollout

| Stage | Mode | Capital | Purpose |
|---|---|---|---|
| 0 — Prereqs (user) | — | — | Enable Trading API + TOTP on Dhan; note PIN; get HDFCBANK/ADANIENT `securityId`; confirm the 2 EMA_RSI configs are active |
| 1 — Log only | `log` | none | Adapter logs intended entry/exit orders (no Dhan call). Confirm signal→order mapping, timing, 15:15 exits vs sim `Trade` rows |
| 2 — Sandbox | `sandbox` | none | Real Dhan API calls against sandbox. Verify auth/TOTP refresh, order acceptance, status polling, fill capture |
| 3 — Live | `live` | ~₹10–15K | `DHAN_TEST_RISK`≈₹250 + qty/notional caps. Reconcile actual vs simulated fills/slippage ~1–2 weeks; then decide on scaling |

---

## 8. Files touched

- **New:** `apps/api/src/dhan/dhan.service.ts`, `dhan.module.ts` (+ securityId config, TOTP dep).
- **Edit:** `apps/api/src/signals/signals.service.ts` (inject `DhanService`; sizing at `:61-66`; entry
  in `create()`; exit in `closeWithPrice()`), `apps/api/src/app/app.module.ts` (register `DhanModule`),
  `docker-compose.yml` + gitignored `.env` (secrets), root `package.json` (TOTP lib; reuse `axios`).
- **No engine changes** — sizing/gating owned by the API.

---

## 9. Verification

- **Stage 1:** diff logged intended orders vs the day's sim `Trade` rows — side/symbol/qty/timing must
  match; a SELL signal must log SELL-to-open + BUY-to-cover; every position shows a ≤15:15 exit.
- **Stage 2:** token auto-refreshes (force-expire → 401 → regenerate); sandbox order ids returned; fill
  price fetched; kill-switch trips when the daily-loss threshold is crossed (simulated).
- **Stage 3:** first live day — watch one full round-trip on Dhan (order book shows MIS entry + exit),
  reconcile fill vs simulated price, confirm no MIS position survives square-off.

---

## 10. Related work

- Prior v1 hygiene tasks (strategy prune, symbol filter, swing time-stop, Telegram digest) are deferred;
  the adapter's hard whitelist supersedes the prune/filter for *safety*, and the Telegram digest is
  complementary for monitoring the live test.
- Month-1 performance review: [performance-review-2026-07.md](performance-review-2026-07.md).
