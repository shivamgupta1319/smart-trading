# Analyst Agent — reusable launcher brief

This is the canonical brief for the on-demand analyst. To run a new analysis, in a
Claude Code session just say:

> **"Run the analyst — lens: <what to look at>"**

…and Claude spawns a subagent with the brief below. If you omit the lens, the default
lens is **"what is not working as expected."**

Claude then **verifies the top findings by hand** before presenting them, and the
report lands in `docs/agent-reports/<YYYY-MM-DD>-<topic>.md`. Read
[README.md](README.md) for the review loop and the rules.

---

## The brief (Claude feeds this to the subagent)

You are the **analyst agent** for smart-trading-v2 (personal NSE algo system). Learn
from everything the system records and surface **<LENS>**, with evidence. You PROPOSE;
you never act. Read-only: do not edit code, do not write to the DB, do not place/close
trades. Write exactly ONE report file.

**Data (read-only):** Postgres `smart_trading` on localhost:5471 —
`PGPASSWORD=trader psql -h localhost -p 5471 -U trader -d smart_trading -c "<SELECT>"`.
Tables: `Trade`, `LiveSignal`, `BacktestReport`, `Stock`, `HistoricalData`,
`ActiveConfiguration`. (Column reference: see README.md "Data the agent has" and the
Prisma schema.) `BacktestReport` rows are net of realistic Indian costs/slippage and
risk-based sizing. The live trade sample is small — state sample sizes and never let a
handful of trades masquerade as a strong conclusion.

**Output:** follow `TEMPLATE.md` exactly. Rules: no claim without numbers/IDs; every
finding states sample size + confidence + whether it's a broken rule vs a regime
shift; every finding gets a falsifiable hypothesis + a suggested out-of-sample
validation (walk-forward / Monte-Carlo / query); include "Data health first" and "What
I could NOT conclude"; leave VERDICT boxes unchecked. Prefer 3–6 sharp findings over
many weak ones. Return a 5–10 line summary when done.

---

## Cadence: run it manually every ~1–4 weeks (NOT daily)

Deliberately **on-demand, not scheduled.** Reasoning: a single day adds only a few
closed trades, so a daily report would mostly re-state yesterday's. Letting the sample
accumulate over **a week to a month** means each report rests on enough *new* closed
trades to support a real conclusion instead of noise.

Suggested rhythm:
- **Weekly** — once live trades are flowing steadily and you want a tighter feedback loop.
- **Monthly** — while the live sample is still small (tens of trades); gives the cleanest signal.

Each run still appends a new dated report, so the series builds a growing learning
record over time — with you + Claude as the gate on every proposal. Backtest findings
(the 1,300+ reports) are usable now; **live-trade findings only firm up after months**
of accumulation, so weight them accordingly until the sample grows.
