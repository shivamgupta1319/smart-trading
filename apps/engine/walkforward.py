"""Walk-forward folds with indicator warm-up — one implementation for both callers.

The history is cut into `folds` consecutive test windows. Each window used to be
handed to the strategy on its own, so a 200-day moving average had no data at the
start of every fold and long-lookback strategies simply could not trade there:
their out-of-sample result was really an "insufficient data" result. There were
also two copies of the loop (the validate endpoint and auto-select).

Now each fold's frame starts WARMUP_BARS earlier. Those bars feed the indicators
but no trade may start in them (`simulate(trade_from=...)`); a trade that starts
inside the test window may run past its end, to the end of the data.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from backtest_config import _i

# Enough for the hungriest strategy (250-bar guards) plus indicator settling.
WARMUP_BARS = _i("WF_WARMUP_BARS", 300)
MIN_TEST_BARS = 30


def fold_bounds(n: int, folds: int, warmup: int = WARMUP_BARS) -> list[tuple[int, int, int]]:
    """[(frame_start, test_start, test_end)] bar positions for each fold."""
    folds = max(2, min(folds, 12))
    size = n // folds
    out = []
    for k in range(folds):
        test_start = k * size
        test_end = n if k == folds - 1 else (k + 1) * size
        if test_end - test_start < MIN_TEST_BARS:
            continue
        out.append((max(0, test_start - warmup), test_start, test_end))
    return out


def run_folds(strategy, df: pd.DataFrame, folds: int, warmup: int = WARMUP_BARS) -> list[dict]:
    """Backtest each fold with warm-up. A fold whose strategy raises is skipped."""
    results = []
    for k, (frame_start, test_start, test_end) in enumerate(fold_bounds(len(df), folds, warmup), 1):
        frame = df.iloc[frame_start:test_end]
        try:
            m = strategy.run_backtest(frame, trade_from=test_start - frame_start)
        except Exception:
            continue
        results.append({
            "fold": k,
            "bars": test_end - test_start,
            "warmupBars": test_start - frame_start,
            "trades": m["totalTrades"],
            "roiPercentage": m["roiPercentage"],
            "winRate": m["winRate"],
            "profitFactor": m["profitFactor"],
        })
    return results


def summarise(fold_results: list[dict]) -> dict:
    traded = [f for f in fold_results if f["trades"] > 0]
    rois = [f["roiPercentage"] for f in traded]
    profitable = [r for r in rois if r > 0]
    mean = float(np.mean(rois)) if rois else 0.0
    std = float(np.std(rois)) if rois else 0.0
    return {
        "foldsEvaluated": len(fold_results),
        "foldsWithTrades": len(traded),
        "pctProfitableFolds": round(len(profitable) / len(traded) * 100, 2) if traded else 0.0,
        "meanOosRoi": round(mean, 2),
        "stdOosRoi": round(std, 2),
        # Consistency: low std relative to mean is good; flag erratic strategies.
        "consistent": bool(rois and mean > 0 and std <= abs(mean)),
    }
