"""Correctness tests for the realistic backtest engine (strategies/base.py).

Run from apps/engine:  python -m pytest test/test_backtest_engine.py -q
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategies.base import BaseStrategy  # noqa: E402


class _FixedSignalStrategy(BaseStrategy):
    """Emits one BUY at bar 0 with explicit SL/TP for deterministic testing."""

    name = "FIXED_TEST"
    timeframe = "1D"

    def __init__(self, sl, tp):
        self._sl = sl
        self._tp = tp

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["signal"] = 0
        df.iloc[0, df.columns.get_loc("signal")] = 1
        df["stop_loss"] = self._sl
        df["target"] = self._tp
        return df


def _make_df(prices_hl):
    """prices_hl: list of (open, high, low, close)."""
    idx = pd.date_range("2024-01-01", periods=len(prices_hl), freq="D")
    o, h, l, c = zip(*prices_hl)
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c}, index=idx)


def test_target_hit_via_intrabar_high():
    # Entry next bar open=100; target 110 is touched by bar 2's HIGH (not close).
    df = _make_df([
        (100, 101, 99, 100),   # signal bar
        (100, 102, 99, 101),   # entry fills here at open=100
        (101, 111, 100, 105),  # HIGH 111 >= target 110 -> exit at TP even though close=105
    ])
    res = _FixedSignalStrategy(sl=95, tp=110).run_backtest(df)
    assert res["totalTrades"] == 1
    assert res["winRate"] == 100.0
    # Net must be below gross because of costs+slippage.
    assert res["netProfit"] < res["grossProfit"]
    assert res["totalCosts"] > 0


def test_stop_hit_via_intrabar_low():
    df = _make_df([
        (100, 101, 99, 100),
        (100, 102, 99, 101),   # entry at 100
        (101, 102, 94, 96),    # LOW 94 <= SL 95 -> stop hit (close 96 would've hidden it)
    ])
    res = _FixedSignalStrategy(sl=95, tp=120).run_backtest(df)
    assert res["totalTrades"] == 1
    assert res["netProfit"] < 0  # a loss


def test_pessimistic_when_bar_straddles_both():
    # A single bar pierces BOTH sl(95) and tp(110): pessimistic => SL fill (loss).
    df = _make_df([
        (100, 101, 99, 100),
        (100, 102, 99, 101),
        (101, 115, 90, 100),   # high 115>=tp AND low 90<=sl
    ])
    res = _FixedSignalStrategy(sl=95, tp=110).run_backtest(df)
    assert res["totalTrades"] == 1
    assert res["winRate"] == 0.0  # pessimistic tie-break books the SL
    assert res["netProfit"] < 0  # treated as the loss


def test_invalid_geometry_is_skipped():
    # SL above entry for a long is invalid -> no trade taken.
    df = _make_df([(100, 101, 99, 100)] + [(100, 101, 99, 100)] * 5)
    res = _FixedSignalStrategy(sl=105, tp=110).run_backtest(df)
    assert res["totalTrades"] == 0
    assert res["skippedInvalid"] >= 1


def test_no_signal_no_trades():
    class _Flat(BaseStrategy):
        name = "FLAT"
        timeframe = "1D"

        def generate_signals(self, df):
            df = df.copy()
            df["signal"] = 0
            return df

    df = _make_df([(100, 101, 99, 100)] * 10)
    res = _Flat().run_backtest(df)
    assert res["totalTrades"] == 0
    assert res["netProfit"] == 0.0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
