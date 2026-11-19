"""Walk-forward folds give the strategy warm-up data (audit F8).

Run from apps/engine:  python -m pytest test/test_walkforward.py -q
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategies.base import BaseStrategy  # noqa: E402
from walkforward import fold_bounds, run_folds, summarise  # noqa: E402


def test_fold_bounds_cover_the_series_and_reach_back_for_warmup():
    bounds = fold_bounds(1000, 4, warmup=300)
    assert [(ts, te) for _, ts, te in bounds] == [(0, 250), (250, 500), (500, 750), (750, 1000)]
    assert [fs for fs, _, _ in bounds] == [0, 0, 200, 450]      # never before bar 0


class _NeedsHistory(BaseStrategy):
    """Buys every 10th bar, but only once it has seen 200 bars — like a 200-day SMA."""

    name = "NEEDS_HISTORY_TEST"
    timeframe = "1D"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        seen = np.arange(len(df))
        df["signal"] = np.where((seen >= 200) & (seen % 10 == 0), 1, 0)
        df["stop_loss"] = df["Close"] * 0.97
        df["target"] = df["Close"] * 1.06
        return df


def _frame(n=1000):
    rng = np.random.default_rng(0)
    close = 100 + np.cumsum(rng.standard_normal(n) * 0.8)
    idx = pd.date_range("2022-01-03", periods=n, freq="D")
    return pd.DataFrame({"Open": close, "High": close + 1, "Low": close - 1,
                         "Close": close, "Volume": 1000}, index=idx)


def test_later_folds_trade_because_they_are_warmed_up():
    df = _frame()
    warmed = run_folds(_NeedsHistory(), df, folds=4, warmup=300)
    starved = run_folds(_NeedsHistory(), df, folds=4, warmup=0)
    # Fold 1 has no earlier data either way. Folds 2-4 are 250 bars each: starved,
    # the strategy only wakes up for the last 50 bars of each; warmed, for all 250.
    for w, s in zip(warmed[1:], starved[1:]):
        assert w["trades"] > s["trades"]
    assert summarise(warmed)["foldsWithTrades"] >= 3


def test_no_trade_starts_inside_the_warmup_bars():
    df = _frame()
    strat = _NeedsHistory()
    whole = strat.simulate(df)
    late_only = strat.simulate(df, trade_from=900)
    assert 0 < len(late_only["net_trades"]) < len(whole["net_trades"])
    assert len(strat.simulate(df, trade_from=len(df))["net_trades"]) == 0


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
