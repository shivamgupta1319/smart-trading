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
  price_jump                                    the stock has an unexplained >20% daily
                                                move in stored history (possible split /
                                                demerger cliff) — treat its rows with care
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import sys
import time

import numpy as np
import pandas as pd
from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest_config import ENGINE_VERSION  # noqa: E402
from db.client import engine  # noqa: E402
from strategies import STRATEGY_REGISTRY, STRATEGY_TIMEFRAMES, STRATEGY_HOLD_DURATIONS  # noqa: E402

JUMP_LOG_RETURN = 0.20  # |ln(close/prev close)| above this on a daily bar is flagged

FIELDS = [
    "symbol", "strategy", "timeframe", "bucket", "bars", "span_years", "trades", "win_pct",
    "net", "avg_r", "pf", "max_dd_pct", "r_first_half", "r_second_half",
    "skipped_limits", "skipped_unsizable", "cannot_evaluate", "price_jump", "error",
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


def price_jumps(daily: pd.DataFrame) -> list[str]:
    """Dates of daily closes that moved more than JUMP_LOG_RETURN from the prior close."""
    if daily.empty:
        return []
    lr = np.log(daily["Close"] / daily["Close"].shift(1)).abs()
    return [d.strftime("%Y-%m-%d") for d in lr[lr > JUMP_LOG_RETURN].index]


def _mean(xs) -> float | None:
    return float(np.mean(xs)) if len(xs) else None


def run_cell(strategy, df: pd.DataFrame) -> dict:
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
        "cannot_evaluate": sim.get("no_signal_column", False),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--strategies", default="", help="comma-separated subset (default: all)")
    ap.add_argument("--symbols", default="", help="comma-separated subset (default: all active)")
    args = ap.parse_args()

    only_s = {x for x in args.strategies.split(",") if x}
    only_y = {x.upper() for x in args.symbols.split(",") if x}
    started = time.monotonic()

    with engine.connect() as conn:
        stocks = conn.execute(text('SELECT id, symbol FROM "Stock" WHERE "isActive" ORDER BY symbol')).fetchall()
        stocks = [s for s in stocks if not only_y or s[1].upper() in only_y]
        rows = []
        for n, (stock_id, symbol) in enumerate(stocks, 1):
            frames: dict[str, pd.DataFrame] = {}
            for tf in sorted(set(STRATEGY_TIMEFRAMES.values())):
                frames[tf] = load(conn, stock_id, tf)
            jumps = price_jumps(frames.get("1D", pd.DataFrame()))
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
                        row.update(run_cell(strategy, df.copy()))
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
