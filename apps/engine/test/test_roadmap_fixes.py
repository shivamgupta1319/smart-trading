"""Regression tests for the v2 authenticity fixes:

  * 200-MA swing strategies no longer raise on short (walk-forward) slices.
  * BB mean-reversion intraday emits only valid-geometry trades.
  * The backtest sizes each trade to ONE portfolio slot (slot_capital), and
    reports ROI against that slot.

Run from apps/engine:  python -m pytest test/test_roadmap_fixes.py -q
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest_config import RISK  # noqa: E402
from strategies.base import BaseStrategy  # noqa: E402
from strategies.swing.golden_cross import GoldenCrossStrategy  # noqa: E402
from strategies.swing.ema200_macd import EMA200MACDStrategy  # noqa: E402
from strategies.swing.sma44_pullback import SMA44PullbackStrategy  # noqa: E402
from strategies.intraday.bb_mean_reversion_intraday import (  # noqa: E402
    BBMeanReversionIntradayStrategy,
)


def _random_ohlc(n, seed=0, freq="D"):
    rng = np.random.default_rng(seed)
    base = 100 + np.cumsum(rng.standard_normal(n) * 0.5)
    df = pd.DataFrame({
        "Open": base,
        "High": base + np.abs(rng.standard_normal(n)),
        "Low": base - np.abs(rng.standard_normal(n)),
        "Close": base + rng.standard_normal(n) * 0.2,
        "Volume": rng.integers(1000, 9000, n),
    })
    df.index = pd.date_range("2024-01-01", periods=n, freq=freq)
    return df


@pytest.mark.parametrize("Strat", [GoldenCrossStrategy, EMA200MACDStrategy, SMA44PullbackStrategy])
@pytest.mark.parametrize("n", [20, 50, 80, 199])
def test_200ma_strategies_safe_on_short_slices(Strat, n):
    """Walk-forward folds can be <200 bars; pandas_ta returns None there. The
    guard must produce a clean zero-signal frame instead of raising."""
    df = _random_ohlc(n, seed=n)
    out = Strat().generate_signals(df.copy())
    for col in ("signal", "stop_loss", "target"):
        assert col in out.columns
    assert (out["signal"] == 0).all()
    # run_backtest must not raise either (this is what 500'd /run-walk-forward).
    m = Strat().run_backtest(df.copy())
    assert m["totalTrades"] == 0


def test_bb_mean_reversion_geometry_is_valid():
    """Every emitted long must have target above entry-ish (room to the mid
    band); shorts the reverse. Invalid geometry would be silently skipped."""
    df = _random_ohlc(400, seed=7, freq="15min")
    out = BBMeanReversionIntradayStrategy().generate_signals(df.copy())
    longs = out[out["signal"] == 1]
    shorts = out[out["signal"] == -1]
    # For longs the target (mid band) must sit above the signal close.
    assert (longs["target"] > longs["Close"]).all()
    assert (longs["stop_loss"] < longs["Close"]).all()
    # For shorts the target must sit below the signal close.
    assert (shorts["target"] < shorts["Close"]).all()
    assert (shorts["stop_loss"] > shorts["Close"]).all()


def test_backtest_sizes_to_one_slot():
    """A single-cell backtest must cap notional at one slot (slot_capital) and
    report ROI against the slot, not the whole ₹1L account."""
    assert RISK.slot_capital == RISK.initial_capital / RISK.max_concurrent_positions
    assert RISK.max_position_value == RISK.slot_capital

    class _OneBuy(BaseStrategy):
        name, timeframe = "ONE_BUY", "1D"

        def generate_signals(self, df):
            df = df.copy()
            df["signal"] = 0
            df.iloc[0, df.columns.get_loc("signal")] = 1
            df["stop_loss"] = 95.0
            df["target"] = 110.0
            return df

    # entry ~100, target 110 hit on bar 2's high.
    idx = pd.date_range("2024-01-01", periods=3, freq="D")
    df = pd.DataFrame({
        "Open": [100, 100, 101], "High": [101, 102, 111],
        "Low": [99, 99, 100], "Close": [100, 101, 105],
    }, index=idx)
    sim = _OneBuy().simulate(df)
    # qty capped by slot: floor(slot_capital / entry) bound. With slot=10k, entry~100
    # the risk-based qty (slot*2% / 5 = 40) binds, well under the 100-share notional cap.
    m = _OneBuy().run_backtest(df)
    assert m["totalTrades"] == 1
    # ROI denominator is the slot, so netProfit / slot_capital * 100 == roiPercentage.
    assert m["roiPercentage"] == pytest.approx(m["netProfit"] / RISK.slot_capital * 100, abs=0.01)
