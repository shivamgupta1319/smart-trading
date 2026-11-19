"""Re-run every strategy on every active stock and write one CSV row per cell.

READ-ONLY: it only SELECTs stored candles. It does not fetch data, and it does not
write BacktestReport rows — the result is a file you can study before deciding
anything. Run from apps/engine (or inside the engine container):

    python tools/backtest_all.py --out /tmp/backtest_all.csv

What the columns are for
  trades, win_pct, net, avg_r, pf, max_dd_pct   the usual metrics, NET of costs
  r_first_half / r_second_half                  average R of the first and second half
                                                of the cell's trades. A cell that is
                                                positive in only one half is not stable.
  skipped_limits / skipped_unsizable            signals dropped by the daily cap/cooldown
                                                or because one share broke the risk cap
  cannot_evaluate                               the strategy returned no signal column
Besides the per-cell file it writes <out>.strategies.csv: one row per strategy with a
luck correction (see `strategy_table`), and appends every strategy tested to a trials ledger.

  price_jump                                    daily moves above 20% that nobody has
                                                reviewed (config/known_price_actions.json)
                                                — treat that stock's rows with care
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest_config import ENGINE_VERSION  # noqa: E402
from data_checks import back_adjust, unexplained_jumps  # noqa: E402
from db.client import engine  # noqa: E402
from luck_check import load_candles as load, strategy_table  # noqa: E402,F401  (strategy_table is imported from here by tests)
from research_trials import Trial, TrialsLedger  # noqa: E402
from strategies import STRATEGY_REGISTRY, STRATEGY_TIMEFRAMES, STRATEGY_HOLD_DURATIONS  # noqa: E402

FIELDS = [
    "symbol", "strategy", "timeframe", "bucket", "bars", "span_years", "trades", "win_pct",
    "net", "avg_r", "pf", "max_dd_pct", "r_first_half", "r_second_half",
    "skipped_limits", "skipped_window", "skipped_unsizable", "skipped_costly", "cannot_evaluate", "price_jump", "error",
]


STRATEGY_FIELDS = ["strategy", "bucket", "cells", "trades", "avg_r", "sharpe_per_trade",
                   "p_value", "q_value", "deflated_sharpe", "stands_out"]


def _mean(xs) -> float | None:
    return float(np.mean(xs)) if len(xs) else None


def run_cell(strategy, df: pd.DataFrame) -> tuple[dict, list[float]]:
    sim = strategy.simulate(df)
    net, r = sim["net_trades"], sim["r_trades"]
    wins = [x for x in net if x > 0]
    losses = [-x for x in net if x < 0]
    half = len(r) // 2
    span_days = (df.index[-1] - df.index[0]).days if len(df) > 1 else 0
    return {
        "bars": len(df),
        "span_years": round(span_days / 365.25, 2),
        "trades": len(net),
        "win_pct": round(100 * len(wins) / len(net), 1) if net else None,
        "net": round(sum(net), 0),
        "avg_r": round(_mean(r), 3) if r else None,
        "pf": round(sum(wins) / sum(losses), 2) if losses and wins else None,
        "max_dd_pct": round(100 * sim["max_dd_pct"], 1),
        "r_first_half": round(_mean(r[:half]), 3) if half else None,
        "r_second_half": round(_mean(r[half:]), 3) if half else None,
        "skipped_limits": sim.get("skipped_limits", 0),
        "skipped_window": sim.get("skipped_window", 0),
        "skipped_unsizable": sim.get("skipped_unsizable", 0),
        "skipped_costly": sim.get("skipped_costly", 0),
        "cannot_evaluate": sim.get("no_signal_column", False),
    }, list(r)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--strategies", default="", help="comma-separated subset (default: all)")
    ap.add_argument("--symbols", default="", help="comma-separated subset (default: all active)")
    ap.add_argument("--ledger", default="", help="trials ledger file (default: trials-ledger.jsonl next to --out)")
    args = ap.parse_args()

    only_s = {x for x in args.strategies.split(",") if x}
    only_y = {x.upper() for x in args.symbols.split(",") if x}
    started = time.monotonic()

    with engine.connect() as conn:
        stocks = conn.execute(text('SELECT id, symbol FROM "Stock" WHERE "isActive" ORDER BY symbol')).fetchall()
        stocks = [s for s in stocks if not only_y or s[1].upper() in only_y]
        rows = []
        r_by_strategy: dict[str, list[float]] = {}
        cells_by_strategy: dict[str, int] = {}
        for n, (stock_id, symbol) in enumerate(stocks, 1):
            frames: dict[str, pd.DataFrame] = {}
            for tf in sorted(set(STRATEGY_TIMEFRAMES.values())):
                frames[tf] = load(conn, stock_id, tf)
            # Only moves nobody has reviewed are flagged; reviewed demergers are scaled out.
            daily = frames.get("1D", pd.DataFrame())
            jumps = [str(j) for j in unexplained_jumps(symbol, daily["Close"])] if not daily.empty else []
            frames = {tf: back_adjust(f, symbol) for tf, f in frames.items()}
            for name, strategy in STRATEGY_REGISTRY.items():
                if only_s and name not in only_s:
                    continue
                tf = STRATEGY_TIMEFRAMES.get(name, "1D")
                row = {"symbol": symbol, "strategy": name, "timeframe": tf,
                       "bucket": STRATEGY_HOLD_DURATIONS.get(name), "price_jump": ";".join(jumps), "error": ""}
                df = frames.get(tf, pd.DataFrame())
                try:
                    if df.empty:
                        row["error"] = "no stored candles"
                    else:
                        cell, r_list = run_cell(strategy, df.copy())
                        row.update(cell)
                        r_by_strategy.setdefault(name, []).extend(r_list)
                        cells_by_strategy[name] = cells_by_strategy.get(name, 0) + 1
                except Exception as exc:  # one broken cell must not stop the run
                    row["error"] = f"{type(exc).__name__}: {exc}"[:160]
                rows.append(row)
            print(f"[{n}/{len(stocks)}] {symbol} done ({time.monotonic() - started:.0f}s)", flush=True)

    with open(args.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    errors = sum(1 for r in rows if r["error"])
    print(f"engine {ENGINE_VERSION}: {len(rows)} cells, {errors} with errors → {args.out}")

    # Luck correction, one row per strategy. Every strategy tested is recorded in the trials
    # ledger first, so the number of tries can only grow: it is counted, not typed in.
    base = args.out[:-4] if args.out.endswith(".csv") else args.out
    ledger = TrialsLedger(args.ledger or os.path.join(os.path.dirname(os.path.abspath(args.out)), "trials-ledger.jsonl"))
    prior = ledger.sharpes()
    table = strategy_table(r_by_strategy, prior)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    variant = f"engine={ENGINE_VERSION}"
    for row in table:
        row["bucket"] = STRATEGY_HOLD_DURATIONS.get(row["strategy"])
        row["cells"] = cells_by_strategy.get(row["strategy"], 0)
        if row["sharpe_per_trade"] is not None:
            ledger.record(Trial(strategy=row["strategy"], variant=variant, instrument_set=f"{len(stocks)} stocks",
                                sharpe=row["sharpe_per_trade"], n_obs=row["trades"], timestamp=stamp))
    with open(base + ".strategies.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=STRATEGY_FIELDS)
        w.writeheader()
        w.writerows(table)
    winners = [r["strategy"] for r in table if r["stands_out"]]
    print(f"{len(table)} strategies tested ({ledger.n_trials()} trials on record). "
          f"Stand out beyond luck: {', '.join(winners) if winners else 'none'} → {base}.strategies.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
