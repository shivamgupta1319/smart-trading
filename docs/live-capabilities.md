# Live (Real-Money) Trading — Capabilities & Limits

**Scope:** the Dhan real-money execution path only (not the paper simulator). This is the
canonical "what it can and can't do" reference. Last updated 2026-07-14.

**One-line summary:** a carefully-guarded, narrow, *supervised* executor that takes small
intraday trades on a whitelisted `(strategy, symbol)` set with real broker-side protection and
restart durability — built to **fail safe (no trade)** rather than fail open. Not yet a proven
autonomous system.

Operational runbook (setup + adding pairs): [real-money-trading.md](real-money-trading.md).
Design/impl references: [dhan-live-execution.md](dhan-live-execution.md) · [handoff.md](handoff.md) ·
code: `apps/api/src/dhan/dhan.service.ts`, `apps/engine/scanner/live_scanner.py`.

---

## ✅ Capable of

### Execution
- Places **real MARKET entry orders** on Dhan when the sim fires a whitelisted signal.
- Computes its **own quantity** — `min(risk-based, notional, maxQty)`, fully decoupled from the
  sim's position size. Risk is capped at **2% of the account** (`DHAN_MAX_RISK`); the notional
  ceiling is **₹5K margin × 5× MIS = ₹25K** for intraday (`DHAN_MAX_NOTIONAL`×`DHAN_INTRADAY_LEVERAGE`).
- Trades **both directions intraday** — long (BUY) and short (SELL), MIS product.
- Rests a **broker-side protective stop** (`STOP_LOSS` limit) at the original stop the
  instant an entry fills — protection persists even if our whole system is down.
- **Exits** via the scanner's logic (stop / target / trailing / reversal / time-stop),
  placing a MARKET exit and **cancelling the resting stop first**, with guards that never
  double-sell (aborts rather than risk a net-short).
- **Squares off intraday** itself before Dhan's 15:18–15:20 auto-square (and its ₹20 penalty):
  the scanner closes at 15:10, and an independent **broker-truth EOD sweep (15:12–15:20)** in the
  api force-flattens any position still open at the broker, driven by real Dhan netQty (not our
  in-memory map) — so restarts/aborted-exits can't leave a position for the broker to auto-square.
- **Reconciles against the broker on restart** — reloads open positions from DB, checks
  Dhan's actual positions/orders, and rehydrates or closes accordingly (no orphans).
- **Records real fills** (entry/exit prices + order ids) for P&L reconciliation.

### Resilience / safety
- **Auto-refreshes the Dhan token** (TOTP) and **self-recovers** if another session
  (app login / concurrent gen) invalidates it.
- Routes all order traffic through a **static IP** (SEBI mandate); **fail-safe** if the proxy
  dies — orders fail, they never bypass.
- **Daily-loss kill-switch** (`DHAN_MAX_DAILY_LOSS` → flips to `off`) and **daily order cap** (20),
  both now **durable across restarts** (a redeploy can't undo them).
- On a rejected protective stop, **polls + retries once with a wider limit buffer**, then fires the
  "POSITION UNPROTECTED" alert (was: place-and-forget, never detected async rejection).
- **Instant kill** via `DHAN_TRADING_MODE=off`; Telegram alerts on unprotected positions,
  aborted exits, and kill-switch trips.

---

## ❌ Not capable of (by design or not yet)

### Deliberately narrow (it's a validation harness, not a general trader)
- **Only whitelisted `(strategy, symbol)` pairs** — currently **MACD_Zero/ZEEL** and
  **RVOL_ORB/BSE**. Everything else is a hard no-op — never touches real money. (Legacy
  HDFCBANK/ADANIENT remain in the securityId map for *exits only*, not new entries.)
- **Cash equity, intraday only.** No delivery/CNC, **no overnight/swing on real money**, no
  options / futures / F&O. (Adding a swing pair needs CNC + a `DhanPosition.productType` migration
  — deferred; `placeEntry` skips non-INTRADAY.)
- **MIS intraday leverage ~5×** (₹25K notional on ₹5K margin per trade), bounded by the 2%-of-account
  risk cap.

### Behavioral gaps
- **No partial exits on the real position** — all-or-nothing, even though the sim books partials.
- The **broker stop is not trailed** — it rests at the *original* stop; trailing is "soft"
  (in our engine only). If we're down, you're protected at the original level, not the trailed one.
- **Exit timing is polled (~100s)**, not tick-by-tick. The broker stop covers a catastrophic
  gap between polls, but a normal target/trailing exit can lag up to ~100s.
- A **violent gap through the limit stop** can leave it unfilled → falls back to MIS EOD
  square-off. (Dhan rejects a below-LTP market stop, so the protective stop is a limit.)

### Dependencies — if any is down, execution degrades (fail-safe, but degraded)
- Needs the **api + scanner + TrueIP proxy + a valid Dhan token** all up. Any failure → no new
  trades; open positions lean on the broker stop / MIS EOD.

---

## ⚠️ Maturity (be clear-eyed)

- A handful of real entries so far (e.g. ADANIENT ×3 +₹111 and HDFCBANK ×15, both 2026-07-14).
  **Early validation stage**, not battle-tested. The protective-stop + restart-rehydrate paths
  have now fired live (e.g. #653 rehydrated and reconciled flat on a mode restart).
- Single broker, single account, small size (₹10K funded; ₹5K margin/pair).

**Do not treat it as a proven autonomous system.** It cannot yet be trusted unsupervised, at
size, across strategies/symbols, or for anything beyond intraday cash equity.

---

## Guardrails at a glance

Current live values (₹10K account; see [real-money-trading.md](real-money-trading.md) for the
authoritative snapshot):

| Control | Value / behavior |
|---|---|
| Whitelist (entry) | MACD_Zero/ZEEL, RVOL_ORB/BSE |
| Risk cap / trade | ₹200 = **2% of the account** (`DHAN_MAX_RISK`) |
| Notional ceiling | ₹5K margin × 5× = ₹25K (`DHAN_MAX_NOTIONAL`×`DHAN_INTRADAY_LEVERAGE`) |
| Max qty / order | 250 (`DHAN_MAX_QTY`) |
| Daily order cap | 20 (`DHAN_MAX_ORDERS_PER_DAY`) |
| Daily-loss kill-switch | ₹600 → mode `off` (`DHAN_MAX_DAILY_LOSS`), durable |
| Product | INTRADAY (MIS) |
| Protective stop | resting `STOP_LOSS` limit, buffer `DHAN_SL_LIMIT_BUFFER_PCT` (0.15%), poll+retry on reject |
| Self square-off | scanner 15:10 + broker-truth EOD sweep 15:12–15:20 (before Dhan's 15:18–15:20) |
| Instant off switch | `DHAN_TRADING_MODE=off` + restart api |
