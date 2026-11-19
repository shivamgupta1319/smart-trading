# Decisions log

Why things are the way they are. Each entry: the decision, the reasoning, and **what would change our
mind**. If you are about to argue with one of these, check the last column first.

Date format: YYYY-MM-DD. Newest last.

---

## D1 — Phase 1 is Python-only. No API, no UI, no Docker, no Postgres.
**2026-07-15**

Phase 1's deliverable is a **decision**, not a service. Every tier deleted is a tier that cannot drift.

V2's engine is littered with comments saying *"MUST match `apps/api/src/common/risk.ts`"* — that burden
exists **only** because sizing was implemented twice, in two languages. One of those comments (F12)
cites a constant that **no longer exists**. *There is no shared schema, only shared intent.*

**Changes our mind:** Phase 1 finds edge → Phase 2 needs an execution layer and a UI, and then the
two-runtime problem returns. It must be solved with **one config both runtimes read**, not comments.

---

## D2 — Parquet + DuckDB, not Postgres.
**2026-07-15**

60 stocks × 15y daily ≈ 225k rows. Postgres bought concurrency and a UI; Phase 1 has one user and no
UI. DuckDB gives SQL-over-parquet with zero setup — and **preserves the owner's ability to audit by
SQL**, which is exactly how the N6 data corruption was found.

**Changes our mind:** Phase 2 needs concurrent writers and a UI ⇒ Postgres returns.

---

## D3 — numpy/pandas, not polars. Port before optimising.
**2026-07-15**

The ported engine must stay **line-comparable to V2's `base.py`** so the parity gate's claim ("it is
the same engine") is verifiable by reading. Rewriting in polars destroys that argument for a speedup
we do not need at 60 stocks.

**Changes our mind:** nothing, in Phase 1. Optimise after parity is proven and only if measured slow.

---

## D4 — The friction gate ships **second**, before the data layer.
**2026-07-15**

It is ~200 LOC, needs **zero data**, and answers most of the intraday question by arithmetic:
180 trades/yr × **₹53.00** (a ₹50,000 position — the 5× cap on a ₹10k slot) / ₹10,000 =
**95.4%/yr of friction**. At a wider 0.52% stop (₹38,675 deployed) it is ₹41.00 ⇒ **73.8%/yr**.

> **2026-07-15 — corrected.** This entry originally read "180 × ₹41 / ₹10,000 = 73.8%", citing ₹41 as
> the cost of a ₹50,000 position. **₹41 is the cost of a ₹38,675 position**; ₹50,000 costs ₹53.00.
> Intraday cost is a **rate** (10.60 bps of notional), so the rupee figure follows from stop width and
> cannot be quoted alone. **The decision is unaffected and gets stronger** — the range is 19%–96%/yr and
> **every point loses to NIFTY's free ~12%.** See ARCHITECTURE §5.

V2 built and measured **14 intraday strategies that this arithmetic had already excluded.** That was
the single biggest process failure in the project and the cheapest one to never repeat — it was
decidable on paper, in an hour, with no code and no data.

**Kill the cheapest question first** is the entire sequencing logic of this repo.

**Changes our mind:** nothing. This is the core lesson of two failed systems.

---

## D5 — No compounding in Phase 1. Fixed ₹10k per slot.
**2026-07-15**

Three reasons:
1. Phase 1 measures **edge**. Compounding makes ROI path-dependent and non-comparable across cells.
2. **It doesn't match reality** — the owner *tops up* ₹10k per pair on go-live. It is not a compounding
   bankroll. We were modelling something he does not do.
3. V2 compounded, hit **+639% geometric inflation**, then bolted on `cap_position_value` to hide it.
   That flag is a *symptom* of per-cell compounding being in tension with honest ROI reporting.

Report **avgR**, **net ₹/trade**, and **annualised ₹ on ₹10k** instead.

Because this deviates from V2, it is an **explicit ladder rung (R5)** — the port reconciles to V2
exactly *before* the deviation switches on. The deviation is measured, not assumed.

**Changes our mind:** Phase 2 with a real shared bankroll needs a real capital allocator, and that
does compound.

---

## D6 — Do not port C3 (the intraday exit model).
**2026-07-15**

C3 is a **live-execution** model (3-phase partials / breakeven / candle-trail / reversal / 15:15
square-off) with no place in **edge discovery**.

Three reasons, in increasing order of force:
1. **It is V2's largest unexplained term.** −12 to −47pp of V2's intraday result is unattributed, and
   C3 is one of only two unmeasured rungs.
2. **N3: its backtest and live implementations check exits in opposite order.** Backtest checks the
   stop **first** (`base.py:373`); live checks it **last** (`live_scanner.py:469`). Same bar, different
   outcome, systematically. **It has never been reconciled against anything** — the audit's Gate B
   covered only swing (`gates.py:17` skipped intraday).
3. **The precedent.** The swing time-stop looked reasonable when shipped and turned out to be a
   −3.57pp regression. C3 is ~10× more complex and has *less* validation. **Do not assume C3 is
   correct.**

Dropping it **removes** an unknown rather than importing one. Phase-1 intraday = plain fixed SL/TP +
square-off.

**Changes our mind:** Phase 2 needs a real exit model for live trading — but then it gets built once,
called by both sides literally, and reconciled. The current halfway house (shared constants, forked
control flow) is the worst of both.

---

## D7 — Deflated Sharpe Ratio primary, BH-FDR as cross-check.
**2026-07-15**

V2 tested **1,860 cells with no correction** ⇒ ~93 expected false winners at p=0.05. That is why its
"winners" were noise.

DSR (Bailey & López de Prado) directly answers the real question — *"given N trials with this spread of
Sharpes, is the best one still real?"* — and adjusts for N, skew, kurtosis **and sample length**, all
of which bite hard on a short, fat-tailed Indian sample.

Rejected: **White's Reality Check** (bootstrap over all strategies' joint returns — heavier, and its
power collapses when strategies are correlated, which ours will be); **Hansen's SPA** (fixes that, but
more machinery than 4 strategies justify); **Bonferroni** (too conservative). **BH-FDR at q=0.10** is
the cross-check — more powerful than Bonferroni, valid under positive dependence.

**Subtlety:** N=1,860 is *also* wrong. The hypothesis under test is **the strategy**, not the cell.
Aggregate cells to a strategy-level series; N = strategies × variants tried.

**Changes our mind:** nothing. Some correction is non-negotiable; the specific choice is arguable.

---

## D8 — The slot is the atom: (instrument_set × strategy), funded ₹10k per concurrent slot.
**2026-07-15**

V2's "cell" = (stock × strategy) cannot express a cross-sectional strategy, which ranks 60 stocks and
holds the best 6 — the capital *rotates between stocks*. That is V2's ceiling, and it is why a whole
class of well-evidenced strategies was never testable.

The generalisation: **what the owner funds is a concurrent position, not a stock.** Time-series →
`slots=1` → ₹10k (his model, unchanged). Cross-sectional top-6 → `slots=6` → **₹60k**.

Each sleeve is its own ₹10k at 1×, so **per-position cost arithmetic is identical for both** — which is
exactly what lets one friction gate apply uniformly.

This independently matches the owner's own instinct: *"if in future we need swing or equity trading
then we create a separate web application for it and we same backend."* The backend is shared because
the funding unit is shared.

**Changes our mind:** nothing — but the owner must be told plainly that **a top-6 strategy is a ₹60,000
commitment, not ₹10,000.**

**✅ Clarified by the owner 2026-07-16, and it settles the "must be told" point:**
- **Slots do not net across strategies.** ₹10k is per **(stock × strategy)** pair held concurrently. If
  two strategies both hold RELIANCE, that is ₹20k in RELIANCE — two slots, no offset. His words: *"we
  make 10K for each slot... if a stock has 3 strategies then we use 30K in total not just 10K."*
- **Phase 1 uses mock money, so total capital does not bind the design.** *"currently its mock so we
  can use 10K for each slot and trade as many as we can so we have good amount of data."* ⇒ **the
  backtest engine must NOT impose a portfolio-level capital cap** — every slot is an independent ₹10k
  and concurrency is unbounded. The ₹120k+ total for both momentum sleeves is irrelevant in backtest.
- **Real money is self-limiting.** *"once the system is ready and we have tested/live result i am going
  to use only top performance stocks and strategies pair for real money."* He funds only the winners
  P11 ranks, at ₹10k each — so the ₹60k top-6 figure cannot ambush him. He never funds all pairs live.

**Design consequence:** per-position cost arithmetic stays identical across both classes (still one
friction gate), AND the engine tracks P&L per independent ₹10k slot with no bankroll constraint in
Phase 1. A total-capital limit would be a real feature to add only if/when he asks for one at go-live.

---

## D9 — Two engines, not one fake abstraction.
**2026-07-15**

`generate_signals(df) → df` cannot express a cross-sectional ranker. Forcing it to would be a fake
abstraction. And **cross-sectional momentum has no per-trade stop** — inventing one would be modelling
fiction.

So: `StopEngine` (per symbol, port of V2's `simulate`) + `RebalanceEngine` (panel-wide, next-open
fills, no stops). **Unify at the entry point and the ledger**, not the signal function. One `Trade` /
`Result` type is what makes them comparable.

Enforced by a real test: a degenerate cross-sectional strategy holding exactly 1 name must produce a
trade list matching `StopEngine`'s on the same signals.

**Changes our mind:** nothing.

---

## D10 — Store raw, derive adjusted, and refuse to trade through unexplained jumps.
**2026-07-15**

V2's `history.py:118-126` re-fetched only the last 5 days while yfinance **retro-adjusts the whole
series** on a corporate action ⇒ a permanent spliced cliff. **Verified by SQL: 3 of 60 stocks** — VEDL
−64.9%, TMPV −40.2%, TRENT −33.0%.

Storing raw (`auto_adjust=False`, explicit) and deriving adjustment ourselves makes this
**structurally impossible for splits/dividends** — raw prices don't change retroactively, so there is
nothing to splice.

✅ **Adjustment BUILT 2026-07-16 — `src/trading/data/adjust.py`, verified against yfinance.** The
evidence sharpened what "derive adjustment" means: **splits are already in yfinance's `Close`** (it
pre-applies them even at `auto_adjust=False` — verified across ITC/RELIANCE/TRENT split dates), so the
only thing to derive is **dividends**. `Close` and `Adj Close` differ by exactly the dividend
back-adjustment. We derive it ourselves (CRSP-style, factor = ∏`(1 − Dᵢ/closeᵢ₋₁)` over future
ex-dates) rather than store yfinance's `Adj Close`, which is retro-recomputed on every payout (= N6).
`store.adjusted_close` derives on read from stored raw + stored dividends — never materialised, so it
cannot drift from raw. **Reconciles to yfinance `Adj Close`: 0.0000% pure, 0.0077% end-to-end.**
⚠️ Because yfinance bakes splits into `Close`, our stored "raw" is **split-adjusted, not truly raw** —
a *new* split still retro-restates `Close`, so the "raw prices don't change" claim holds for dividends
but is only *mostly* true for splits. The cliff detector is the backstop if a re-pull ever restates it.

**But that alone does not fix the owner's actual cases, and this is the important part:** VEDL and TMPV
are **demergers**. A demerger is neither a split nor a dividend and **will not appear in yfinance's
actions at all.** Factor reconstruction cannot catch it.

So we add an **unexplained-jump detector**: `|log return| > 20%` on 1D not explained by a known action
⇒ **quarantine the symbol and refuse to backtest through it** until a reviewed entry exists in
`config/known_actions.yaml`.

**You cannot auto-solve a demerger. You can refuse to silently trade through one.**

✅ **BUILT 2026-07-16 — `src/trading/data/actions.py`, with a live regression on the real bug.** VEDL
(−64.9%, 2026-04-30) and TRENT (−33.0%, 2026-01-01) are **detected with an empty allowlist and cleared
by the shipped `known_actions.yaml`** — the P4 deliverable. Three things the real data taught, now
load-bearing:
- **The 20% rule flags real crashes too, and that is correct, not a bug.** Full history flags VEDL's
  Jan-2008 crash and Oct-2020 delisting collapse, and TRENT's Mar-2020 COVID low, alongside the
  demergers. **From price alone a demerger and a crash are the same bar** — so review is unavoidable,
  and the allowlist records what a human decided each was (`kind: demerger` vs `kind: real_move`). An
  unknown `kind` raises: a safety config that tolerates typos is not one.
- **Splits need no entry.** yfinance pre-applies stock splits even with `auto_adjust=False` (verified —
  TRENT's 2026-05-29 1.5:1 split made no cliff), so they never reach 20%. ⚠️ This also means our "raw"
  is **split-adjusted**, which the *adjustment* slice (deferred) must account for — related to N7.
- **TMPV cannot be gated yet:** its old symbol no longer resolves on yfinance (the demerger renamed
  it). That *is* the demerger problem; the symbol must be resolved before it can be listed.

**Also:** full re-pull for 1D always (the incremental path bought nothing and cost correctness);
pull **15y not 5y** (free, ~3× the sample — the difference between 60 and ~180 monthly observations,
i.e. between "insufficient evidence" and a verdict).

**Changes our mind:** a reliable corporate-actions data source (paid) would let us adjust demergers
properly instead of quarantining. Worth revisiting if the universe grows.

---

## D11 — Slippage is `max(1 tick, k × spread)`, and every verdict ships a sensitivity curve.
**2026-07-15**

V2's flat 5bps is **wrong in both directions**: 13 ticks on RELIANCE (₹1,300) and an impossible **0.5
ticks on SUZLON (₹52)** — you cannot slip less than one tick.

Spread comes from the **Corwin–Schultz** high/low estimator (published; computable from OHLC we already
store), cached per symbol.

**Tick size lives in `config/universe.yaml`, not in code.** NSE's standard is ₹0.05 but sub-₹250
segments differ — **unverified, so it is a config table with a source note, not a guess.**

**The sensitivity curve is mandatory**, because slippage is the single biggest lever the audit found:
5bps → −5.42, 3bps → −2.73, 2bps → −1.36, **1bp → +0.01**. That curve is what made the intraday verdict
robust rather than an assertion — it proved the answer wasn't just our cost model being harsh.
**Any strategy whose verdict flips within the plausible range is reported as *undetermined*, not a
winner.**

**Changes our mind:** real quote/spread data would replace the estimator. The curve stays regardless.

---

## D12 — `qty = 0` skips the trade. Never `max(1, ...)`.
**2026-07-15**

V2's `qty = max(1, min(notional_qty, risk_qty))` forces at least one share even when that blows the 2%
risk cap. **Not theoretical:** 3 of the original 19 stocks already breached it, and POWERINDIA at
₹33,980 would risk **17% of the fund on a single share** — 8.5× the cap. The same bug exists in live
(`signals.service.ts:114`), not just the backtest.

> ⚠️ **2026-07-15 — the "3 of 19" number needs a re-look; the decision does not.** That figure was
> computed analytically assuming `RISK_PER_TRADE_PCT = 0.02`. **N5 is now confirmed: it was `2.0`, so
> V2's risk cap never bound at all** (see CLAUDE.md). With a 200% budget `qty_risk` never constrained
> anything, so the *breach* was not 3-of-19 — it was structural, and `max(1, ...)` was rarely even
> reached. **`qty = 0` skips remains correct** — arguably more so, since it is the only bound left once
> you learn the cap you were relying on was off.

**A trade that cannot be sized within the risk budget is a trade that should not be taken.**

This also removes the need for the ₹4,000 price-ceiling hack in the universe, which currently excludes
9 otherwise-liquid names (MARUTI, TITAN, ULTRACEMCO, HAL…).

**Changes our mind:** nothing.

---

## D13 — Ground truth never lives in /tmp. Learned the hard way.
**2026-07-15**

The attribution ladder (~380 LOC) and its ground-truth CSVs lived **only** in an ephemeral `/tmp`
scratchpad. It was identified as a P0 rescue item, confirmed present at 20:0x, and **reaped at ~20:21
— before the rescue ran.** The code is gone and must be rewritten.

The data survived **only because both databases were still running.** It is now committed at
`tests/fixtures/v1_reports.csv` (1,761 rows) and `v2_reports.csv` (718 rows), regenerable via
`scripts/dump_ground_truth.sh`.

**Rule: anything that proves a number is right gets committed the moment it exists.** If it took real
compute or a live system to produce, it does not live in a temp directory. The rewrite is feasible
(V1's engine is 96 lines and still in git), but this cost real work that a `cp` would have saved.

**Changes our mind:** nothing.

---

## D14 — Config is loaded explicitly, as data. Nothing reads the environment at import time.
**2026-07-15**

D1 said "one config both runtimes read". This is the sharper, cheaper rule underneath it, and it was
**earned, not reasoned**: V2's 2% risk cap (FEAT-005 — a safety feature it deliberately built) **never
ran once**, and the mechanism was an env var read at import time.

The chain, traced end to end:
1. `.env` sets `RISK_PER_TRADE_PCT=2`, meaning *2 percent*.
2. `backtest_config.py:52` reads it as a **fraction**: `_f("RISK_PER_TRADE_PCT", 0.02)` → **`2.0`**.
3. `base.py:218`: `risk_budget = current_capital * 2.0` → **a 200% risk budget.**
4. `qty_risk` is then ~100× too large, so `min(qty_notional, qty_risk)` **always picks `qty_notional`**
   — every intraday position sizes to the full 5× cap, ₹50,000, costing **₹53/round trip, 95%/yr.**

**The part that makes it a rule rather than a bug:** whether the cap worked depended on **the order of
two import lines in a different file.** `main.py:16` calls `load_dotenv()` *after* its imports, which
would have frozen the safe default `0.02` — but `routers/backtest.py:6` imports `db.client` (which
calls `load_dotenv()` at module scope) **one line before** it imports `strategies` → `backtest_config`.
The env var wins by one line. Nobody chose that. Nobody could see it.

**So, in v3:** rates live in `config/*.yaml` and are loaded by an explicit call. No module-level
`os.getenv`. Secrets stay env vars, documented by name only — they are the one thing that *must* come
from the environment, and they are never rates.

**This is also why the golden tests can exist at all.** `export BT_GST_PCT=0` would silently move
₹53.0046 while every test still passed — against a different world than the one it claimed to test. A
test cannot pin a number that an env var can move.

**Consequence for P6:** the parity gate's `v2_compat` mode must set `RISK_PER_TRADE_PCT = 2.0`
explicitly, because the stored fixtures were produced by an engine with **no working risk cap**.
Without that, R0 cannot reconcile and will look like a port bug.

**Related:** `DHAN_MAX_RISK` (₹2,000 code default vs ₹200 documented, absent from every config) and
`RISK_PER_TRADE_PCT` meaning *2* in V1, *0.02* in V2's `risk.ts`, and *2.0* in V2's
`backtest_config.py`. **Three names, three unit conventions, no shared schema.**

**Changes our mind:** nothing. This one cost real money.

---

## D15 — Regime filters are PRE-REGISTERED here, before any backtest data exists.
**2026-07-16**

The owner, a real trader, noticed something worth acting on: *"on some trading sessions almost every
strategy fails."* When **many independent strategies fail on the same day**, the cause cannot be any
one strategy's quirk — it is a **market-wide condition**. So the honest question is: can we identify
that condition **at 09:15**, before trading, and stand aside?

This is a **market-condition (regime) filter**. It is also the single most overfittable idea in
trading: take the losing days, look backwards, and you will *always* find "a condition" that would have
avoided them — and it will almost never generalise. That is the exact failure (a pattern in the past
that does not repeat) that gave V1/V2 their fake winners.

**The only defence is pre-registration.** A filter chosen *before* seeing which days lost, then tested
on days not used to invent it, is a hypothesis. A filter reverse-engineered from the losing days is a
lie. There is no backtest data in this project yet, so this is the maximally-credible moment to write
the hypotheses down. **These three are the owner's, from watching real sessions — not data-mined:**

1. **Event / expiry day** *(exogenous, cannot be overfit — build first).* F&O expiry and
   Budget/RBI/Fed/election dates are fixed **weeks in advance**. There is nothing to fit. Built as a
   **sourced calendar**, exactly like the NSE session calendar (`data/calendar.py`). ⚠️ NSE changed its
   expiry weekday recently — **source the rule, do not type it from memory** (the D13/friction rule
   applied to dates).
2. **Big gap open** *(measurable at 09:15; guard the threshold).* `|open − prev_close| / prev_close`.
   Cleanly ex-ante. The danger is a magic threshold, so it ships as a **sensitivity curve over gap
   size** (the D11 rule), never a single tuned number.
3. **Choppy / rangebound** *(the dangerous one — test last, most sceptically).* "Choppy" is usually a
   **hindsight** label. To be a filter it needs a 09:15–10:00 measurable that *predicts* chop (opening-
   range width vs ATR, India VIX), not one that describes it after the whipsaw.

The owner **did not** cite "index falling hard" — so his bad days are structural (gaps, chop, events),
not a broad long-only sell-off. That is consistent with intraday breakout/reversion specifically.

**How it connects to the live verdict.** A filter that trades *less* pays *less* friction, and friction
is why fast intraday is dead. Intraday at 180 trades/yr loses to NIFTY; the ~2×/month variant is the
one open question ([[v3-friction-arithmetic]]). A regime filter that keeps only good-condition days is a
concrete way to *reach* ~2×/month — so this is not a side-quest, it may be what decides the open
question.

**The honest limit, stated so it cannot disappoint later:** a filter can only **protect** edge, never
**create** it. Fewer trades × zero per-trade edge is still zero. So D15 does **not** replace the
Phase-1 question "does edge exist?"; it rides beside it. Each filter is tested through the **same gate**
(a friction/edge prior, DSR-corrected), and counts as **trials in the P10 ledger** — a filter is a
degree of freedom, and unpriced degrees of freedom are how 1,860 cells became 93 fake winners.

**Sequencing:** the event/expiry calendar is a data-layer artifact and can be built alongside P3/P4.
The gap and chop filters need the engine, so they are tested at/after P11, as pre-registered variants.

**Changes our mind:** if, once data exists, "all-strategies-fail" days do **not** cluster by any
ex-ante condition — i.e. bad days are indistinguishable at 09:15 from good ones — then there is no
filter to build, and we say so. "Insufficient evidence" remains a legitimate answer here too.

---

## D16 — Session membership is removed-and-recorded; only integrity quarantines.
**2026-07-16**

The write boundary was conflating two different questions, and real data broke it. The live smoke
test (P3's fetch layer) pulled real RELIANCE 1D and found what no synthetic fixture had: yfinance
returns, **every year**, bars that are not normal sessions — a **Diwali Muhurat** session (real, ~2M
volume, ceremonial ~1h, which the XBOM calendar does not model), zero-volume **holiday** placeholders,
and (for `period="max"`) a decade of **pre-2006** data the calendar cannot speak to.

The validator flagged all of these as `non_session_day`, and the store quarantines per **year** on any
violation. So one Muhurat bar quarantined the whole year — and every year has a Diwali. A real pull
was **almost entirely unreadable.**

The fix is to see that these are two different questions:
- **Membership** — *is this date a real trading day?* A non-session bar is **extraneous**, not corrupt.
- **Integrity** — *is a real session-day bar well-formed?* A high-below-low bar **is** corrupt.

**The owner's call (2026-07-16):** *"remove + record"* and *exclude Muhurat.* So membership moved to
`partition_sessions()`: non-session and pre-calendar bars are dropped from what gets stored and written
to `meta/removed_bars.parquet` with a reason (`non_session_day` or `outside_calendar_coverage`) and
their OHLCV — **"never silently drop" becomes "never drop without a record."** `validate()` now checks
only integrity, on data already known to be real sessions. `non_session_day` and the `calendar_coverage`
crash both leave `validate()`; keeping them would be checks that cannot fire (the rows are gone), the
dead-check antipattern D-nothing/mutation-testing already taught us to delete.

**Result, on real data:** RELIANCE 1D → **21 clean years, 0 quarantined**, 2006–2026 readable (4,918
bars); 2,729 pre-2006 + 18 non-session bars removed and recorded (the 18 include 2008-11-27, the real
Mumbai-attacks closure that yfinance carries a junk bar for). Before this, unusable.

**Muhurat is excluded, not kept.** It is a real session, but ~1h of unrepresentative ceremonial
liquidity would leak noise into intraday results. We store raw and derive, so this is cheap to revisit
if a reason appears.

**Changes our mind:** a use for the Muhurat session (e.g. a strategy the owner runs specifically then)
would flip it from "remove" to "keep" — it is one entry in the calendar. Nothing else changes.
