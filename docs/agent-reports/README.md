# Agent Reports — the analyst loop

This folder holds **analysis reports written by an AI analyst agent**, not code and
not decisions. The agent's job is to learn from everything the system already
records — live trades, signals, backtest reports, regime tags, risk/heat — and
surface **what is not working as expected**, with the evidence to prove it.

The agent **proposes**. It never acts. It writes to this folder and nothing else.

## Why it works this way (read this before trusting any report)

A system that tunes its own rules on its own loss history doesn't self-improve — it
**overfits to noise**. Markets are noisy and our live sample is small. So the safety
mechanism is *you and Claude as the gate*: the agent only ever produces a reviewable
report; a human decides whether each finding is real before any code changes.

Three failure modes every report is designed to expose, not hide:

1. **Small samples.** A "pattern" from 6 trades is superstition. Every finding states
   its sample size; we reject anything thin.
2. **Confident confabulation.** An LLM will always produce a fluent reason for a loss,
   true or not. So every finding must cite **trade IDs / cells / numbers** — no claim
   without data behind it.
3. **Regime shift vs broken rule.** A strategy that stopped working may just be in the
   wrong regime. Findings must distinguish "rule is wrong" from "conditions changed."

## The loop

```
1. Analyst agent runs (on-demand)  → writes docs/agent-reports/<date>-<topic>.md
2. You + Claude review it          → fill the Verdict box on each finding
3. Accepted findings only          → Claude drafts a feature doc (/create-feature)
4. Normal phase-gate flow          → /review-docs → /execute-phase → /verify-feature
```

A finding becomes work **only** if (a) we both accept the verdict, **and** (b) its
suggested validation (walk-forward / Monte-Carlo on out-of-sample data) confirms it.
Nothing skips straight from "the agent thinks so" to a code change.

## What the agent may and may not do

| May | May not |
|-----|---------|
| Read the DB read-only, hit read-only API/engine endpoints | Write to the DB, place/close trades, mutate config |
| Run walk-forward / Monte-Carlo to *test* a hypothesis | Edit any application code |
| Cite trade IDs, cells, regimes, exact numbers | Make a claim without data behind it |
| Say "not enough data to conclude" | Manufacture a confident story to fill the report |

## Data the agent has

- **DB (read-only):** `smart_trading` on `localhost:5471` — `Trade`, `LiveSignal`,
  `BacktestReport`, `Stock`, `HistoricalData`, `ActiveConfiguration`.
- **Derived metrics (API :3001, computed not stored):** `/api/trades/stats`
  (per stock×strategy expectancy / avgRMultiple / profitFactor / maxDrawdown /
  confidence / reliable), `/api/trades/risk`, `/api/engine/regime`,
  `/api/engine/leaderboard`. These need the API key.
- **Validation (engine :8001):** `/run-walk-forward`, `/run-monte-carlo`.

## Files

- `TEMPLATE.md` — the required shape of every report. The agent must follow it.
- `<YYYY-MM-DD>-<topic>.md` — one dated report per run.
