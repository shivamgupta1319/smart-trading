"""Is any strategy's backtest more than luck?

Backtesting 28 strategies at once guarantees that some look good by chance. This module
runs every registered strategy on every active stock, pools each strategy's trades (in R)
and asks two questions of each one (`research_stats.py`):

  * q_value: the chance of a result this good with no edge, corrected for testing all the
    strategies at once (Benjamini-Hochberg);
  * deflated_sharpe: whether it beats the best result luck alone would give across every
    trial on record.

A strategy "stands out" only when its average is positive, q is at or below 10% and the
deflated Sharpe is above 0.95.

Trials on record. The count of tries cannot be typed in: it is the seed file
(`config/research_trials_seed.jsonl`, a copy of the research ledger) plus every stored run.
A trial is a strategy on one engine version, so the daily refresh of the same strategy on
the same engine replaces its entry instead of adding a try; a new strategy or a new engine
version adds one.

`tools/backtest_all.py` uses `strategy_table` for its report. `run_and_store` is what the
scheduler and the API call; the result is kept in the `LuckCheckRun` table.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

from backtest_config import ENGINE_VERSION
from data_checks import back_adjust
from db.client import engine
from research_stats import DSR_THRESHOLD, bh_adjusted, deflated_sharpe_ratio, psr_pvalue, sharpe_ratio
from research_trials import TrialsLedger
from strategies import STRATEGY_HOLD_DURATIONS, STRATEGY_REGISTRY, STRATEGY_TIMEFRAMES

FDR_Q = 0.10  # share of "discoveries" we accept being false
_HERE = Path(__file__).resolve().parent
_running = threading.Lock()


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


def load_candles(conn, stock_id: int, timeframe: str) -> pd.DataFrame:
    rows = conn.execute(text(
        'SELECT timestamp, open, high, low, close, volume FROM "HistoricalData" '
        'WHERE "stockId" = :sid AND timeframe = :tf ORDER BY timestamp'
    ), {"sid": stock_id, "tf": timeframe}).fetchall()
    df = pd.DataFrame(rows, columns=["timestamp", "Open", "High", "Low", "Close", "Volume"])
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df.set_index("timestamp")


def _seed_path() -> Path:
    inside_image = _HERE / "config" / "research_trials_seed.jsonl"
    if inside_image.is_file() or len(_HERE.parents) < 2:
        return inside_image
    return _HERE.parents[1] / "config" / "research_trials_seed.jsonl"


def prior_trials(conn, seed_path: Path | None = None) -> dict[tuple[str, str], float]:
    """Sharpe of every trial on record, keyed by (strategy, variant). A later record of the
    same key replaces the earlier one: same strategy, same engine, same hypothesis."""
    trials: dict[tuple[str, str], float] = {}
    for t in TrialsLedger(seed_path or _seed_path()).read():
        trials[(t.strategy, t.variant)] = t.sharpe
    stored = conn.execute(text('SELECT "engineVersion", rows FROM "LuckCheckRun" ORDER BY id')).fetchall()
    for version, rows in stored:
        for row in rows if isinstance(rows, list) else json.loads(rows):
            if row.get("sharpe_per_trade") is not None:
                trials[(row["strategy"], f"engine={version}")] = row["sharpe_per_trade"]
    return trials


def collect_r(conn) -> tuple[dict[str, list[float]], dict[str, int], int]:
    """Every strategy on every active stock: (R of each trade by strategy, cells by strategy,
    number of stocks). A cell that fails is skipped; one bad cell must not stop the run."""
    import universe  # here, not at the top: universe imports nothing from this module

    stocks = universe.active_stocks(conn)
    r_by_strategy: dict[str, list[float]] = {}
    cells: dict[str, int] = {}
    for stock_id, symbol, on_intraday_list in stocks:
        # Daily candles for every stock; intraday candles only for the intraday list.
        wanted = universe.timeframes_for(on_intraday_list, sorted(set(STRATEGY_TIMEFRAMES.values())))
        frames = {tf: back_adjust(load_candles(conn, stock_id, tf), symbol) for tf in wanted}
        for name, strategy in STRATEGY_REGISTRY.items():
            df = frames.get(STRATEGY_TIMEFRAMES.get(name, "1D"), pd.DataFrame())
            if df.empty:
                continue
            try:
                r_by_strategy.setdefault(name, []).extend(strategy.simulate(df.copy())["r_trades"])
                cells[name] = cells.get(name, 0) + 1
            except Exception as exc:
                print(f"  [luck check] {symbol} {name}: {type(exc).__name__}: {exc}"[:200])
    return r_by_strategy, cells, len(stocks)


def build_run(r_by_strategy, cells, prior: dict[tuple[str, str], float]) -> tuple[list[dict], int]:
    """(rows, trials on record) for one run. Pure: no database, no clock."""
    variant = f"engine={ENGINE_VERSION}"
    earlier = [s for (name, v), s in prior.items() if not (v == variant and name in r_by_strategy)]
    rows = strategy_table(r_by_strategy, earlier)
    for row in rows:
        row["bucket"] = STRATEGY_HOLD_DURATIONS.get(row["strategy"])
        row["cells"] = cells.get(row["strategy"], 0)
    trials = len(earlier) + sum(1 for r in rows if r["sharpe_per_trade"] is not None)
    return rows, trials


def run_and_store() -> dict | None:
    """Compute the luck check on stored candles and save it. Returns the saved run, or None
    when another run is already in progress. About a minute for 60 stocks."""
    if not _running.acquire(blocking=False):
        return None
    try:
        with engine.connect() as conn:
            r_by_strategy, cells, n_stocks = collect_r(conn)
            rows, trials = build_run(r_by_strategy, cells, prior_trials(conn))
        with engine.begin() as conn:
            conn.execute(text(
                'INSERT INTO "LuckCheckRun" ("engineVersion", stocks, trials, rows) '
                'VALUES (:v, :s, :t, CAST(:r AS jsonb))'
            ), {"v": ENGINE_VERSION, "s": n_stocks, "t": trials, "r": json.dumps(rows)})
        return latest()
    finally:
        _running.release()


def latest() -> dict | None:
    """The most recent stored run, or None when there is none yet."""
    with engine.connect() as conn:
        row = conn.execute(text(
            'SELECT "computedAt", "engineVersion", stocks, trials, rows FROM "LuckCheckRun" ORDER BY id DESC LIMIT 1'
        )).fetchone()
    if row is None:
        return None
    rows = row[4] if isinstance(row[4], list) else json.loads(row[4])
    return {
        "computedAt": row[0].isoformat() + "Z",
        "engineVersion": row[1],
        "stocks": row[2],
        "trials": row[3],
        "strategies": len(rows),
        "fdrQ": FDR_Q,
        "dsrThreshold": DSR_THRESHOLD,
        "standOut": [r["strategy"] for r in rows if r["stands_out"]],
        "rows": rows,
    }
