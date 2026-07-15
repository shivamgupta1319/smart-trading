# Analyst Report — <topic>

- **Date:** <YYYY-MM-DD>
- **Lens:** <what this report looked for, e.g. "what's not working as expected">
- **Data window:** <date range of trades/backtests analysed>
- **Sample:** <N closed trades, N signals, N backtest reports examined>

## TL;DR (≤5 bullets)

- <the headline findings, each one line, no jargon>

## Data health first

> Before any finding: is there even enough data to conclude anything? Be blunt.

- Closed live trades: <N> (<enough / too thin to trust>)
- Backtest reports: <N>
- Known caveats this run inherits (sample size, regime coverage, data gaps): <...>

---

## Findings

> One block per finding. No claim without numbers. If you can't cite it, cut it.

### F1 — <short title>

- **Observation:** <what the data shows — concrete numbers>
- **Evidence:** <trade IDs / (stock×strategy) cells / regime / exact metrics>
- **Sample size:** <N> — **confidence:** <low / medium / high, and why>
- **Is it a broken rule or a regime shift?** <which, and how you can tell>
- **Hypothesis:** <the testable improvement, stated so it can be falsified>
- **Suggested validation:** <which walk-forward / Monte-Carlo / query would confirm
  it on out-of-sample data before we touch code>

> **VERDICT (filled by human review):** ☐ Accept ☐ Reject ☐ Needs more data
> — _notes:_

### F2 — <short title>
... (same shape)

---

## What I could NOT conclude

> Honesty section. List things that looked interesting but the data was too thin,
> or where live and backtest disagree and you can't yet say which is right.

- <...>

## Suggested next report

- <the most valuable follow-up analysis, given what this run found>
