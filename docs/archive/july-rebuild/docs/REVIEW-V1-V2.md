# Review of V1 and V2 — what to keep, what to drop, what was missing

**Date:** 2026-07-15 · **Scope:** full read of both codebases, read-only, plus SQL against both live
databases. **Status: complete.** This is the deliverable for the owner's ask *"review both codebases
and summarise what's worth keeping from each."*

Sources: `~/workspace/smart-trading` (V1, branch `roadmap-v1`) and `~/workspace/smart-trading-v2`
(V2, branch `roadmap-v2`, HEAD `44ef892`). Grounded in
`smart-trading-v2/docs/agent-reports/2026-07-15-v1-v2-engine-audit.md`.
⚠️ That audit's line numbers are drifted 13–20 lines; everything below is verified against HEAD.

---

## The headline

**16% of the code carries ~all of the value.**

| | LOC | Portable |
|---|---:|---:|
| V2 engine | 7,912 | ~900 (fill model + costs) |
| V2 API | 2,452 | ~500 (schema, costs.ts, risk.ts) |
| V2 frontend | 7,440 | 0 (but port its *information design*) |
| V1 Dhan execution layer | 1,078 | **~1,078 — all of it** |
| Attribution ladder | 360 | **all of it — ⚠️ was lost, see below** |
| **Total** | **~18,164** | **~2,900 (16%)** |

**You have one working execution layer (V1's Dhan) and one working measurement layer (V2's engine),
bolted onto strategies that don't work.** That is the accurate summary of two years of work.

---

## The owner's three specific questions, answered

### 1. "V1 solved the 24-hour Dhan token problem — keep it"

**Solved, and simpler than it sounds: a hand-rolled TOTP (RFC 6238), ~90 lines, zero dependencies
beyond Node's built-in `crypto`.** No headless browser, no partner API, no refresh token.

`smart-trading/apps/api/src/dhan/dhan.service.ts`:
- `:1001-1013` `getToken()` — use cache if >60s life → else generate via TOTP → else fall back to a
  manually-pasted token
- `:1015-1039` `generateAccessToken()` → `https://auth.dhan.co/app/generateAccessToken`.
  **Params go as a QUERY STRING, not a JSON body** — this was its own bugfix commit (`7c355fe`) and
  is exactly the kind of detail that costs a day to rediscover.
- `:1048-1078` `totpCode()` — 6-digit / 30s / SHA1, verified against the RFC test vector `287082`
- `:967-978` **`authed()` — the real cleverness.** Retries once on 401 / `DH-901` / `DH-906`. Safe by
  construction: auth errors are *pre-execution* rejections, so it can never double-place an order.

Triggered **lazily and on-401 — there is no cron.** Needs `DHAN_CLIENT_ID`, `DHAN_PIN`,
`DHAN_TOTP_SECRET`.

**Correction to prior belief:** an older note claimed a "2-minute generation throttle" in our code.
**It was never there** — verified via `git log -S` across the whole history. That is *Dhan's
server-side* limit, and **we have no client-side throttle, backoff, or jitter against it.**

**Fragilities to fix when porting:** no throttle/backoff (a token storm regenerates on every call);
the cache is **in-memory only**, so restarting twice within 2 minutes wedges it with no recovery
(this already cost a full day once); generation failure **silently** falls back to a stale token with
**no alert**, despite every other failure class alerting; the auth URL is **hardcoded at `:1024`** and
ignores `DHAN_API_BASE`, so "sandbox" mode still authenticates against production.

### 2. "V2 applies broker charges; V1 does not"

**Confirmed. V1 models zero costs — literally none.** A grep for
`brokerage|round_trip|CostModel|stt_|stamp|slippage` across all of `smart-trading/apps/` returns
**no matches.** V1 omits costs at exactly three P&L sites: `trades.service.ts:201-209`,
`signals.service.ts:187-194` and `:224-233`, plus the backtest at `base.py:62-71`.

**Quantified:** V1 intraday at ₹5L notional silently omits ~₹190–200 per round trip — about **10% of
its ₹2,000 risk cap, on every single trade.** V1's equity curve is optimistic by roughly one-tenth of
an R per trade *before* slippage.

**V2's cost model is correct and is the single best-verified asset in either repo**
(`backtest_config.py:94-155`, ~60 LOC). Checked against real 2026 Indian rates: brokerage
min(0.03% intraday / 0% delivery, ₹20) per side; STT 0.025% sell intraday / 0.1% both sides delivery;
exchange 0.00297%; SEBI 0.0001%; stamp 0.003%/0.015% buy-side; GST 18% on (brokerage+exchange);
DP ₹14.75 flat per delivery sell. Two negligible nits: GST base omits SEBI fees (~₹0.0002/trade), and
NSE IPFT is not modelled. **Port verbatim.**

### 3. "Initial fund differs"

**True, but the more important fact is that V1's backtest and V1's live code implement two different
models** — so V1's backtest never simulated what V1 actually did.

| | V1 live | V1 backtest | V2 |
|---|---|---|---|
| Fund | one shared ₹1,00,000 | ₹1,00,000 | **per-cell ₹10,000** |
| Compounding | **no** (hardcoded const) | yes | yes |
| Leverage | 5× intraday / 1× swing | **none** | 5× / 1× |
| Risk cap | ₹2,000 flat | **none** | ₹200 (2% of the live cell fund) |
| Shares | integer | **fractional (!)** | integer |
| Costs | none | none | full |

**V1's headline bug:** `INITIAL_CAPITAL` is a `const`, so the ₹2,000 risk cap **never shrinks after
losses and never grows after wins**. A blown-down account still risks ₹2,000 a trade.

**Unit hazard for v3:** `RISK_PER_TRADE_PCT` means **2** (percent) in V1, **0.02** (fraction) in V2's
`risk.ts`, and **2.0** (percent again) in V2's `backtest_config.py`. **Three conventions, one name.**

---

## KEEP

### From V1 — the Dhan execution layer (`dhan.service.ts`, 1,078 LOC). This is V1's only asset.

Genuinely hard-won and real-money tested. The reasoning here is the kind you only write after getting
burned:

- **TOTP token auto-generation + `authed()` self-heal** — above.
- **Static-IP / SEBI workaround** (`:114-122`). SEBI mandates a static IP for Order APIs (`DH-905`);
  `setIP` **locks it for 7 days**. **The insight: Dhan whitelists IPv6 and its endpoints are
  dual-stack**, so a *free* TrueIP static IPv6 satisfies a mandate others pay ₹700/mo of VPS for.
  Wired as **one shared axios instance**, so there is no silent bypass — if the proxy dies, orders
  fail safe instead of egressing from the wrong IP. Credentials masked in logs.
  (The Oracle Cloud runbook doc is **superseded — ignore it**; Oracle was abandoned on a card lock.)
- **Protective stop = `STOP_LOSS` limit, NOT SL-M** (`:830-862`). Dhan *rejects* a below-LTP SELL
  `STOP_LOSS_MARKET` ("Trigger Price should be greater than Price"), so the limit is placed just past
  the trigger to fill like a market order while staying inside Dhan's price-protection band.
- **Tick rounding** (`:995-997`) — off-tick orders POST fine and are *asynchronously* rejected. The
  `.toFixed(2)` kills float artifacts like `3152.7000000000003`.
- **SL-reject poll/retry is a tri-state** (`:572-642`, `:946-960`) — `true` → done; `false` → retry
  once with double buffer (safe: the first order is definitively dead); **`undefined` → never retry**,
  because two live stops means an oversell. **The sharpest reasoning in either codebase.**
- **EOD square-off sweep 15:12–15:20 IST** (`:184-292`) — beats Dhan's ~15:18 auto-square penalty, and
  is **driven by broker truth (`netQty`), not the in-memory map**, so it catches orphans from restarts.
- **`getPositions()` returns `null` on error, deliberately distinct from `[]`** (`:916-933`) — never
  treat an unreachable broker as "flat". A battle scar from a real orphaned-position bug. **Port it.**
- **Persist to DB *before* arming the stop** (`:455`); reconcile **never places orders** (`:315-318`).

### From V2 — the measurement layer

- **The honest fill model** (`strategies/base.py:112-326`, `simulate`, ~215 LOC): next-bar entry
  (`:181-188`), intrabar High/Low stops (`:237-252`), **pessimistic tie-break** (`:243-246` — if a bar
  hits both the stop and the target, assume the stop; the single most valuable line in the repo),
  geometry validation (`:194-199`). **Zero DB/network/framework dependencies** — it lifts cleanly.
- **The cost model** — above.
- **`avgRMultiple` as the ranking metric.** ROI is raw-cumulative and window-dependent (1D ≈ 5.1y vs
  15m/5m ≈ 4.7mo ⇒ **~13× incomparable**).
- **The strategy interface** — `generate_signals(df) → df` adding `signal`/`stop_loss`/`target`.
  Minimal and honest. **But it cannot express a cross-sectional strategy** — that is V2's ceiling.
- `ENGINE_VERSION` stamping + one-row-per-cell UPSERT; `Decimal(18,4)` for money; the partial unique
  index for one-active-signal-per-cell; `normalize_to_ist_naive()`; the fetch scheduler.
- **The docs system** — `docs/features/<slug>/*` + `feature-index.json` + dated agent-reports +
  **code↔report backlinks** + "NOT AUTO-APPLIED" banners on one-off SQL. Genuinely good practice.
- **Tests worth porting:** `test_backtest_engine.py` (esp. `test_pessimistic_when_bar_straddles_both`)
  and `test_roadmap_fixes.py` (sizing parity + `test_live_fetch_covers_every_strategy_lookback`).

### The attribution ladder — the best technique either system produced

Hold signals constant; toggle **one behaviour per rung**; **require both ends to reconcile against the
real systems** (Gate A: V1's stored rows, 182/190; Gate B: V2's real backtest, **305/305, d=0.00**).
It caught a shipped regression in hours **and publicly refuted its own author's hypothesis**. A
harness that can embarrass the person running it is a harness that works.

> ⚠️ **It lived only in an ephemeral `/tmp` scratchpad and was REAPED on 2026-07-15 before rescue.**
> ~380 LOC lost. **The ground truth was recovered** from the still-running databases and is now
> committed at `tests/fixtures/v1_reports.csv` (1,761 rows) and `v2_reports.csv` (718 rows), with
> `scripts/dump_ground_truth.sh` to regenerate. **The code must be rewritten** — feasible, because
> V1's engine is 96 lines and still in git. **Lesson: ground truth never lives in /tmp.**

---

## DROP

- **V1's backtest engine entirely** (`smart-trading/apps/engine/strategies/base.py`, **96 lines**).
  Buys at the **signal bar's own close** (lookahead), checks stops on the **close only** (never sees
  the bar's Low, so it pretends intrabar stop-outs didn't happen), fills at the **exact** stop/target
  price even when the bar gapped far through it, charges **zero** costs, uses **fractional shares**,
  deploys the full ₹1L. **Its good numbers are not real.**
- **All 31 strategies.** They are **~4 ideas wearing 31 hats**: 8 moving-average trend variants, 4
  mean-reversion, 5 intraday breakout. Testing 31 correlated variants is not a search — it is one bet
  sampled 31 times. And **31 × 60 = 1,860 cells with no multiple-testing correction ⇒ ~93 false
  winners expected at p=0.05.** The "winners" were noise.
- **The ₹10k-per-cell fiction as an accounting unit.** The flat ₹14.75 DP charge is 0.6–0.8% of a
  ₹3,097 deployed notional versus 0.06% of V1's ₹95k. **The account unit ate the edge, not the
  strategy.** (Keep ₹10k as the *funding* unit — that's the owner's real model. Just don't let it
  drive position size into the ground.)
- **C3, the intraday exit model — do not port.** See N3 below. It is V2's largest unexplained term.
- **V2's frontend** (7,440 LOC, ~1,000 of it dead boilerplate) — **but port its information design**
  (`LiveScanner.tsx:22-43`, `:745-754`): annualise ROI, grey out avgR below the confidence threshold,
  explain "gains ₹X per ₹1 risked". Those decisions were hard-won. The JSX was not.
- **Both repos' migration history.** Schema declares `@@unique([stockId, strategyName])`; the only
  migration creates `UNIQUE(stockId)`; `Trade` was never migrated at all. The DB was shaped by
  `db push --accept-data-loss`. **v3 starts from a clean baseline.**
- **The worktree arrangement.** V2 is a *git worktree of V1* — same repo, same history. That is why a
  V1 secret contaminates both. **v3 gets its own repo.**

---

## MISSING from both — build these new

1. **A data layer you can trust.** V2 has **no validation whatsoever**: no `high >= low` check, no
   zero/negative price check, no gap detection, no bar-count assertion, no staleness check. A bad
   yfinance response is stored as truth and silently backtested. **This is the weakest area in the
   entire system and it sits underneath every number ever computed.**
2. **The friction-budget gate** (~200 LOC, needs no data). Would have killed all 14 intraday
   strategies on paper in one hour. Neither system had any version of this.
3. **Multiple-testing correction.** Neither system had any.
4. **A capital allocator.** V2's per-cell fund is a *research* model, not a portfolio model — there is
   no shared bankroll, no funding gate, and **no cap on total concurrent exposure**. `MAX_HEAT_PCT` is
   a dashboard flag, not a gate. If v3 trades real money this is genuinely new work.
5. **Point-in-time universe membership.** The 60 stocks were chosen *today* by liquidity ⇒ any
   cross-sectional backtest on them **manufactures momentum**.

---

## Defects found in this review, beyond the audit — do not re-inherit

**P0**
- **N1 — the "honest" fill model is not honest about gaps.** `base.py:248,251,374` book a gap-through
  exit **at the stop price**: a long with a ₹100 stop, on a bar opening at ₹92, books ₹100 and
  collects ₹8/share that never existed. Overnight gaps are *exactly* where swing stops get hit, so
  **every honesty rung in the audit understates the true cost.** Fix: `min(open, sl)` for longs.
- **N2 — live re-introduces the lookahead the backtest removed.** `live_scanner.py:198` posts
  `entryPrice = latest['Close']` (last *completed* candle) → `signals.service.ts:115`. For a 1D signal
  that is **yesterday's close**. This makes `costs.ts:6-9` factually wrong ("live P&L already uses the
  real observed prices" — it does not), so **live P&L is a fiction and every live-vs-backtest
  reconciliation compares against it.**
- **N3 — C3's backtest and live check exits in OPPOSITE ORDER.** Backtest checks the stop **first**
  (`base.py:373`); live checks it **last** (`live_scanner.py:469`). Same bar, different outcome,
  systematically. **A strong candidate for much of the audit's unexplained −12 to −47pp** — meaning
  the intraday gap may be substantially a *measurement artifact*, not a real loss. Gate B never
  covered intraday (`gates.py:17` skipped it), so **C3 has never been reconciled against anything.**
- **N6 — corporate actions silently corrupt stored history.** `history.py:118-126` re-fetches only the
  last 5 days, but yfinance retro-adjusts the **whole** series on a split/demerger ⇒ a permanent
  spliced cliff. **Verified by SQL — exactly 3 of 60 stocks:**

  | Symbol | Date | Before → After | Jump |
  |---|---|---|---|
  | VEDL | 2026-04-30 | 773.60 → 271.55 | **−64.9%** (demerger) |
  | TMPV | 2025-10-14 | 655.31 → 392.20 | **−40.2%** (demerger) |
  | TRENT | 2026-01-01 | 4272.69 → 2860.71 | **−33.0%** |

  **Bounded — 3 of 60 is too small to overturn the audit's "no edge" verdict.** Do not let this become
  hope. Note **demergers never appear in yfinance's actions data**, so factor reconstruction alone
  cannot catch them; you need an unexplained-jump detector that quarantines the symbol.

**P1** — **N4** leaderboard drawdown ÷ ₹100k while booked on a ₹10k slot ⇒ **DD 10× understated,
Calmar 10× inflated** (the correct column exists and is ignored). · **N5** `RISK_PER_TRADE_PCT=2` in
`.env` but the code expects `0.02` ⇒ risk budget = 200% ⇒ **the cap is silently disabled**; prod is
safe only by accident (compose passes no `env_file`), so **local backtests silently differ from
prod**. · **N9** the time-stop default is **still 10/20/40 in code** — only compose sets it to 0, so a
naive port re-inherits the −3.57pp regression. · **N11** the `max(1,…)` risk-cap breach exists in
**live too** (`signals.service.ts:114`), not just the backtest.

**Still open from the audit:** F4 (`ret_dd` gates on raw window-dependent ROI at `auto_select.py:226`,
even though `spanYears` is computed, persisted, *and already used by the frontend*), F7 (~4 dead
strategies), F8 (walk-forward folds have **no warmup prepend** ⇒ 200-bar strategies get ~23 usable
bars and are spuriously rejected — and the bug exists in **two** copies), F9, F10, **F11** (bare
`except` in `_hold_bucket` silently disables long-only + time-stop + trail + R-target),
F12 (a comment cites `MAX_CONCURRENT_POSITIONS` in `risk.ts` — **it does not exist**).

**The deepest architectural problem:** every constant — risk %, leverage, every cost rate, the phase
triggers — is duplicated Python↔TypeScript and held together by **comments saying "MUST match"**. One
is already stale. *There is no shared schema, only shared intent.* **v3: one config file both
runtimes read.**

> ⚠️ **SECURITY:** a **live Telegram bot token and chat ID are committed in plaintext** at
> `smart-trading/docker-compose.prod.yml:30-31`, and the file is **tracked**. Because V2 is a worktree
> of the same repo, that history is in **both** checkouts. `.gitignore` does not help a tracked file.
> **Rotate the token and purge it from history** (ask the owner first — rewriting shared history is
> his call).

---

## The uncomfortable conclusion

Across 31 strategies × 60 stocks, **no strategy has shown an edge that survives real costs.** Swing is
~1%/yr even fully fixed. Intraday friction is ~2× the edge, and that verdict is robust even at a
near-perfect 1bp fill.

**This is not an architecture problem, and a rewrite will not create edge.** V3 is worth building only
because it can answer the edge question *honestly and cheaply* — not because it will trade better.
If the answer is "no edge", **stopping is the correct outcome**, and it will have cost weeks instead
of another year.

**Read [USER-GUIDE.md](USER-GUIDE.md) for the plain-language version of all of this.**
