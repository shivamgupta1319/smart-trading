# Paper Trading with DhanHQ (free)

SmartTrader does **paper trading** by *simulating* fills in its own Trade ledger
(with the realistic fill + Indian-cost model from Phase 1). It just needs a
**free, reliable market-data feed** to price those simulated trades. DhanHQ
provides that for free — **no real orders are ever placed by SmartTrader.**

## What you get

- Live prices and historical candles from Dhan instead of (unofficial) yfinance.
- Automatic fallback: if no Dhan token is set, everything keeps working on yfinance.
- A diagnostics endpoint to confirm which source is live.

## One-time setup

1. **Open a free Dhan account** at dhan.co (free demat; no API subscription fee).
2. **Generate API credentials**: in the Dhan web app go to
   *Profile → DhanHQ Trading APIs → Access Token*, create a token, and note:
   - `DHAN_ACCESS_TOKEN` (a long JWT)
   - `DHAN_CLIENT_ID` (your numeric Dhan client id)
3. **Put them in the v2 root `.env`** (gitignored):
   ```env
   BROKER=dhan
   DATA_SOURCE=auto            # use Dhan when configured, else yfinance
   DHAN_ACCESS_TOKEN=eyJ0eXAi...
   DHAN_CLIENT_ID=1100XXXXXX
   ```
4. **Recreate the engine** so it picks up the env:
   ```bash
   cd /home/shivam/workspace/smart-trading-v2
   docker compose up -d engine
   ```
5. **Verify** the active source flipped to Dhan:
   ```bash
   curl -s -H "x-api-key: $API_KEY" http://localhost:8001/api/engine/broker/status
   # -> {"broker":"dhan","dataSource":"dhan","dhanConfigured":true,...}

   curl -s -H "x-api-key: $API_KEY" http://localhost:8001/api/engine/broker/probe/RELIANCE
   # -> {"source":"dhan","quote":{"price":...}}
   ```

## What's free vs paid on Dhan (verified)

| Data | Dhan tier | SmartTrader uses |
|------|-----------|------------------|
| **Live quotes** (LTP/quote) | ✅ Free | **Dhan** — drives the scanner + live prices |
| **Historical candles** | ❌ Paid "Data API" (returns HTTP 451 otherwise) | **yfinance** (free) — backtests + charts |

So the zero-cost setup is **live = Dhan, historical = yfinance**, and the facade
does this automatically. Historical via Dhan is disabled by default
(`DHAN_HISTORICAL_ENABLED=false`); flip it to `true` only if you subscribe to
Dhan's Data API. Confirm the split anytime:

```bash
curl -s -H "x-api-key: $API_KEY" http://localhost:8001/api/engine/broker/status
# -> "liveSource":"dhan", "historicalSource":"yfinance (...)"
```

## How it flows

```
Dhan (free live quotes) ─┐
                         ├─► engine data facade (brokers/) ─► live-prices / scanner
yfinance (free history) ─┘                                  ─► backtests / charts
                                       └─► SmartTrader SIMULATED trades (paper)
```

## The 24-hour token (your daily refresh)

Dhan's self-generated access token is a JWT that expires **~24h** (visible in
`/broker/status → dhanToken.expiresAt / hoursLeft`). When it expires, live quotes
simply **fall back to yfinance** (no crash) until you refresh.

You do **not** need to edit `.env` or restart Docker. Each morning:

1. Regenerate the token in the Dhan web app.
2. Paste it in — **easiest: the UI**. Open **⚙️ Settings** in the navbar
   (http://localhost:5174/settings), paste the token, hit **Save & Activate**.
   The page shows the live data source + token expiry (hours left) and flips to
   Dhan instantly.

   Or via API (same effect — written to a volume-mounted file the engine
   re-reads on every request):
   ```bash
   curl -s -X POST http://localhost:3001/api/engine/broker/dhan/token \
     -H "x-api-key: $API_KEY" -H "Content-Type: application/json" \
     -d '{"token":"<new-dhan-jwt>"}'
   # -> {"ok":true,"tokenStatus":{...},"dataSource":"dhan"}
   ```

(You could instead write the token into `apps/engine/.dhan_token` directly — same
effect. That file is gitignored.) If you later want true hands-off renewal, Dhan's
partner/consent OAuth flow supports scripted tokens; not wired here.

## Notes

- Instrument-id mapping is downloaded from Dhan's scrip master and cached ~12h.
- Endpoint/field names in `brokers/dhan.py` follow DhanHQ API v2; the facade always
  falls back to yfinance so the app never hard-fails on a broker change.

## Switching to Upstox instead

Set `BROKER=upstox` and fill the `UPSTOX_*` vars. Upstox uses a daily OAuth token:
`GET /api/engine/broker/upstox/login-url` → authorize → `POST /api/engine/broker/upstox/token`
with the returned `code` → set `UPSTOX_ACCESS_TOKEN`. (Dhan is simpler; Upstox is
provided as an alternative.)

## Going to *real* (live) orders later

This integration is **data-only / paper**. Real order placement would add a
`brokers/dhan.py::place_order()` behind an explicit, off-by-default confirmation
flag — intentionally not built here so nothing can place a real trade by accident.
