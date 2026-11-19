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
from research_stats import DSR_THRESHOLD, bh_adjusted, deflated_sharpe_ratio, psr_pvalue, sharpe_ratio  # noqa: E402
from research_trials import Trial, TrialsLedger  # noqa: E402
from strategies import STRATEGY_REGISTRY, STRATEGY_TIMEFRAMES, STRATEGY_HOLD_DURATIONS  # noqa: E402

FIELDS = [
    "symbol", "strategy", "timeframe", "bucket", "bars", "span_years", "trades", "win_pct",
    "net", "avg_r", "pf", "max_dd_pct", "r_first_half", "r_second_half",
    "skipped_limits", "skipped_unsizable", "skipped_costly", "cannot_evaluate", "price_jump", "error",
]


def load(conn, stock_id: int, timeframe: str) -> pd.DataFrame:
    rows = conn.execute(text(
        'SELECT timestamp, open, high, low, close, volume FROM "HistoricalData" '
        'WHERE "stockId" = :sid AND timeframe = :tf ORDER BY timestamp'
    ), {"sid": stock_id, "tf": timeframe}).fetchall()
    df = pd.DataFrame(rows, columns=["timestamp", "Open", "High", "Low", "Close", "Volume"])
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df.set_index("timestamp")


FDR_Q = 0.10  # share of "discoveries" we accept being false

STRATEGY_FIELDS = ["strategy", "bucket", "cells", "trades", "avg_r", "sharpe_per_trade",
                   "p_value", "q_value", "deflated_sharpe", "stands_out"]


def strategy_table(r_by_strategy: dict[str, list[float]], prior_sharpes: list[float]) -> list[dict]:
    """One row per strategy: is its result more than luck, given how many were tried?

    Each strategy's trades (pooled over its stocks, in R) are one hypothesis. `p_value` is
    the chance of a result this good if the strategy had no edge. `q_value` corrects that for
    testing all the strategies at once (Benjamini-Hochberg). `deflated_sharpe` asks the same
    question against the best result luck alone would give across every trial on record
    (`prior_sharpes` plus this run). `stands_out` needs all three: a positive average, q at
    or below 10%, and a deflated Sharpe above 0.95.
    """
    rows, measured = [], []
    for name, rs in r_by_strategy.items():
        row = {"strategy": name, "trades": len(rs), "avg_r": round(float(np.mean(rs)), 3) if rs else None,
               "sharpe_per_trade": None, "p_value": None, "q_value": None, "deflated_sharpe": None,
               "stands_out": False}
        try:
            # Identical trades have no spread to judge against; rounding can leave a
            # spread of 1e-17 that would otherwise read as an infinitely good result.
            if len(rs) < 2 or float(np.std(rs, ddof=1)) < 1e-9:
                raise ValueError("nothing to test")
            row["sharpe_per_trade"] = sharpe_ratio(rs)
            row["p_value"] = psr_pvalue(rs)
            measured.append(row)
        except ValueError:
            pass  # fewer than 2 trades, or every trade identical: nothing to test
        rows.append(row)
    if measured:
        for row, q in zip(measured, bh_adjusted([r["p_value"] for r in measured])):
            row["q_value"] = float(q)
        trial_sharpes = list(prior_sharpes) + [r["sharpe_per_trade"] for r in measured]
        for row in measured:
            try:
                row["deflated_sharpe"] = deflated_sharpe_ratio(r_by_strategy[row["strategy"]], trial_sharpes)
            except ValueError:
                row["deflated_sharpe"] = None
            row["stands_out"] = bool(
                (row["avg_r"] or 0) > 0 and row["q_value"] is not None and row["q_value"] <= FDR_Q
                and row["deflated_sharpe"] is not None and row["deflated_sharpe"] > DSR_THRESHOLD
            )
    for row in rows:
        for k in ("sharpe_per_trade", "p_value", "q_value", "deflated_sharpe"):
            if row[k] is not None:
                row[k] = round(row[k], 4)
    return sorted(rows, key=lambda r: (r["avg_r"] is None, -(r["avg_r"] or 0)))


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
