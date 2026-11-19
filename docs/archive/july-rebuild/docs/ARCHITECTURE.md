# Architecture — Phase 1 (prove edge)

**Scope of this document: Phase 1 only.** Phase 1's deliverable is a **decision**, not a service:
*does any edge exist that survives real costs at ₹10,000 per slot?*

**Explicitly out of scope until Phase 1 answers yes:** API, frontend, broker/Dhan integration,
Telegram, Docker, live scanner, database server. Those are Phase 2+, and Phase 2's design is
downstream of Phase 1's answer.

Plain-language version: [USER-GUIDE.md](USER-GUIDE.md). Terms: [GLOSSARY.md](GLOSSARY.md).

---

## 1. Stack

| Choice | Why |
|---|---|
| **Python 3.12 + uv** | Phase 1 produces a decision, not a service. |
| **No NestJS / React / Postgres / Docker** | Every tier deleted is a tier that cannot drift. V2's engine is littered with "MUST match `apps/api/src/common/risk.ts`" comments — that burden exists **only** because sizing was implemented twice. One runtime, one source of truth. |
| **Parquet + DuckDB (no server)** | 60 stocks × 15y daily ≈ 225k rows. DuckDB gives SQL-over-parquet with zero setup — and **preserves the owner's ability to audit by SQL**, which is exactly how the N6 corruption was found. |
| **numpy / pandas, NOT polars** | The ported engine must stay **line-comparable to V2's `base.py`** for the parity gate. Rewriting in polars destroys the "is it the same?" argument. Port first. 60 stocks never needs optimising. |
| **Drop pandas-ta** | Unmaintained; its conventions are a silent-divergence risk. Our strategies need SMA / rank / ATR / VWAP ≈ 40 LOC of testable numpy. |
| **pytest + hypothesis** | Property tests for the data validator: generate random OHLC, assert invariants. |

---

## 2. The core abstraction: the slot is the atom

The owner funds **₹10,000 per pair**, on go-live. V2 made a "pair" = (stock × strategy). That cannot
express a cross-sectional strategy, which ranks 60 stocks and holds the best 6 — the capital rotates
between stocks.

The generalisation: **the thing he actually funds is a concurrent position**, not a stock.

```python
@dataclass(frozen=True)
class InstrumentSet:
    id: str                       # "RELIANCE" | "NIFTY200"
    symbols: tuple[str, ...]

@dataclass(frozen=True)
class Cell:                       # the unit of TESTING and of FUNDING
    instrument_set: InstrumentSet
    strategy: str
    slots: int                    # 1 for time-series; K for cross-sectional top-K
    @property
    def capital(self) -> float:
        return self.slots * 10_000
```

- Time-series (`RELIANCE × ORB`) → `slots=1` → **₹10k**. Exactly the owner's model, unchanged.
- Cross-sectional (`NIFTY200 × Momentum-12-1`, top 6) → `slots=6` → **₹60k**.

> **Tell the owner this plainly and early: a top-6 cross-sectional strategy is not a ₹10,000
> commitment, it is ₹60,000.** Each of the 6 sleeves is its own ₹10k at 1×, so the per-position cost
> arithmetic is *identical* to a time-series cell — which is exactly what lets one friction gate apply
> to both.

**This also matches the owner's own instinct** ("if in future we need swing or equity trading then we
create a separate web application for it and we same backend") — the backend is shared because the
funding unit is shared. Arrived at independently.

**The ledger enforces it.** Both engines emit `list[Trade]` carrying a `slot_id`; `Ledger` asserts
`max_concurrent(slot_ids) <= cell.slots`. A strategy that quietly holds 9 names when it declared 6
**fails loudly** instead of silently spending money that does not exist.

---

## 3. Two engines, one entry point, one result

`generate_signals(df)` genuinely cannot express a cross-sectional ranker — that is V2's ceiling, and
pretending otherwise is how you get a fake abstraction. The honest unification is at the **entry point
and the ledger**, not the signal function:

```python
class TimeSeriesStrategy(Strategy):
    def generate_signals(self, df) -> DataFrame:        # V2's interface, kept
        ...                                              # adds signal / stop_loss / target

class CrossSectionalStrategy(Strategy):
    def generate_targets(self, panel: Panel) -> DataFrame:
        ...                                              # index (rebalance_ts, symbol), col: weight

def run(strategy, panel, capital, flags) -> Result:      # THE single entry point
    ...                                                  # dispatches on spec.kind
```

```
StopEngine       per symbol; port of V2's simulate(); intrabar High/Low stops   ─┐
                                                                                 ├─→ Ledger → Metrics → Result
RebalanceEngine  panel-wide; next-open fills at rebalance dates; no stops       ─┘
```

**Cross-sectional momentum has no per-trade stop.** Forcing one on it would be modelling fiction. Two
engines is the truthful design; one `Trade`/`Result` type is what makes them comparable.

**Cross-engine invariant (a real test, ~30 LOC):** a degenerate cross-sectional strategy that always
holds exactly 1 name must produce a trade list matching `StopEngine`'s for the same signals.

---

## 4. Registry: decorator + dataclass

V2 used **three parallel dicts keyed by a magic string** (`STRATEGY_REGISTRY`, `STRATEGY_TIMEFRAMES`,
`STRATEGY_HOLD_DURATIONS`). A typo silently yields `bucket=None`, which — via F11's bare `except` —
silently disables long-only, the time-stop, the trail *and* the R-target, and still returns a
plausible-looking result.

```python
@dataclass(frozen=True)
class StrategySpec:
    name: str
    kind: Literal["time_series", "cross_sectional"]
    timeframe: str
    bucket: HoldBucket        # ENUM, required ctor arg — never a lazy upward import
    min_bars: int             # warmup — kills the walk-forward starvation (F8)
    slots: int
    proposal: Proposal        # the friction prior — REQUIRED to register

@strategy(spec=StrategySpec(...))
class XSMomentum121(CrossSectionalStrategy): ...
```

A typo becomes an **ImportError at collection time**, not a silent `None`. And `Proposal` being
required is what wires the friction gate to registration itself: **you cannot register a strategy that
has not stated its prior.**

---

## 5. The friction-budget gate — the key new component

**~200 LOC, needs zero data, ships SECOND (before the data layer).** Neither V1 nor V2 had any version
of this, and it is the cheapest thing in the project.

```
qty, N, rupees_at_risk = capital.size(entry, stop, bucket)   # the REAL sizing fn, not a magic N
friction = cost_rt(N) + 2 × qty × max(tick, k × spread)      # ported CostModel + slippage

friction_load     = T × friction / S                  # T trades/yr, S = ₹10,000 slot
required_avg_R_be = friction / rupees_at_risk         # None when there is no stop — see below
required_edge_bps = friction / N × 10_000
p_breakeven(RR)   = (1 + f) / (1 + RR),  where f = friction / rupees_at_risk
```

**The gate calls `capital.size()` rather than taking a notional** — that is what makes the gate and the
engine structurally incapable of disagreeing about position size, which is the "MUST match `risk.ts`"
failure D1 exists to prevent.

**Two corrections to the formulas as first written:**
- **`/(S × 0.02)` → `/rupees_at_risk`.** ₹200 is the *budget*; actual rupees at risk equal it only when
  the **risk** cap binds (stop ≥ 0.4%). For tighter stops the **notional** cap binds first and real
  risk is *less* than ₹200 — so the old formula understated `f`. The two coincide in the common case;
  using the real number makes it exact rather than approximate.
- **The gate needs TWO arms, because `required_avg_R_be` is undefined for cross-sectional momentum.**
  D9 says XS momentum has **no per-trade stop** ⇒ no `risk_per_share` ⇒ **no R**. The R arm returns
  `None` for it and the **`required_edge_bps`** arm does the work (>73.9 bps per rebalance at 2×). A
  gate that only spoke in R could not price the one strategy with real evidence behind it.

**Its test is that it reproduces already-established facts — each with its notional stated.**
⚠️ **This table is COSTS-ONLY**, matching how the original figures were derived. Real friction is
roughly **double**: §5's own formula adds slippage, which the headline omitted. See below.

| Case (entry ₹100) | Notional | Formula (costs only) | Result |
|---|---:|---|---|
| Intraday, T=180, **5× cap binds** (stop ≤ 0.4%) | ₹49,900 | `180 × 53.03 / 10,000` | **95.5%/yr** |
| Intraday, T=180, 0.517% stop — *the docs' original case* | ₹38,600 | `180 × 41.02 / 10,000` | **73.8%/yr** ✓ |
| Intraday, T=180, 2% stop | ₹10,000 | `180 × 10.63 / 10,000` | **19.1%/yr** |
| Quarterly cross-sectional, T≈6, incl. ₹14.75 DP | ₹10,000 | `6 × 37.00 / 10,000` | **2.2%/yr** |

⚠️ **The correction that produced this table.** ROADMAP:18 said "₹50k intraday ≈ ₹41". At ₹50,000 the
model gives **₹53.00**; ₹41 is the cost at **₹38,675**. And "₹25" for quarterly XS **dropped the ₹14.75
DP charge** — it is ₹36.97. Neither was a typo. **Intraday cost is a rate — 10.60 bps of notional — so
the rupee figure is an *output of sizing* and moves with stop width.** A rupee constant in prose cannot
carry the assumption it depends on, which is why it drifted from its own formula within one sitting.
**Rule: never quote a rupee cost without its notional.** (`tests/test_costs_golden.py` now enforces it.)

⚠️ **A SECOND correction — the headline omitted slippage, which is ~half of friction.** §5's formula
says `friction = cost_rt(N) + 2 × qty × max(tick, k × spread)`, but every number the docs quoted was
the `cost_rt(N)` term alone. On a ₹100 stock with a ₹0.05 tick, one tick is 5 bps of price, so
slippage ≈ cost. **The honest table** (`make friction`, entry ₹100 — the tool prints this, so it cannot
drift again):

| Stop | Notional | Cost | Slippage | **Friction** | **Per year @ T=180** |
|---|---:|---:|---:|---:|---:|
| 0.4% | ₹49,900 | ₹53.03 | ₹49.90 | **₹102.93** | **185.3%** |
| 0.517% | ₹38,600 | ₹41.02 | ₹38.60 | ₹79.62 | 143.3% |
| 1% | ₹20,000 | ₹21.26 | ₹20.00 | ₹41.26 | 74.3% |
| 2% | ₹10,000 | ₹10.63 | ₹10.00 | ₹20.63 | **37.1%** |
| **Quarterly XS, T=6** | ₹10,000 | ₹37.00 | ₹10.00 | ₹47.00 | **2.8%** |

**Slippage is price-dependent, so this is not a universal doubling.** On RELIANCE (₹1,300) a tick is
0.38 bps and slippage is a rounding error; on SUZLON (₹52) it is 9.6 bps — **19.2 bps round trip, ~2×
the entire cost model** — and dominates everything. The gate takes `entry_price` for exactly this
reason. **There is no "the" friction number**; there is friction at a stated price, stop and frequency.

**The ~40× gap survives at 66× (185.3 / 2.8), and the intraday NO gets *stronger*.** It no longer
depends on picking the right rupee figure: **every intraday row above loses to NIFTY's free ~12% — by
3× at best.** That is why the gate ships before the data layer, and why it reports a **curve**.

**And the case the curve says is still open:** intraday at **T=24** with a 1% stop is **9.9%/yr** —
under the hurdle. It needs **0.206R** per trade to break even, against V2's measured **0.122R**. So the
honest question is not "does intraday work" but *"is there a signal ~2× better than anything V1/V2
produced, that fires twice a month?"* That is what P11's intraday pair is for.

**How it gates:**
```python
assert prop.expected_avg_R_gross > required_avg_R_be * MARGIN     # MARGIN = 2.0
```
A strategy that cannot clear **2×** its friction on **its own author's optimistic prior** never gets
written. `MARGIN=2.0` is justified, not arbitrary: V2's intraday book measured at ~0.5× (₹2 spent per
₹1 earned), so 2× demands 4× the realised edge/friction ratio of anything V1/V2 ever produced — and
50%+ out-of-sample decay is the norm.

**It also runs post-hoc** against *realised* trade counts. A strategy whose prior claimed 40 trades/yr
but backtests at 300 gets flagged — **the prior being wrong is itself a finding.**

Owner-facing outputs (both derivable, both matching the measured `avgR 0.122 → −0.187`) — **and both
must name the stop width they assume**:
> *"At a **0.52% stop** (₹38,675 deployed), every intraday trade must earn **0.205R** just to pay the
> toll. At a **0.4% stop** (₹50,000 — the 5× cap) it is **0.265R**. Your measured gross edge was
> **0.122R**. You are paying ₹2 to earn ₹1."*
> *"At 2:1 reward:risk, a frictionless coin-flipper breaks even at **33.3%** wins. You need **40.2%**
> at a 0.52% stop, **42.2%** at the 5× cap."*

---

## 6. Sizing — and one deliberate deviation from V2

```python
qty_notional = floor(per_slot * leverage(bucket) / entry)   # ₹50k intraday (5×) / ₹10k delivery (1×)
qty_risk     = floor(per_slot * 0.02 / risk_per_share)      # ₹200 / stop distance
qty = min(qty_notional, qty_risk)
if qty == 0:
    skip_trade()        # F10 FIX — never max(1, ...)
```

**F10/N11 fix:** V2's `qty = max(1, min(...))` forces a share even when that blows the 2% cap
(3 of 19 stocks already breached it; POWERINDIA at ₹33,980 would risk 17% of the fund on one share).
**A trade that cannot be sized within the risk budget is a trade that should not be taken.** This also
removes the need for the ₹4,000 price-ceiling hack in the universe.

**Deliberate deviation — no compounding in Phase 1.** Fixed ₹10k per slot on every trade. V2
compounded per-cell equity, hit geometric inflation (+639%), then bolted on `cap_position_value` to
hide it. Phase 1 measures **edge**; compounding makes ROI path-dependent and non-comparable across
cells. It also **does not match reality** — the owner *tops up* ₹10k per pair; it is not a compounding
bankroll. Report **avgR**, **net ₹/trade**, and **annualised ₹ on ₹10k**.

Because this deviates from V2, it becomes an **explicit ladder rung**, so the port can still reconcile
to V2 exactly *before* the deviation is switched on.

---

## 7. Data layer — the thing that does not exist today

V2 has **no validation at all**. This is the weakest area in the system and it sits underneath every
number ever computed.

```
artifacts/data/
  raw/        {symbol}/{timeframe}/{yyyy}.parquet   # auto_adjust=False, exactly as fetched
  actions/    {symbol}.parquet                      # splits + dividends
  adjusted/   {symbol}/{timeframe}.parquet          # DERIVED, rebuildable, disposable
  quarantine/ {symbol}/...                          # failed validation — never silently dropped
  meta/       fetch_log.parquet, validation_report.parquet, spread_estimates.parquet
```

**Store raw, derive adjusted, never splice.** `auto_adjust=False`, explicit, on **every** call (fixes
N7). Compute adjustment factors ourselves from the actions table. This makes N6 **structurally
impossible for splits/dividends**: the cliff came from splicing two differently-adjusted series, and
raw prices do not change retroactively.

🔴 **N7 is worse than "not explicit", and it lands on P6, not here. CONFIRMED 2026-07-16 by reading
the code.** V2's `history.py:113` and `:126` call `ticker.history()` with **no `auto_adjust` argument
at all**, and `apps/engine/requirements.txt:5` pins **`yfinance` bare, with no version**. So the
adjustment basis is whatever the installed yfinance defaults to — and on the version available here
(**1.4.1**, signature read directly, not recalled) that default is **`auto_adjust=True`**.

⇒ **V2's backtest database holds auto-ADJUSTED prices, not raw ones.** v3 stores raw and derives
adjustment itself (above). Those are different series.

⇒ **P6's `v2_compat` must feed the engine auto-adjusted data, or R0 will never reconcile — and it
will look like a port bug.** This is **N5's twin**: a second place where `v2_compat`'s job is to
reproduce V2's wrongness faithfully rather than fix it. Do not "correct" it there.

⚠️ Unverified and worth one check in P6: bare pin + no explicit argument + upsert-never-deletes means
rows written under an older yfinance (when the default was `False`) would still be sitting in the same
table as rows written under a newer one. If so the stored series is **internally mixed**, not merely
adjusted. Confirm before trusting any single stored number.

**N8 is misfiled and costs the port nothing.** This section says "that MultiIndex is *why* the
positional rename existed" — true, but it happened in the **scanner**, not the data layer.
`history.py:130` already selects **by name** (`df[['Open','High','Low','Close','Volume']]`). The blind
`df.columns = ['Open',...]` rename lives in `scanner/live_scanner.py:140,236,253`,
`scanner/analyze_reversals.py:23` and `scanner/simulate_trailing.py:365`, paired with `yf.download()`.
**The scanner is dropped**, so N8 arrives in v3 as a validator check (`schema`) and nothing more.

**But that alone does not fix the owner's actual 3 cases — and this matters.** VEDL and TMPV are
**demergers**. A demerger is neither a split nor a dividend and **will not appear in yfinance's
actions**. Factor reconstruction cannot catch them. So we need both:

- **(a)** raw + own adjustment from actions → handles splits / bonus / dividends
- **(b)** an **unexplained-jump detector**: `|log return| > 20%` on 1D not explained by a known action
  ⇒ **quarantine the symbol and refuse to backtest through it** until an explicit, reviewed entry
  exists in `config/known_actions.yaml`.

**You cannot auto-solve a demerger. You can refuse to silently trade through one.** That is the honest
design. VEDL / TMPV / TRENT become **test fixtures** — detected before allowlisting, resolved after: a
regression test against a real, SQL-verified bug.

**Other decisions:**
- **Full re-pull for 1D, always.** The incremental path bought nothing and cost correctness. 60 symbols
  × 15y = seconds. **Delete the optimisation.**
- **Pull 15y, not 5y.** V2's `history.py:23` hardcodes `period="5y"`; `"max"` is free and ~triples the
  sample. For a monthly-rebalanced strategy this is the difference between **60 and ~180
  observations** — i.e. between "insufficient evidence" and an actual verdict.
- **Intraday must stay incremental** (yfinance's 60d cap) ⇒ add an **overlap assertion**: re-fetch the
  overlapping window and assert stored ≈ fetched within one tick. Mismatch ⇒ the series was restated
  ⇒ quarantine and rebuild.
- **Named columns, never positional** (fixes N8). Handle yfinance's MultiIndex explicitly via
  `droplevel` — that MultiIndex is *why* the positional rename existed — then select by name and raise
  `KeyError` if absent.

**Validator at the write boundary — ✅ BUILT (P3), `src/trading/data/validate.py`.** Nothing enters
`raw/` without passing. **It reports; it never drops** — V2's fetch ended in `.dropna()`
(`history.py:130`), so bad rows vanished while the row count still looked healthy. A validator that
silently discards is worse than none: it manufactures the appearance of clean data.

🔴 **Membership and integrity are SEPARATE — the split that keeps the store usable (D16).** Two
different questions were being answered by one check, and it broke on real data:
- **Membership** — *"is this date a real trading day?"* — is `partition_sessions()`. Non-session bars
  (Diwali Muhurat, holidays, weekends) and pre-calendar bars are **removed and recorded** to
  `meta/removed_bars`, **not** quarantined. The owner's decision (2026-07-16): "never silently drop"
  becomes "never drop without a record." Without this, a single Muhurat bar quarantines the whole
  year, and **every year has a Diwali** ⇒ a real RELIANCE pull was almost entirely unreadable.
- **Integrity** — *"is this session-day bar well-formed?"* — is `validate()`. What survives the
  partition is real session data; corruption there quarantines the series.

**Integrity checks that ship (each independently reachable by a mutation test):** `schema` (named
columns, dtype) · `index_type` · `index_tz` · `duplicate_timestamps` · `index_order` · `timeframe` ·
`empty` · `nan` · `positive_prices` · `positive_volume` · `ohlc_consistency` · `session_hours` ·
`stale`. **Membership** (`non_session_day`, `outside_calendar_coverage`) is `partition_sessions`' job,
run *before* validate — putting it in validate would be a check that cannot fire (the rows are already
gone), the same dead-check antipattern below.

**End to end on real data:** RELIANCE 1D → 21 clean years, **0 quarantined**, 2006–2026 readable (4,918
bars); 2,729 pre-2006 + 18 non-session bars removed and recorded. Before the split, that pull was
unusable.

⚠️ **This section previously specified 9 checks. Three of them cannot fail, and mutation testing
proved it** — each was implemented, deleted, and the suite stayed green:

| listed check | why it can never fire alone |
|---|---|
| `high >= low` | implied: `low <= min(o,c) <= max(o,c) <= high` |
| `low <= close <= high` | implied by the same two bracket conditions |
| bar-count vs the calendar | implied by session + grid + no-duplicates. A 15m session has exactly **25** legal slots; a 26th bar must be off-grid, a duplicate, or on another session (which *raises* the allowed count) — all already caught |

**A check that cannot fail is a coverage claim the suite cannot honour.** They are folded in, and
both implications are machine-checked in `tests/test_validate.py` rather than asserted in prose. The
13 that ship are each verified to turn the suite red when broken.

🔴 **"weekdays only" is WRONG — do not reintroduce it.** NSE runs full Saturday sessions:
**2025-02-01** (Union Budget day, one of the year's highest-volume sessions) and **2024-01-20** (live
session from the disaster-recovery site), both the normal 09:15–15:30 length. That rule quarantines
Budget Day. The validator asks the calendar (`data/calendar.py`) and never infers a session from the
day of the week. There is a regression test on that exact date.

🔴 **The unexplained-jump detector is NOT here — it cannot be, and this is structural.** `raw/` is
`auto_adjust=False`, so it holds real split cliffs **by construction**: a 1:10 split is a legitimate
−90% raw return. D10's detector only works by asking *"is this jump explained by a known action?"*,
and answering needs the **actions table** ⇒ **P4 owns it.** Running it at this boundary without
actions would quarantine every split in the universe. The seam is `ValidationReport.violations` — P4
appends to it and restructures nothing.

---

## 8. Slippage — `max(1 tick, k × spread)`

V2's flat 5bps is **wrong in both directions**: 13 ticks on RELIANCE (₹1,300), and an impossible
**0.5 ticks on SUZLON (₹52)** — you cannot slip less than one tick.

Spread source: we have no quote data, so use the **Corwin–Schultz** high/low spread estimator (a
published estimator computable from the OHLC we already store), cached per symbol as a median in
`meta/spread_estimates.parquet`, with a bps floor fallback.

**Corwin–Schultz lands in P3, not P1 — a recorded decision, not an omission.** CS is a *spread source*;
P1 owns the *rule*. Its consumer (`meta/spread_estimates.parquet`) is a P3 artifact, so shipping it in
P1 means committing an estimator with no caller. More importantly, **CS needs a calibration decision
that requires real OHLC**: it produces **negative** spread estimates on a material fraction of days, and
the convention for handling them (truncate at zero vs. average before truncating) materially moves the
median. **Choosing that blind is a guess** — exactly what D11 refuses to do about tick sizes. P1 ships
the seam instead: `per_share(price, tick, spread=None, ...)` takes spread as an optional input and falls
back to the bps floor. P3 supplies it. No signature change, no rework.

**Tick size is per-instrument, in `config/universe.yaml`, not hardcoded.** NSE's standard tick is
₹0.05 but sub-₹250 segments differ — **unverified, so it is a config table with a source note, not a
guess in code.**

**Non-negotiable:** because slippage is the single biggest lever (the audit's sensitivity curve:
5bps → −5.42, 3bps → −2.73, 2bps → −1.36, **1bp → +0.01**), **every verdict must ship a slippage
sensitivity curve.** It is a required field of `Result`, not an option. **Any strategy whose verdict
flips within the plausible slippage range is reported as *undetermined*, not as a winner.**

---

## 9. Walk-forward, and multiple testing

### Walk-forward with warmup (the F8 fix)

```python
# V2 (advanced_backtest.py:109):  window = df.iloc[start:end]          # starved
# v3:
data_window = df.iloc[start - spec.min_bars : end]                     # warmup PREPENDED
trades = [t for t in run(...) if t.entry_ts >= df.index[start]]        # counted only in-window
```
A trade is attributed to the fold it **enters** in, and may complete past the boundary on real future
bars — that is holding, not lookahead, and it avoids truncation bias.

**Opinionated:** Phase 1 declares priors and does **not optimise parameters**, so this is closer to a
single out-of-sample test than a true walk-forward. Do not overbuild purge/embargo — those matter for
parameter fitting. Instead:
- a **physically separate holdout** (research 2010–2024, holdout 2025–2026) enforced in
  `store.load(split=...)`; the holdout **raises unless `--unlock-holdout` is passed**, so cheating
  requires an explicit, logged act;
- rolling folds for **stability reporting** only;
- the **multiple-testing correction** does the real work.

### Multiple testing: DSR primary, BH-FDR cross-check

**Deflated Sharpe Ratio** (Bailey & López de Prado) as primary — it directly answers the actual
question ("given N trials with this spread of Sharpes, is the best one still real?") and adjusts for
N, skew, kurtosis **and sample length**, all of which bite hard on a short, fat-tailed Indian sample.
Accept iff `DSR > 0.95`.

*Why not the others:* **White's Reality Check** needs a bootstrap over all strategies' joint returns —
heavier, and its power collapses when strategies are correlated (ours will be). **Hansen's SPA** fixes
that but is more machinery than 4 strategies justify. **Bonferroni** is too conservative.
**BH-FDR at q=0.10** is the cross-check for "which cells are winners" — more powerful than Bonferroni
and valid under positive dependence, which is what correlated equity strategies are.

**Where V2 actually sinned, and a subtlety:** it ran 1,860 cells uncorrected (~93 expected false
winners). But **N=1,860 is also wrong** — the hypothesis under test is *the strategy*, not the cell.
Aggregate cells to a strategy-level equal-weight return series across the instrument set, and set
**N = strategies × variants tried**.

**Trials ledger** (`artifacts/trials.jsonl`) — append-only, **written by the runner, not by hand.**
Every strategy/parameter combination ever evaluated. This makes N auditable and makes quiet
under-reporting of N require **lying to a file**.

**The component's own test is the point:** *100 pure-noise strategies must produce **zero**
discoveries at q=0.10* — proving the correction would have caught V2's exact failure mode.

### Baselines — the honest hurdle

- **Random-entry null:** same trade count, same holding period, same friction. If a strategy cannot
  beat a coin flip *paying identical tolls*, it is nothing.
- **NIFTY buy-and-hold.** **A delivery strategy netting 8%/yr is a FAILURE** — NIFTYBEES pays ~12% for
  free. Phase 1's success criterion is **excess over NIFTY buy-and-hold after costs**, not "positive".

---

## 10. Verification — how we know the port is right

This is the rescued ladder's reconcile-both-ends technique, promoted to a gate.

**The port gets a compat mode.** `EngineFlags(v2_bugs=True)` deliberately **re-enables** the N1 gap
bug, F10's `max(1,…)`, and V2's compounding+cap sizing.

**End A — external ground truth.** V2's stored `BacktestReport` ROI is truth **we did not produce**,
now committed at `tests/fixtures/v2_reports.csv` (718 rows) and `v1_reports.csv` (1,761 rows).
**Gate:** for every 1D swing cell, `v3.run(flags=v2_compat).roi == v2_stored_roi` within 0.05 **and
identical trade count**, on ≥95% of cells. If that passes, the port is bit-faithful.

**Then the ladder prices every fix, one rung at a time:**

```
R0  v2-compat                 ← MUST reconcile to V2's stored ROI (the gate)
R1  +fix N1 (gap-through fills)
R2  +fix F10 (qty=0 skips)
R3  +explicit bucket (F11)    ← MUST be a no-op
R4  +tick-aware slippage
R5  +constant ₹10k sizing
R6  = v3-honest               ← the research engine
```

Each rung's delta is a **measured number**: the owner learns exactly what each bug cost him.
**R3 being a no-op is itself a test** — if it is *not* a no-op, F11 was silently firing in V2 and the
audit's numbers move.

**End B — the honest end has no external truth**, so build one: ~10 **hand-computed golden trades**
(entry, stop hit, gap-through, exact ₹ costs).

> **One real Dhan contract note (PDF) remains the highest value-per-effort ask** — it converts the cost
> model from "verified against published rates" into "verified against money that actually left the
> owner's account." **Asked 2026-07-15; the owner cannot supply one.** His counter-proposal was better
> than the fallback: use **Dhan's own published charge list**, which is now the sourced `dhan_2026`
> profile in `config/costs.yaml`.
>
> **That finding was worth the ask on its own:** V2's rates were never Dhan's — `backtest_config.py:107`
> calls them "Zerodha-style", only the DP charge was Dhan-specific, they predate NSE's 01-Mar-2026
> revision, and IPFT was never modelled. **Size of it: +₹0.136 on a ₹50k round trip.** Real, worth
> fixing, and **not** an explanation of anything.
>
> **What published rates still cannot verify** (so the offer stays open): rounding conventions, NSE
> IPFT's real incidence, the GST base, and whether DP is truly ₹14.75 per instruction vs per day — that
> last one **will** bite in Phase 2 if a position is exited in parts on one day. One PDF ⇒ a golden test
> ⇒ an hour's work.

---

## 11. Directory layout

```
stock-trading/
├── README.md                      # entry point
├── pyproject.toml                 # uv, py3.12, pinned
├── Makefile                       # make data | test | friction | parity | report
├── docs/
│   ├── USER-GUIDE.md              # ← the owner reads this one
│   ├── GLOSSARY.md                # every term, one plain sentence
│   ├── REVIEW-V1-V2.md            # what to keep/drop, and why
│   ├── ARCHITECTURE.md            # this file
│   ├── DECISIONS.md               # why no compounding, why no C3, why DSR
│   └── ROADMAP.md                 # phases, sizing, dependency order
├── config/
│   ├── universe.yaml              # symbols + tick_size + listing_date + PIT membership
│   ├── costs.yaml                 # broker rates — ported, now DATA not code
│   ├── known_actions.yaml         # reviewed corporate actions incl. VEDL / TMPV / TRENT
│   └── research.yaml              # holdout dates, slot capital, gate margin
├── src/trading/
│   ├── data/        schema fetch validate actions anomaly store calendar
│   ├── core/        types capital costs slippage registry
│   ├── engine/      stop_engine rebalance_engine ledger run
│   ├── research/    friction ladder walkforward stats baselines
│   ├── strategies/  xs_momentum_12_1 xs_pead intraday_orb intraday_vwap_reversion
│   └── cli.py
├── tests/
│   ├── fixtures/    v1_reports.csv  v2_reports.csv     # ✅ RESCUED — the parity ground truth
│   ├── test_costs_golden.py       test_stop_engine.py      test_parity_v2.py
│   ├── test_data_integrity.py     test_friction_gate.py    test_walkforward.py
│   └── test_registry.py           test_stats.py            test_ladder.py
├── tools/attribution/             # the ladder, rewritten and promoted to first-class
├── scripts/dump_ground_truth.sh   # ✅ regenerates the fixtures from the live DBs
└── artifacts/                     # gitignored: parquet, reports, trials.jsonl
```

---

## 12. Key risks

| # | Risk | Mitigation |
|---|---|---|
| **R1** | Beautiful infrastructure, still no edge | The friction gate ships **second**, for ~200 LOC. Kill-cheapest-first *is* the sequencing logic. |
| **R2** | **Sample size.** Monthly cross-sectional over 5y = **60 observations.** DSR on T=60 is brutal — correctly so. | Pull **15y** not 5y (free). Widen the universe for breadth at the same T. **Accept that "insufficient evidence" is a legitimate and valuable answer — V1 and V2 both failed by refusing to say it.** |
| **R3** | ⚠️ **SURVIVORSHIP BIAS — the highest-risk open item, and fatal to cross-sectional momentum specifically.** The 60 names were chosen **today** by measured liquidity. Ranking today's liquid winners over 2020–26 **manufactures momentum**: a name became liquid *because* it went up. | Build the universe **point-in-time** (NIFTY 200 constituents as of each rebalance date). If unobtainable: include delisted/dead names and **bound and document the bias**. **This is the #1 way Phase 1 produces a confident wrong YES.** |
| **R4** | yfinance intraday capped at 60d and unbackfillable | The intraday NO rests on **arithmetic (the gate)**, not on a thin backtest. That is the honest position and it happens to be the strong one. |
| **R5** | Porting V2's bugs imports its unknowns (−12 to −47pp of intraday is unattributed; C3 never measured) | **Do not port C3.** It is a live-execution model with no place in edge discovery. Dropping it **removes** the unknown instead of importing it. Phase-1 intraday = plain fixed SL/TP + square-off. |
| **R6** | Multiple testing through the back door (interactive iteration) | `trials.jsonl` written by the runner; holdout gated behind `--unlock-holdout`. Cheating must be explicit and logged. |
| **R7** | Lookahead in cross-sectional ranking (rank on month-end close, trade that close) | Rank on close of *t*, fill at open of *t+1* — **reuse the ported next-bar rule**, do not reinvent it. |
| **R8** | yfinance earnings dates are unreliable/retro-edited ⇒ PEAD drift is manufactured | Cross-validate earnings dates against volume spikes. **Drop PEAD if dates cannot be verified.** Do not let a data dependency invent an anomaly. |
