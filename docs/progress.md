# Progress — final product (one app on `main`)

Started 2026-11-19. This file is the checklist for merging the two paper-trading apps
(v1 = `roadmap-v1`, v2 = `roadmap-v2`) into one final product. Tick a line when its
change is merged to `main`. The earlier phase history (Phases 0–8) is in
[archive/progress-phases-0-8.md](archive/progress-phases-0-8.md).

## Where we are going

- One app, built on the v2 code, with v1's Dhan real-money layer, Telegram digests and
  landing page brought over.
- Deployed at `trading.pseo.cloud` from `main`. All other branches are removed at cutover.
- Starts with a fresh database, then 3–6 months of paper trading before any real money.
- Strategies keep running in paper. Only the three worst are removed.

## Why (live data, 2026-11-19)

Both apps were checked against their live databases (v1: 4,066 closed paper trades,
v2: 337). The queries are in `infra/scripts/analysis/` and can be re-run at any time.

| Finding | Evidence |
|---|---|
| A good backtest did not mean a good live result | v1: correlation between backtest ROI and live result = −0.06 (53 cells). v2: 58 cells picked for a strong backtest (about 12 backtest trades each) went from 55% wins in backtest to 17% live |
| Too many combinations tested on too few trades | 1,832 stock × strategy combinations backtested; 110 added to the live roster on 2026-07-27 |
| Swing trades only buy, and the market fell | Median stock: Aug −1.1%, Sep −5.6%, Oct −1.3%. v2 swing: −₹13,740 on 110 closed trades. Nothing checks the market before buying |
| v1 does not charge costs | About ₹174 of charges per intraday trade, about ₹6.9 lakh in total, none of it booked |
| No limit on re-entry | `EMA20_Pullback` traded about 3 times per stock per day: 1,557 trades, −₹6.56 lakh. The rest of v1 made about +₹5.05 lakh before costs |
| Nothing switches a losing cell off | No automatic deactivation in either app |
| Paper fills are not real fills | Entry is booked at an old candle's close; stops are booked at exactly the stop price; the backtest enters at the next bar's open |
| Live results repeat | 22 cells with 20+ trades in each half of the period: correlation 0.84; all 9 positive cells stayed positive |
| Trading with the market works better | v1 intraday: 0.215R per trade with the market (361 trades) vs 0.049R against it (306 trades) |

Positive after costs so far: `MACD_Zero`, `SMC_FVG`, `RVOL_ORB`, `VWAP_MACD_RSI`,
`Inside_Bar`, `PDH_PDL_Breakout`.

## Phase 0 — Safety and baseline

- [x] Back up both databases on work-pc (`~/backups/smart_trading-v{1,2}-pre-final-merge-20261119.sql.gz`)
- [x] Save the analysis queries in `infra/scripts/analysis/`
- [x] New progress tracker (this file); old one archived
- [x] `main` fast-forwarded to `roadmap-v2` and pushed
- [ ] Owner: rotate the Telegram bot token that is committed in `docker-compose.prod.yml` on `roadmap-v1`

## Phase 1 — Truthful fills, and backtest = live

- [x] Live entry booked at the live price when the signal is found, not an old candle close
- [x] Stop-outs booked at the worse of the stop and the live price; targets at the target level
- [x] Backtest: a stop that price gaps through fills at the open, not at the stop
- [x] Exit order reviewed: live checks one price per poll, so a stop and a profit level cannot both be true in the same check; no code change needed. The bar-versus-poll difference that remains is listed under "Not yet verified"
- [x] Cooldown (30 min) and maximum trades per day (2) for each intraday cell, in both scanner and backtest
- [x] Scanner dedupe key includes the strategy
- [x] A trade that cannot be sized inside the risk cap is skipped, not forced to 1 share
- [x] A strategy with too little data is reported (scanner warning, backtest flag) instead of quietly giving no signal
- [x] One shared settings file (`config/trading.json`) for fund size, leverage, risk cap and costs, read by engine and API
- [x] Engine dependencies pinned; database driver named explicitly (a fresh image build would otherwise have broken)
- [ ] Parity test: one day of stored candles gives the same trades in scanner and backtest

## Phase 2 — Strategy cleanup and fresh backtest

- [ ] Remove `EMA20_Pullback`, `Volume_Profile_POC`, `VWAP_Supertrend`
- [ ] Fix `Gap_And_Go` (cannot fire live today)
- [ ] Fix `Fibonacci_Golden_Zone` (does not check trend direction)
- [ ] Fix `RSI_Divergence` (fires on every bar while true)
- [ ] Fix `BB_Squeeze` (measures the squeeze on the breakout bar)
- [ ] Fix `MTF_Alignment` (crashes in backtest)
- [ ] `Bollinger_Mean_Reversion`, `Channel_Oscillation`: keep the strategy's own target
- [ ] `docs/strategies.md`: one rule sheet per strategy with its status and reason
- [ ] Price-jump check on stored history (demerger and split cliffs)
- [ ] Walk-forward folds get warm-up data
- [ ] Re-run all backtests on latest data; use only as a first filter (drop clearly broken cells)
- [ ] Fresh roster on a fixed list of liquid stocks

## Phase 3 — Cell lifecycle and scorecard

- [ ] Cell status: `TESTING` → `PROVEN` → `PAUSED`, with the reason stored
- [ ] Automatic pause for cells that keep losing; paused cells continue in a test book
- [ ] Scorecard page: backtest next to live, costs, status, reason for every cell

## Phase 4 — Market condition ("smart switching")

- [ ] Stage A: every trade stamped with the market condition at entry
- [ ] Stage B: rule table (strategy × condition); Portfolio shows "all trades" and "switch-approved" books
- [ ] Stage C: weekly/monthly analyst report that proposes rule changes and new strategies

## Phase 5 — Bring over v1's parts

- [ ] Dhan service and its tables (mode stays `off`)
- [ ] Telegram daily and weekly digests
- [ ] Landing page at `/`
- [ ] Dhan fixes: risk-cap settings passed through compose; `off` must not block exits on open positions; token failure alert

## Phase 6 — Cutover

- [ ] Final stack on work-pc from `main`, fresh database, served at `trading.pseo.cloud`
- [ ] v1 and v2 stacks stopped; `trading-v2.pseo.cloud` retired
- [ ] Old branch tips tagged `archive/*`, then all branches except `main` deleted
- [ ] `smart-trading-v2` worktree removed
- [ ] README rewritten; old docs moved to `docs/archive/`; single `docs/HANDOFF.md`

## Phase 7 — New strategies (each discussed first)

- [ ] Opening-range breakout only in the market's direction
- [ ] Relative-strength long / relative-weakness short against NIFTY
- [ ] EMA20 pullback rebuilt (first pullback after a breakout, once a day)
- [ ] First VWAP reclaim or rejection of the day, with volume
- [ ] Swing: 52-week-high breakout with volume, only when the market is up
- [ ] Swing: relative-strength momentum basket

## Not yet verified

- Whether the 2% risk-cap setting is correct on work-pc today. (From the next deploy a wrong value stops the service at start-up instead of silently disabling the cap.)
- Live polls every 100 seconds, so a stop can be noticed after price has moved past it; the backtest books the stop level. Size of this gap is not measured yet.
- The scanner's database read for entry limits and a real scanner-to-API rejection have not been exercised against a running stack.
- The market-direction result covers about 940 trades; 1,485 had no 15-minute data.
