# Live (Real-Money) Trading — Capabilities & Limits

**Scope:** the Dhan real-money execution path only (not the paper simulator). This is the
canonical "what it can and can't do" reference. Last updated 2026-07-13.

**One-line summary:** a carefully-guarded, narrow, *supervised* executor that takes small
intraday EMA_RSI trades on two large-caps with real broker-side protection and restart
durability — built to **fail safe (no trade)** rather than fail open. Not yet a proven
autonomous system.

Design/impl references: [dhan-live-execution.md](dhan-live-execution.md) · [handoff.md](handoff.md) ·
code: `apps/api/src/dhan/dhan.service.ts`, `apps/engine/scanner/live_scanner.py`.

---

## ✅ Capable of

### Execution
- Places **real MARKET entry orders** on Dhan when the sim fires a whitelisted signal.
- Computes its **own notional-capped quantity** (~₹12,500/order, ≤20 shares) — fully
  decoupled from the sim's position size.
- Trades **both directions intraday** — long (BUY) and short (SELL), MIS product.
- Rests a **broker-side protective stop** (`STOP_LOSS` limit) at the original stop the
  instant an entry fills — protection persists even if our whole system is down.
- **Exits** via the scanner's logic (stop / target / trailing / reversal / time-stop),
  placing a MARKET exit and **cancelling the resting stop first**, with guards that never
  double-sell (aborts rather than risk a net-short).
- **Squares off intraday at 15:10** itself, beating Dhan's 15:18–15:20 auto-square (and its
  ₹20 penalty).
- **Reconciles against the broker on restart** — reloads open positions from DB, checks
  Dhan's actual positions/orders, and rehydrates or closes accordingly (no orphans).
- **Records real fills** (entry/exit prices + order ids) for P&L reconciliation.

### Resilience / safety
- **Auto-refreshes the Dhan token** (TOTP) and **self-recovers** if another session
  (app login / concurrent gen) invalidates it.
- Routes all order traffic through a **static IP** (SEBI mandate); **fail-safe** if the proxy
  dies — orders fail, they never bypass.
- **Daily-loss kill-switch** (₹1,000 → flips to `off`) and **daily order cap** (20), both now
  **durable across restarts** (a redeploy can't undo them).
- **Instant kill** via `DHAN_TRADING_MODE=off`; Telegram alerts on unprotected positions,
  aborted exits, and kill-switch trips.

---

## ❌ Not capable of (by design or not yet)

### Deliberately narrow (it's a validation harness, not a general trader)
- **Only 2 symbols** (HDFCBANK, ADANIENT) and **one strategy** (EMA_RSI). Everything else is a
  hard no-op — never touches real money.
- **Cash equity, intraday only.** No delivery/CNC, **no overnight/swing on real money**, no
  options / futures / F&O.
- **No real leverage** beyond the notional cap (deliberately ~1–2.5×).

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

- Has taken **exactly one real entry** so far (ADANIENT ×3, 2026-07-13). **Early validation
  stage**, not battle-tested.
- **Not yet verified on real money:** the full broker-stop flow (entry → stop shows in the Dhan
  app → exit cancels it) and the restart-rehydrate path — both validated *synthetically*, live
  confirmation pending the next signal.
- Single broker, single account, tiny size.

**Do not treat it as a proven autonomous system.** It cannot yet be trusted unsupervised, at
size, across strategies/symbols, or for anything beyond intraday cash equity.

---

## Guardrails at a glance

| Control | Value / behavior |
|---|---|
| Whitelist | EMA_RSI · HDFCBANK, ADANIENT only |
| Per-order notional cap | ~₹12,500 (`DHAN_MAX_NOTIONAL`) |
| Max qty / order | 20 (`DHAN_MAX_QTY`) |
| Daily order cap | 20 (`DHAN_MAX_ORDERS_PER_DAY`) |
| Daily-loss kill-switch | ₹1,000 → mode `off` (`DHAN_MAX_DAILY_LOSS`), durable |
| Product | INTRADAY (MIS) |
| Protective stop | resting `STOP_LOSS` limit, buffer `DHAN_SL_LIMIT_BUFFER_PCT` (0.15%) |
| Self square-off | 15:10 IST (before Dhan's 15:18–15:20) |
| Instant off switch | `DHAN_TRADING_MODE=off` + restart api |
