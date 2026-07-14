# Real-Money Trading — Runbook (Dhan, v1)

How the funded Dhan account is sized, kept safe, and **how to add a new
`(stock, strategy)` pair when you top up the account by ₹5K**. Real-money order routing lives
entirely in the api container (`DhanService`). For the build/deploy mechanics see
[work-pc-deployment.md](work-pc-deployment.md); for the Dhan order API gotchas see
[dhan-live-execution.md](dhan-live-execution.md).

> The **simulator** (paper `Trade` rows) is a *separate* model (₹5L intraday / ₹1L swing per trade)
> and is intentionally decoupled from real money. Nothing below changes the sim.

---

## Current setup (snapshot — keep this updated)

| Item | Value |
|---|---|
| Funded Dhan account | **≈ ₹10,000** |
| Capital model | **₹5,000 margin per (stock, strategy) pair** → account funds = ₹5K × number of pairs |
| Live pairs (2) | **MACD_Zero / ZEEL** (securityId `3812`), **RVOL_ORB / BSE** (`19585`) — both INTRADAY |
| Mode | `DHAN_TRADING_MODE=live` |

### Live env caps (`work-pc:/home/work/workspace/smart-trading/infra/.env`)

| Var | Value | Meaning |
|---|---|---|
| `DHAN_MAX_NOTIONAL` | `5000` | **base margin per trade** (₹5K per stock) |
| `DHAN_INTRADAY_LEVERAGE` | `5` | MIS multiplier → notional ceiling = ₹5K × 5 = **₹25,000** |
| `DHAN_MAX_RISK` | `200` | **2% of the total account** (₹10K → ₹200). Update when the account grows. |
| `DHAN_MAX_QTY` | `250` | absolute per-order share cap (fat-finger guard) |
| `DHAN_MAX_DAILY_LOSS` | `600` | daily realized-loss kill-switch (~3 full losses); auto-reverts mode→off |
| `DHAN_MAX_ORDERS_PER_DAY` | `20` (default) | per-day order cap |

> After editing `.env`, apply with `docker compose up -d api` (a plain restart does NOT reload env).

---

## The sizing model (how a real order is sized)

Per trade: `qty = min( riskQty, notionalQty, maxQty )` — [dhan.service.ts `computeQty`](../apps/api/src/dhan/dhan.service.ts).
- `riskQty = floor(DHAN_MAX_RISK / |entry − stop|)` → **risk is fixed at 2% of the account**; the
  position size *flexes* with the strategy's stop distance.
- `notionalQty = floor(notional / price)` where `notional = INTRADAY ? MAX_NOTIONAL × LEVERAGE : MAX_NOTIONAL`
  (₹25K intraday). This is the **ceiling**, not a target.
- `maxQty` = hard safety cap.

**Key point:** the risk % sets position *size*, not how often the stop is hit. Stop *distance* is a
**strategy** parameter (ATR / opening-range based). If stops hit too fast, widen the strategy stop —
do not touch the risk cap.

Effective today: ZEEL (~0.9% stop) ≈ 185 sh / ₹22K notional (₹4.4K margin); BSE (~1.5% stop) ≈ 3 sh /
₹11.6K notional (₹2.3K margin). Each risks ≈ ₹200. Both open ≈ ₹6.7K margin — inside ₹10K.

---

## Safety systems (all automatic)

- **Protective stop** — a broker-side `STOP_LOSS` (limit) order is placed the instant an entry fills,
  pegged to the original stop; polled and retried once on rejection, else a Telegram "UNPROTECTED" alert.
- **EOD square-off sweep** — 15:12–15:20 IST, force-flattens any open position off broker netQty
  before Dhan's ~15:18 MIS auto-square (avoids the penalty).
- **Daily-loss kill-switch** — at `DHAN_MAX_DAILY_LOSS` realized loss, mode flips to `off` (persisted;
  a restart won't re-enable it) + Telegram alert.
- **Boot reconcile** — on restart, open positions are reconciled against the broker (never orphaned).
- **Static-IP egress** — all Dhan calls go through the TrueIP IPv6 proxy (SEBI static-IP mandate).

---

## ➕ Add a new `(stock, strategy)` pair + ₹5K  (the main runbook)

**Constraint today: INTRADAY strategies only.** Swing/positional needs CNC (delivery) + a
`DhanPosition.productType` migration + EOD-sweep exclusion — not yet wired. Confirm the strategy's
horizon in [`STRATEGY_HOLD_DURATIONS`](../apps/engine/strategies/__init__.py) is `INTRADAY`.

### 1. Fund the account
Add ₹5,000 in the Dhan app → total account = ₹5K × (number of pairs). E.g. 3rd pair → ₹15,000.

### 2. Find the stock's Dhan NSE securityId
Download the scrip master and grep for the symbol (NSE + EQUITY + EQ series):
```bash
curl -s https://images.dhan.co/api-data/api-scrip-master.csv -o /tmp/scrip.csv
awk -F, '$1=="NSE" && $4=="EQUITY" && $15=="EQ" && $6=="<SYMBOL>" {print $3","$6","$16}' /tmp/scrip.csv
# columns: SEM_SMST_SECURITY_ID , SEM_TRADING_SYMBOL , SM_SYMBOL_NAME
```
Never guess a securityId — a wrong one trades the wrong instrument.

### 3. Whitelist the pair (code)
In [apps/api/src/dhan/dhan.service.ts](../apps/api/src/dhan/dhan.service.ts) add to `LIVE_WHITELIST`:
```ts
{ strategy: '<StrategyName>', symbol: '<SYMBOL>', securityId: '<id>' },
```
`SECURITY_IDS` is derived from `LIVE_WHITELIST` (plus legacy exit-only symbols), so no other code change.
The strategy name must **exactly** match the engine strategy's `name`.

### 4. Make the scanner emit the signal (DB on work-pc)
The scanner only scans `(stock, strategy)` pairs present in `ActiveConfiguration` (and `Stock.isActive`).
```bash
# stock must exist + be active:
docker exec smart-trading-db psql -U trader -d smart_trading -c \
  "SELECT id,symbol,\"isActive\" FROM \"Stock\" WHERE symbol='<SYMBOL>';"
# add the config pair if missing (pick the strategy's timeframe, e.g. 15m):
docker exec smart-trading-db psql -U trader -d smart_trading -c \
  "INSERT INTO \"ActiveConfiguration\" (\"stockId\",\"strategyName\",timeframe) \
   VALUES (<stockId>,'<StrategyName>','<tf>') ON CONFLICT DO NOTHING;"
```
(If the stock is new, insert it into `Stock` first — mirror an existing row.)

### 5. Scale the risk caps to the new account size (`.env` on work-pc)
```bash
# account grew by ₹5K → update the 2%-of-account risk + daily cap. MAX_NOTIONAL stays 5000 (per-stock).
DHAN_MAX_RISK        = round(0.02 × new_total_account)   # e.g. ₹15K → 300
DHAN_MAX_DAILY_LOSS  = ~3 × DHAN_MAX_RISK                # e.g. 300 → 900
```
Edit `.env`, then `docker compose up -d api`.

### 6. Build, push, deploy the api image
```bash
# dev PC:
cd /home/shivam/workspace/smart-trading && ./infra/scripts/build-and-push.sh api
# work-pc:
ssh work-pc 'cd /home/work/workspace/smart-trading/infra && docker compose pull api && docker compose up -d api'
```

### 7. Verify
```bash
ssh work-pc "docker logs --since 2m smart-trading-api 2>&1 | grep -E 'mode=|entryWhitelist|EOD square'"
# expect: mode=live | entryWhitelist=...,<StrategyName>:<SYMBOL> | ... killLoss=<new>
ssh work-pc "docker logs --since 3m smart-trading-scanner 2>&1 | grep '<SYMBOL>'"  # scanner now scans it
```
Then update the **snapshot table** at the top of this doc.

---

## Pause / kill real money
```bash
ssh work-pc 'cd /home/work/workspace/smart-trading/infra && sed -i "s/^DHAN_TRADING_MODE=live/DHAN_TRADING_MODE=off/" .env && docker compose up -d api'
```
`mode=off` = pure sim; no real orders placed, no exits touched. Re-enable by setting `live` + `up -d api`
(do it when flat, or right after 15:30 close, to avoid disturbing an open MIS position).

## Checking the account
Funds/positions/ledger: use the **Dhan app**. Do **not** query the Dhan API from a separate process
while the container is live — Dhan allows one active session, so a new token would break the running
container's auth. Query live account data only after 15:30 close (or via the app).

## Notes
- Only whitelisted `(strategy, symbol)` pairs ever place a real order; everything else is sim-only.
- Legacy symbols (HDFCBANK, ADANIENT) remain in `SECURITY_IDS` for *exits only* — no new entries.
- Real-trade history lives in the `DhanPosition` table (audit trail: fills, SL, realized P&L, close reason).
