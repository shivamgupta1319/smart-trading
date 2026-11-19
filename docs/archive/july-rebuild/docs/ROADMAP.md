# Roadmap — phases, sizing, dependency order

Every phase is **≤500 LOC and independently verifiable**. Ordering principle: **kill the cheapest
question first.** V1 and V2 both built the expensive thing first and discovered the cheap fatal
problem at the end.

Plain-language version: [USER-GUIDE.md](USER-GUIDE.md) §10.

---

## Phase 1 — prove edge (~3,350 LOC)

**Deliverable: a decision, not a service.** *Does any edge exist that survives real costs at ₹10k/slot?*

| # | Phase | LOC | Verified by |
|---|---|---:|---|
| **P0** | **Ground-truth rescue** | 0 | ✅ **DONE.** `tests/fixtures/v1_reports.csv` (1,761) + `v2_reports.csv` (718) committed; `scripts/dump_ground_truth.sh` regenerates. ⚠️ The ladder *code* (~380 LOC) was reaped from `/tmp` before rescue and must be rewritten (P7). |
| **P1** | Skeleton + `costs.py` (verbatim port) + `capital.py` + `slippage.py` | ~250 | `test_costs_golden.py`: every case **states its notional** — ₹50k intraday = **₹53.00** (v2_compat) / **₹53.14** (dhan_2026); ₹38,675 = **₹41.00** (this, not ₹50k, is where the docs' ₹41 came from); ₹10k delivery incl. DP = **₹36.97** / **₹37.00**. **No data needed.** |
| **P2** | **The friction gate** + CLI — *deliberately before the data layer* | ~200 | Reproduces **73.8%/yr** at ₹38,675 **and 95.4%/yr at the ₹50k 5× cap**, and **2.2%/yr** quarterly XS. **Zero data. P0+P1+P2 ≈ 450 LOC answers most of the intraday question.** |
| **P3** | Data: fetch + store + validate + calendar | ~400 | ✅ **DONE** (prices). Calendar (XBOM, sourced) · validator (integrity, mutation-verified) · `partition_sessions` (membership: remove+record, D16) · store (raw/quarantine/meta, per-year) · fetch (yfinance, `auto_adjust=False`, IST-naive, **live smoke test**). Real RELIANCE 1D → 21 clean years, 0 quarantined. **R3 point-in-time universe: engine + momentum wiring + 200-name anchor DONE** (`data/universe.py`, `XSMomentum(universe=…)` ranks `members_as_of`, survivorship property mutation-verified; ⬜ ONLY the ~12 NSE reconstitution `changes` events remain — `changes: []` ⇒ still biased until filled). ⬜ left: `make data`/CLI, incremental-intraday overlap, Corwin–Schultz, per-instrument tick `universe.yaml`. |
| **P4** | Data: actions + cliff detection + allowlist | ~250 | ✅ **DONE.** Cliff detector: VEDL/TRENT **detected pre-allowlist, cleared post** (live, D10); `config/known_actions.yaml` (demerger vs real_move). Actions stored; **dividend-adjusted prices derived** and reconciled to yfinance Adj Close (**0.0077%** end-to-end, 0.0000% pure). ⚠️ 20% flags real crashes too (by design). ⬜ left: wire the cliff gate into `store.read`; materialise `adjusted/`; TMPV symbol resolution. |
| **P5** | Registry + strategy ABCs + `Proposal` | ~150 | ✅ **DONE.** `src/trading/strategy/` — `HoldBucket` enum + `StrategySpec` (typo'd bucket **raises at import**, F11 fixed) + `@strategy` (runs the gate at registration; FAILED_PRIOR still registers, marked). Two ABCs (D9). Consistency checks (bucket↔timeframe cost, kind↔prior, class↔ABC) all tested; mutation-verified. |
| **P6** | StopEngine port + v2-compat flags + Ledger | ~400 | 🟡 **core DONE** — `src/trading/engine/stop_engine.py`: honest fill model, **N1 fixed** (SL 90, bar opens 82 → exit **82**, golden-tested) + F10 (qty=0 → skip) + `Result` (avgR/ROI/DD). Mutation-verified. ⬜ left: trailing stop + time-stop (swing buckets); `honest_gap_fill=False` **v2_compat reconcile (R0)** — needs V2's Postgres DB, which is LIVE on work-pc but NOT reachable from this machine (`f`); N5/N7 compat flags. |
| **P7** | Ladder, rewritten and promoted to first-class | ~300 | R0 reconciles to V2's stored ROI; **R3 asserted a no-op**; monotonic flag accumulation. |
| **P8** | RebalanceEngine + Panel + slot accounting | ~350 | ✅ **core DONE** — `src/trading/engine/rebalance_engine.py`: `Panel` (aligned prices, NaN-open skip) + `run` (next-open fills, no lookahead, rotation, slot-atom sizing, no stop → period-return metric). `src/trading/engine/ledger.py`: shared `Trade` + `from_stop_result`/`from_rebalance_result` adapters, **Ledger slot assertion** (`max_concurrent ≤ slots`, exits-before-entries tie-break so rotation reads as 1 — mutation-verified), and the **cross-engine invariant** (1-name XS ≡ StopEngine: same qty/entry/exit/gross/cost/net). Golden + mutation tested. |
| **P9** | Walk-forward (with warmup) + baselines | ~300 | 🟡 **core DONE** — `src/trading/research/walkforward.py`: `make_folds` (5 folds × 1,000 bars, full `min_bars` warmup each; even fold 0 warmed) + `run_walkforward` (warmup prepended, signals causal, entries counted in-window, exits run past the boundary — no truncation bias). `warmup=False` reproduces V2's starvation for the side-by-side: **warmup 50 trades/fold vs starved 25 — V2 lost half.** `baselines.py`: NIFTY buy-and-hold hurdle (one delivery round trip, engine cost+slippage models, simple annualisation). ⬜ left: holdout split (`store.load(split=…, --unlock-holdout)`); rolling-fold stability report; random-entry null (moves to P10). |
| **P10** | Stats: DSR + BH-FDR + trials ledger | ~250 | 🟡 **core DONE** — `src/trading/research/stats.py`: Deflated Sharpe (Bailey & LdP, accept iff DSR>0.95) + PSR + expected-max-Sharpe + Benjamini–Hochberg (numpy + stdlib `NormalDist`, **zero new runtime deps**; scipy dev-only for the BH cross-check). `research/trials.py`: append-only trials ledger (**N = `len(ledger.read())`**, understating it means deleting lines). **The headline test proves it on V2's failure mode:** DSR never flags the luckiest of 100 noise (12 seeds), BH controls the FDR *rate* (per-test <0.02 over 150 batches). Deflation mutation-verified. Math pinned, not magic numbers (√(2 ln N) asymptotic, BH == scipy). ⬜ left: **random-entry null** (couples to the engine → its own slice). |
| **P11** | The strategies (~100 each) | ~400 | 🟡 **3 of 4 DONE** — `strategies/xs_momentum.py`: **XS Momentum 12-1** (top-6, quarterly, no stop; ranking hand-verified on 6 synthetic stocks; the **skip** mutation-verified; gate **PASSED** 300 vs 47 bps). `strategies/intraday.py`: **ORB** + **VWAP reversion** (StopEngine, session-aware reset mutation-verified; both **FAILED_PRIOR** — 0.35R prior vs 0.206R×2 required = the quantified NO). `strategies/__init__.py` registers all on import. ⬜ left: **XS PEAD** (needs an earnings-surprise input the price-only data layer lacks — **blocked on data**). ⚠️ **R3 still gates any momentum *number*.** |
| **P12** | The verdict report (plain English) | ~250 | It renders; **the owner can read it.** |

### ── GATE: does edge exist? ──

- **YES** → Phase 2 (below).
- **NO** → **stop.** That is a successful outcome: weeks spent instead of another year.
- **INSUFFICIENT EVIDENCE** → also a legitimate answer. **V1 and V2 both failed by refusing to say it.**

---

## The strategies (P11)

| Strategy | Prior | Friction gate |
|---|---|---|
| **XS Momentum 12-1** — rank by t−12mo→t−1mo return (skip last month = reversal), top 6 equal-weight, monthly/quarterly rebalance, `slots=6` | Most-replicated anomaly globally; documented in Indian equities | ~6 round trips/slot/yr → **2.2%/yr**. **Passes — but via the `required_edge_bps` arm only**: it has no per-trade stop (D9), so `required_avg_R_be` is undefined for it. Needs >**73.9 bps** (2× friction) per rebalance. |
| **XS PEAD** — long top-decile earnings surprise, hold 20d from t+1 | Robust global anomaly | Passes on friction; **at risk on data (R8)** — drop if earnings dates can't be verified |
| **Intraday ORB 15m** | Weak | **Fails prior. Run anyway.** |
| **Intraday VWAP reversion 15m** | Weak | **Fails prior. Run anyway.** |

**Run the intraday pair even though the gate rejects them**, marked `gate_status=FAILED_PRIOR`. The
owner asked for *"both — let the data decide"*. He gets a **quantified, documented NO** (arithmetic +
empirical + sensitivity curve), not an assertion. Doing the cheap check first *and* the expensive check
anyway respects both instructions.

✅ **RESOLVED 2026-07-15 — the owner chose both:** *"we can go with both"*, returning to his original
*"both, let the data decide"*. All four strategies above are in. What follows: **R3 (survivorship bias)
becomes the highest risk in Phase 1** — it bites XS momentum specifically, so **P4's point-in-time
universe is no longer optional** — and **the owner must confirm he understands a top-6 strategy is a
₹60,000 commitment, not ₹10,000** (D8). The reframing that made the intraday half a fair question
stands: **intraday is dead at 180 trades/yr, not at 20–30.**

---

## Phase 2 — build the system (only if Phase 1 says yes)

Not designed yet — deliberately. **Phase 2's shape depends on Phase 1's answer**, and designing it now
is exactly the mistake V1 and V2 made. Sketch only:

1. **Execution layer** — port V1's Dhan service (`dhan.service.ts`, 1,078 LOC): TOTP token auto-gen +
   `authed()` self-heal, the static-IP IPv6 proxy, `STOP_LOSS`-limit stop semantics, tick rounding, the
   tri-state SL poll/retry, the 15:12 broker-truth EOD sweep, `null`-vs-`[]` position reads.
   **🔴 Fix V1's worst bug first: `mode=off` must NOT disable exits.** In V1, `off` kills the exit path
   (`:477`), the EOD sweep (`:187`, `:209`) *and* boot reconcile (`:152`) — and the kill-switch
   **sets `mode='off'` itself** (`:715`), so it strands the loser exactly when you most want out.
   **v3 must separate "no new entries" from "no exits."** Add: order idempotency (`correlationId` —
   possibly a SEBI retail-algo requirement, never implemented in V1), a client-side token throttle, a
   persistent token cache, and an alert on token-gen failure.
2. **Capital allocator** — genuinely new work. V2's per-cell fund is a *research* model, not a
   portfolio model: no shared bankroll, no funding gate, **no cap on total concurrent exposure**.
3. **One config, two runtimes.** Every constant (risk %, leverage, cost rates) must live in one file
   both runtimes read — V1/V2 duplicated them Python↔TypeScript behind comments saying "MUST match",
   and one is already stale. **Make "MUST match" a build step, not a hope.**
4. **Then, and only then**, the UI. Port V2's *information design* (annualise ROI, grey out avgR below
   the confidence threshold), not its JSX.
5. Swing/equity later as a **separate web app on the same backend** — the owner's own idea, and it
   works because the funding unit (the slot) is shared. See ARCHITECTURE §2.

---

## Housekeeping (not blocking, but real)

- ✅ **Telegram token — DONE. The owner revoked it (2026-07-15).** The plaintext string still tracked at
  `smart-trading/docker-compose.prod.yml:30-31` is now worthless. Purging it from history is **optional
  tidiness, no longer a security item**, and still needs his consent because it rewrites shared history.
- ⚠️ **`DHAN_MAX_RISK` — confirmed absent from compose AND `.env`** ⇒ `dhan.service.ts:108` `?? 2000`
  applies ⇒ **₹2,000 is in force, 10× the documented ₹200.** Harmless while money is off; **must be set
  explicitly before re-enabling.** (Checked on the local checkout; work-pc is LIVE but a separate machine not reachable from here, so its
  env is unverified.)
- 🔴 **NEW — `RISK_PER_TRADE_PCT` units, defect N5: CONFIRMED, not theoretical.** `.env` says `2`
  (percent), `backtest_config.py:52` reads it as a fraction ⇒ **`2.0` ⇒ a 200% risk budget ⇒ V2's 2%
  cap never bound.** It wins the import race via `routers/backtest.py:6` → `db.client` →
  `load_dotenv()`, one line before `backtest_config` is imported. **Consequence for P6: `v2_compat` must
  set `RISK_PER_TRADE_PCT=2.0` or R0 cannot reconcile.** Same family as the `DHAN_MAX_RISK` item above:
  **three names, three unit conventions, no shared schema.**
- V1 real money is **OFF** and there are 0 open positions — ✅ verified **off by construction**
  (`DHAN_TRADING_MODE` absent everywhere ⇒ `|| 'off'`). Keep it that way until Phase 1 answers.
