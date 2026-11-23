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
- [ ] Parity test: one day of stored candles gives the same trades in scanner and backtest (not started; needs the scanner's exit decisions pulled into a function that can be replayed)

## Phase 2 — Strategy cleanup and fresh backtest

- [x] Remove `EMA20_Pullback`, `Volume_Profile_POC`, `VWAP_Supertrend`
- [x] Fix `Gap_And_Go` (could not fire live)
- [x] Fix `Fibonacci_Golden_Zone` (did not check trend direction)
- [x] Fix `RSI_Divergence` (fired on every bar while true)
- [x] Fix `BB_Squeeze` (measured the squeeze on the breakout bar)
- [x] Fix `MTF_Alignment` (crashed in backtest)
- [ ] `Bollinger_Mean_Reversion`, `Channel_Oscillation`: measure own target against the 4R override before changing anything (the July measurement said the override helps)
- [x] `docs/strategies.md`: one rule sheet per strategy with its status and evidence
- [ ] Price-jump check on stored history: the backtest tool now flags them (16 of 60 stocks); reviewing and quarantining them is still to do
- [x] Walk-forward folds get warm-up data (one shared implementation)
- [x] Re-run all backtests on latest data with the corrected engine (read-only tool `apps/engine/tools/backtest_all.py`; results in `docs/strategies.md`)
- [x] Cost rule: a trade is skipped when costs are more than 25% of its risk (engine and API)
- [x] Scanner acts on signals from candles completed between polls
- [ ] Fresh roster on a fixed list of liquid stocks

### What the fresh backtest showed (2026-11-19)

With honest fills and costs at ₹10,000 per cell, **every intraday strategy is negative on
average** across the 60 stocks (−0.35R per trade; −0.14R with the cost rule). The best four
are near break-even on the most volatile stocks. Swing, re-run that evening with the rules
live actually uses (see the correction in strategies.md): 14 of 17 strategies are positive
and six are positive in both halves of 5.5 years, on a stock list that flatters them. Detail and limits:
[strategies.md](strategies.md). This is the baseline the 3–6 months of paper trading starts
from; it is not a reason to expect profit.

## Phase 3 — Cell lifecycle and scorecard

- [x] Cell status: `TESTING` → `PROVEN` → `PAUSED`, with the reason stored (API; rules in `config/trading.json`)
- [x] Automatic pause for cells that keep losing; paused cells continue in a test book (`Trade.cellStatusAtEntry`)
- [x] `GET /api/configs/scorecard` and an end-to-end check (`infra/scripts/e2e-smoke.sh`)
- [ ] Portfolio totals split into main book and test book
- [x] Scorecard page (`/scorecard`): status and reason, live result against the backtest, first and second half, net after costs, main and test book totals

## Phase 4 — Market condition ("smart switching")

- [x] Stage A: every trade stamped with the market condition at entry
- [ ] Stage B: rule table (strategy × condition); Portfolio shows "all trades" and "switch-approved" books
- [ ] Stage C: weekly/monthly analyst report that proposes rule changes and new strategies

## Phase 5 — Bring over v1's parts

- [ ] Dhan service and its tables (mode stays `off`)
- [ ] Telegram daily and weekly digests
- [x] Landing page at `/`
- [ ] Dhan fixes: risk-cap settings passed through compose; `off` must not block exits on open positions; token failure alert

## Phase 6 — Cutover

- [x] Final stack on work-pc from `main`, fresh database, served at `trading.pseo.cloud` (2026-11-19, 387 cells in testing)
- [x] Both earlier stacks stopped (their volumes, images and files are kept on work-pc for now)
- [x] Old second-stack folder removed on work-pc. Kept on purpose: both old database volumes, the old images, the dumps in `~/backups`, and `infra/_archive-before-merge-20261119/` (holds the Dhan settings needed for the port)
- [x] Owner: removed the `trading-v2.pseo.cloud` hostname in Cloudflare (2026-11-19)
- [x] Old branch tips tagged `archive/*`, then all branches except `main` deleted (the Dhan code to port is at tag `archive/roadmap-v1`)
- [x] Second local project folder removed; one folder on `main`
- [ ] README rewritten; old docs moved to `docs/archive/`; single `docs/HANDOFF.md`

## Phase 7 — New strategies (each discussed first)

- [ ] Opening-range breakout only in the market's direction
- [ ] Relative-strength long / relative-weakness short against NIFTY
- [ ] EMA20 pullback rebuilt (first pullback after a breakout, once a day)
- [ ] First VWAP reclaim or rejection of the day, with volume
- [ ] Swing: 52-week-high breakout with volume, only when the market is up
- [ ] Swing: relative-strength momentum basket

## After go-live: adding what is still missing (plan of 2026-11-19)

Everything useful from the first app (git tag `archive/roadmap-v1`), the second app and the
July rebuild goes into this one product. Six packages, in this order.

### 1. Telegram digests
- [x] Daily (15:45 IST), weekly and since-the-start (Fridays) digests, after costs, main book and test book reported apart, with the day's status changes
- [x] `GET /api/reports/digest-preview?period=DAILY|WEEKLY|OVERALL` shows what would be sent
- [x] Deployed to work-pc (2026-11-19)

Also done that day, from issues seen on the live app: dashboard prices are fetched six at a
time (61 quotes in about 8 seconds, was about 30) and all AI analysis goes through the AI
router (`apps/engine/ai_client.py`); the direct OpenRouter and Gemini calls are gone.

### 2. Data you can trust
- [x] Candle data checks where candles are written (`apps/engine/data_checks.py`); rows left out are counted and reported
- [x] Price-jump check with a reviewed list (`config/known_price_actions.json`); unreviewed stocks get `Stock.dataFlag`
- [x] Reviewed demergers are scaled out when history is loaded (backtests and scanner)
- [x] Flag shown on the Scorecard
- [x] Whole series replaced when the data source has re-scaled its prices (split or dividend)
- [x] The 27 flagged moves reviewed: 24 real market moves and 2 demergers listed. The last two were confirmed from news reports: KAYNES 2026-05-14 was a real fall after results; TRENT's step is its 1-for-2 bonus issue, which the data source carried back only to 2026-01-01 (listed as kind `bonus` and scaled out). No stock is flagged now

### 3. Honest numbers
- [x] Slippage per share = the larger of one tick (₹0.05) and 5 basis points, in the engine and the API cost rule
- [x] Luck-correction statistics and a trials ledger (`research_stats.py`, `research_trials.py`; the backtest tool writes a per-strategy table). Result: three long-term trend strategies pass the first test, none passes the stricter one
- [x] NIFTY buy-and-hold comparison (`GET /api/engine/benchmark`), shown on the Portfolio page since the first trade
- [x] Portfolio totals split into main book and test book (all Portfolio figures are the main book)

### 4. Market condition and switching
- [x] Stage A: every trade stamped with the market condition at entry (NIFTY regime, the day's direction across the roster, breadth, and whether the trade goes with the market). Nothing is blocked
- [ ] Stage B: rule table and a "switch-approved" book next to "all trades"
- [ ] Stage C: weekly/monthly analyst report

### 5. Real-money layer (Dhan), switched off
- [x] Service, tables and settings ported from the first app. Fixed while porting: exits keep working when entries are off or halted; sizing limits reach the service and default to the paper book's; the token is cached in the database, respects Dhan's two-minute limit and alerts on failure; the list of tradable pairs is no longer in the source code
- [x] Two locks: a cell must be `PROVEN` and switched on by the owner (`POST /api/configs/:id/live`); `GET /api/dhan/status`
- [x] The switch and the real-money status shown on the Scorecard page
- [x] Runbook and "what live can and cannot do" rewritten for this product (`docs/real-money-trading.md`, `docs/live-capabilities.md`)
- [x] Deployed to work-pc with the mode `off` (2026-11-19; log shows `DhanService mode=off`)

### 6. Finish and retire
- [x] Manual close needs a price (the live quote, or one typed in; never the entry price); planned stop shown in the journal; journal lists all trades
- [x] README rewritten; plain-language user guide (`docs/user-guide.md`); documents from the two earlier apps moved to `docs/archive/old-apps/`
- [x] July rebuild: useful pieces in; the left-out code, tests and decision documents copied to `docs/archive/july-rebuild/`
- [x] Replay test (backtest against the scanner on the same candles): entries now identical; it found and fixed three one-sided rules (late-day entries, stale next-morning signals, the cost rule's inputs)
- [x] Full backtest re-run on the corrected engine (`2026.11.19-parity2`); `docs/strategies.md` refreshed. Correction: the morning's swing figures used a time-stop that live does not have; with live rules 14 of 17 swing strategies are positive, six in both halves. Intraday unchanged: all negative after costs
- [x] Phone menu: below 1200px the links fold into a menu opened by one button; the desktop bar fits from 1200px up
- [x] Luck check shown on the Backtesting page: stored per run (`LuckCheckRun`), refreshed by the scheduler after each daily fetch, and on demand from the page
- [x] Owner's decision (2026-11-19): `~/workspace/stock-trading` stays as it is. It is not used by the product; a full copy of its history is also in `~/backups/stock-trading-2026-11-19.bundle`

## Not yet verified

- Whether the 2% risk-cap setting is correct on work-pc today. (From the next deploy a wrong value stops the service at start-up instead of silently disabling the cap.)
- Live polls every 100 seconds, so a stop can be noticed after price has moved past it; the backtest books the stop level. Size of this gap is not measured yet.
- The scanner's database read for entry limits and a real scanner-to-API rejection have not been exercised against a running stack.
- The market-direction result covers about 940 trades; 1,485 had no 15-minute data.

## Owner's changes, 2026-11-19 (evening)

- [x] Intraday risk per trade is 2% of the ₹50,000 a trade may hold (₹1,000), not 2% of the ₹10,000 fund. Swing unchanged (₹200). A cell is now paused when ₹5,000 is left of its ₹10,000 fund (this replaces "lost 15% in the last 20 trades"); the average-R pause rule is unchanged. Backtest and live use the same rule; engine `2026.11.19-risk5x`. Real-money orders keep their separate ₹200 limit
- [x] Portfolio: profit factor shows "—" until there is a losing trade; flat trades are counted and named
- [x] Validate: the engine's real reason is shown (it was replaced by "internal server error")
- [x] Fresh start (owner's decision): all 390 cells and all 10 trades of the first day deleted; the roster is now 100 cells chosen from the backtest on engine `2026.11.19-risk5x` (rule and list in `infra/scripts/seed-starting-roster.sql`): 7 intraday, 93 swing. Paper trading restarts on 2026-11-20 with every cell at ₹10,000

## Owner's changes, 2026-11-23

- [x] Auto-select runs in the background with a status the page follows (it timed out at the public address's 120-second limit while the run carried on unseen)
- [x] One live rule everywhere (`apps/engine/selection_rule.py`, thresholds in `config/trading.json`): the roster rule gained three checks (profit factor 1.5, profit at least twice the worst drawdown, total return 10%) after the owner found cells live with a small profit and a large drawdown. Auto-select, the per-strategy result rows and the Set Live warning all use it
- [x] Roster pruned to the cells that meet the three new checks

