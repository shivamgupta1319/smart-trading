# Real-money trading (Dhan)

Smart Trading can place real orders at the Dhan broker for a small number of cells. It is
**switched off** by default and was off when this page was written (2026-11-19). This page is
the runbook: how it is kept safe, how to switch a cell on, and what to check.

Read [live-capabilities.md](live-capabilities.md) first for what the real-money side can and
cannot do.

## The safety model

**Real money needs every one of these to be true:**

1. `DHAN_TRADING_MODE` is `live` (default `off`).
2. The cell is **PROVEN** on the Scorecard: 40 or more paper trades, profitable after costs,
   positive in both halves.
3. You have **switched the cell on** yourself.
4. The stock has its Dhan security id saved.
5. The signal is intraday. Swing signals are never traded with real money.
6. Today's limits are not used up (orders per day, daily loss).

A cell that stops being PROVEN stops opening real trades straight away. You do not need to
switch it off.

**Entries and exits are separate.** Switching entries off, in any way, never stops an open
real position from being exited:

| What happened | New real trades | Open real positions |
|---|---|---|
| Mode set to `off` or `log` with a position open | Stopped | Still exited; you get a Telegram alert at start-up |
| Daily loss limit reached | Stopped until tomorrow | Still exited |
| Cell paused or no longer PROVEN | Stopped for that cell | Still exited |

## Modes

| `DHAN_TRADING_MODE` | What it does |
|---|---|
| `off` | No new real position. Default. |
| `log` | Writes the order it would place to the API log. No broker call. Use this first. |
| `sandbox` | Sends orders to Dhan's sandbox (set `DHAN_API_BASE` to the sandbox address). No money. |
| `live` | Sends real orders. |

## Limits

Defaults follow the paper book, so a real trade is sized like its paper twin.

| Setting | Default | Meaning |
|---|---|---|
| `DHAN_MAX_NOTIONAL` | 10000 | Margin per order, in rupees (one cell's fund) |
| `DHAN_INTRADAY_LEVERAGE` | 5 | Position value = margin × this |
| `DHAN_MAX_RISK` | 200 | Most a single trade may lose at its stop (2% of ₹10,000) |
| `DHAN_MAX_QTY` | 500 | Most shares in one order |
| `DHAN_MAX_ORDERS_PER_DAY` | 20 | Entries per day, all cells together |
| `DHAN_MAX_DAILY_LOSS` | 600 | Realised loss in a day that stops new entries |
| `DHAN_SL_LIMIT_BUFFER_PCT` | 0.0015 | How far past the trigger the broker stop's limit sits |

Quantity is the smallest of: risk limit ÷ distance to the stop, position value ÷ price, and
the share limit. If you fund the account with a different amount per cell, change
`DHAN_MAX_NOTIONAL` and `DHAN_MAX_RISK` together (risk = 2% of the fund per cell).

`GET /api/dhan/status` shows the mode, the limits in force, today's counters and any open
real position. It never shows a credential.

## What you need before going live

- A funded Dhan account, with the API enabled.
- In `infra/.env` on work-pc: `DHAN_CLIENT_ID`, `DHAN_PIN`, `DHAN_TOTP_SECRET` (the base32
  seed from web.dhan.co → Profile → DhanHQ Trading APIs).
- `DHAN_HTTP_PROXY`: every Indian broker requires order requests to come from a fixed,
  registered IP address. The app sends all Dhan traffic through this proxy, and the login
  token must be created through it too. Register the address with Dhan first; registering
  locks it for 7 days.
- The old first-app settings are kept on work-pc in
  `infra/_archive-before-merge-20261119/.env` if you need the earlier values.

## Switching a cell on

1. **The cell must be PROVEN** on the Scorecard. If it is not, stop here.
2. **Find the stock's Dhan security id** in Dhan's scrip master (NSE equity segment).
3. **Run in `log` mode for a few days.** Set `DHAN_TRADING_MODE=log`, restart the API, and
   read the log lines `INTENDED ENTRY` / `INTENDED EXIT`. Check the quantities are what you
   expect.
4. **Switch the cell on:**

   ```bash
   curl -X POST https://trading.pseo.cloud/api/configs/<cell id>/live \
     -H 'x-api-key: <key>' -H 'content-type: application/json' \
     -d '{"enabled": true, "securityId": "3812"}'
   ```

   It is refused with a clear message if the cell is not PROVEN or has no security id.
5. **Set `DHAN_TRADING_MODE=live`** and restart the API:
   `docker compose up -d --no-deps api`.
6. **Check** `GET /api/dhan/status` and the API log line that starts `DhanService mode=live`.

To switch a cell off, send `{"enabled": false}` to the same address. To stop all new real
trades at once, set `DHAN_TRADING_MODE=off` and restart the API; open positions are still
exited.

## During the day

- **Entry:** a market order, then a stop order left resting at the broker at the planned
  stop. If the broker rejects the stop, the app retries once with a wider limit and, if that
  also fails, sends the Telegram alert `POSITION UNPROTECTED`.
- **Exit:** when the paper trade closes, the app cancels the resting stop and sends a market
  exit. If the resting stop has already fired, it does not sell again.
- **15:12–15:20 IST:** any real position still open is closed, working from the broker's own
  record of what is held. This runs before Dhan's own forced close, which costs extra.
- **After a restart:** open positions are reloaded from the database and checked against the
  broker.

## Telegram alerts to act on

| Alert | What to do |
|---|---|
| `POSITION UNPROTECTED` | A real position has no stop at the broker. Watch it or close it by hand. |
| `EXIT ABORTED (stop cancel failed)` | The app could not confirm the stop was cancelled, so it did not sell. Check the position at the broker. |
| `could not log in` | Token generation failed. No real order, including exits, can be placed until it works. Check the PIN, the TOTP seed and the proxy. |
| `daily loss limit reached` | No more entries today. Nothing to do unless a position is open. |
| `open position while entries are off` | The mode is off but a real position exists. It will still be exited. |

## Things that go wrong

- **Logging into the Dhan app or website cancels the app's token.** The app notices on its
  next request and creates a new one, but Dhan allows only one new token every two minutes.
  Avoid logging in during market hours.
- **Stop orders must be the limit kind** (`STOP_LOSS`), not stop-market: Dhan rejects a
  sell stop-market below the current price.
- **Prices must be on the ₹0.05 tick.** An off-tick price is accepted and then rejected a
  moment later. The app rounds every price it sends.
- **The access token is stored in the database** (table `DhanToken`) so a restart reuses it.
  Treat database dumps as holding a credential.
