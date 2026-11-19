# July 2026 rebuild: what was kept and what is only stored here

In July 2026 a third version of this product was started from scratch in a separate
folder (`stock-trading`). It was never run on real market data. In November 2026 its
useful parts were built into Smart Trading and the folder was retired.

Nothing in this folder is used by the product. It is here so the ideas are not lost.

## Built into the product

| Piece | Where it lives now |
|---|---|
| Candle data checks and the price-jump review list | `apps/engine/data_checks.py`, `config/known_price_actions.json` |
| Luck-correction statistics and the trials ledger | `apps/engine/research_stats.py`, `apps/engine/research_trials.py` |
| Slippage of at least one tick | `apps/engine/backtest_config.py`, `apps/api/src/common/costs.ts` |
| NIFTY buy-and-hold comparison | Portfolio page, `GET /api/engine/benchmark` |
| Gap-through-stop fills at the open | `apps/engine/strategies/base.py` |
| Walk-forward warm-up | `apps/engine/walkforward.py` |
| One shared settings file | `config/trading.json` |

## Stored here only, not used

| File | What it is | Why it was left out |
|---|---|---|
| `code/rebalance_engine.py`, `code/ledger.py` | An engine that holds a basket of stocks and rebalances it on a schedule | The product trades one stock per cell with a stop and a target. A basket needs a different engine. |
| `code/xs_momentum.py` | A strategy that buys the strongest stocks of the last months and rebalances | Never run on real data. To be discussed as a new strategy idea. |
| `code/universe.py`, `config/universe/nifty200.yaml` | A stock list that knows which stocks were in NIFTY 200 on each past date | The data file was never filled in, so it cannot be used yet. |
| `tests/` | The tests for the four files above | Kept with the code they test. |
| `config/research.yaml` | The rebuild's research settings | Reference for the momentum basket. |
| `docs/DECISIONS.md` | Every decision taken in the rebuild, with the reason | History. |
| `docs/REVIEW-V1-V2.md` | The review of the first two apps and the defects found | History. The defects that mattered are fixed in the product. |
| `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `docs/GLOSSARY.md` | How the rebuild was designed | History. They describe the rebuild, not this product. |

The verdicts in these documents ("passed", "failed") came from arithmetic on costs,
not from a backtest on real prices. Do not read them as results.

The code here imports from a package called `trading` that no longer exists, so it
does not run as it is. Bringing the momentum basket back means porting it, not
switching it on.
