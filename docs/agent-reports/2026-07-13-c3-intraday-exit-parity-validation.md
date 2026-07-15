# C3 — Intraday Exit Parity: deploy + real-data validation (2026-07-13)

**Change:** the backtest now models the live intraday 3-phase exit (35%/35% partials at
50%/75% progress, breakeven + prev-candle trail, reversal at 80%, hard 15:15 square-off)
instead of fixed SL/TP with positions spanning the whole 60-day 15m series. Commit `afd6b4e`
on `roadmap-v2`; shared primitives in `apps/engine/intraday_exits.py` (imported by both the
live scanner and the backtest). Deployed to work-pc this session (engine + api + scanner +
scheduler recreated; scanner verified healthy).

## Before → after (full-history 15m backtest, deployed engine)

| Cell (live P&L / avgR) | metric | BEFORE (fixed SL/TP, multi-day) | AFTER (C3, live exits) |
|---|---|---|---|
| **IFCI · VWAP_MACD_RSI** (live +₹1,474 / R2.40, 7 tr) | net / avgR / DD / trades | +₹17,126 / 0.155 / 32% / 21 | **−₹2,661 / −0.022 / 40% / 35** |
| **BSE · RVOL_ORB** (live +₹1,227 / R6.00, 5 tr) | | +₹9,354 / 0.205 / 39% / 28 | **−₹5,640 / −0.079 / 65% / 80** |
| **OLAELEC · VWAP_MACD_RSI** (live +₹392 / R4.35, 6 tr) | | +₹14,831 / 0.068 / 49% / 25 | **+₹10,159 / 0.177 / 16% / 31** |
| **ATGL · RVOL_ORB** (live +₹1,093 / R0.91, 5 tr) | | +₹8,856 / 0.665 / 57% / 13 | **−₹3,723 / −0.052 / 72% / 63** |
| GROWW · EMA_RSI (live +₹110, 23 tr) | | −₹4,156 / −0.147 / 59% / 17 | −₹2,962 / −0.162 / 36% / 68 |
| MTARTECH · 15m_ORB (live −₹670, loser) | | +₹14,578 / 0.279 / 55% / 53 | +₹3,117 / 0.081 / 54% / 69 |

Trade counts **2–3×** — same-day square-off frees the slot every day, so the strategy
re-enters far more often instead of one position riding for days.

## Faithfulness check (wrapping the REAL `_intraday_exit`)

| Cell | same-day exits | square-off exits | win % | hold bars (min/med/max) |
|---|---|---|---|---|
| IFCI·VWAP_MACD_RSI | **100%** | 57% | 43% | 0 / 14 / 23 |
| BSE·RVOL_ORB | **100%** | 79% | 40% | 0 / 16 / 24 |
| OLAELEC·VWAP_MACD_RSI | **100%** | 45% | 61% | 0 / 9 / 23 |

- **Square-off invariant holds exactly** (100% same-day; no multi-day leak). ~one session is
  25 × 15m bars, and max holds sit at 23–24.
- Exit mix is sane (mostly 15:15 square-offs + a tail of stops/targets/reversals) — the model
  is not dominated by any single mechanic, i.e. it is faithful, not systematically harsh.

## Read-only auto-select dry-run under the new numbers

31 strategies evaluated → **6 picks** (nothing written). Gates: avgR ≥ 0.05, PF ≥ 1.3, DD ≤ 25%,
return/DD ≥ 1.5, ≥60% profitable walk-forward folds, MC prob-profit ≥ 55%, ranked by net avgR.
**Intraday cells now clear gates** — e.g. `OLAELEC · 15m_ORB` (avgR 0.077, PF 1.45, DD 22%,
return/DD 3.95, 100% OOS folds, MC 89.8%). **Before C3 intraday passed 0 gates.**

## The finding (honest read)

C3 did what it was for: the backtest is now live-faithful for intraday, so auto-select can
**rank intraday strategies fairly** — the durable ones (OLAELEC-type, higher win rate) pass;
the rest fail. The twist: several **"proven live intraday winners" don't survive full-history
faithful modeling** (IFCI/BSE/ATGL VWAP/RVOL flip negative). Their edge over 5–7 live trades
was a favorable ~1-week window; over 60 days the same rules lose because the live partial-exit
system caps winners (35/35/30 + breakeven runner) while losers still take ~−1R — so a cell
needs a solid win rate (≈>50%), which these 40–43%-win cells don't have.

**Implication:** do **not** chase the intraday "live winners" as if they were validated edges.
Auto-select's intraday picks are now trustworthy (for the right reasons); treat OLAELEC-class
cells (high win rate, low DD, positive avgR) as the real intraday candidates.

## Not done (deliberately — needs a human decision)

- **A real (mutating) auto-select** was NOT run. It would append the 6 vetted picks (append-only,
  denylist-honored). Given the finding reshapes which intraday cells are "good," this is the
  user's call. `POST /api/engine/auto-select` (dryRun false) when ready.
- No historical DP-charge backfill of the ~11 old delivery sells (≈₹160), per the DP-charge note.
