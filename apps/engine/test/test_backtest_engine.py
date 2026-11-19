"""Correctness tests for the realistic backtest engine (strategies/base.py).

Run from apps/engine:  python -m pytest test/test_backtest_engine.py -q
"""
import dataclasses
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import strategies.base as base_module  # noqa: E402
from backtest_config import RISK, slippage_per_share  # noqa: E402
from strategies.base import BaseStrategy, stop_fill_price  # noqa: E402


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


def _gross_of_single_trade(rows, sl=95, tp=120):
    sim = _FixedSignalStrategy(sl=sl, tp=tp).simulate(_make_df(rows))
    assert len(sim["gross_trades"]) == 1
    return sim["gross_trades"][0]


_ENTRY = 100 + slippage_per_share(100)  # long entry at next-bar open 100, adverse slippage


def test_gap_through_stop_fills_at_the_open_not_the_stop():
    # Same trade twice (entry 100, SL 95). In one the stop is touched intrabar;
    # in the other the bar OPENS at 92, below the stop. Sizing is identical, so
    # the ratio of the two losses is the ratio of the per-share losses.
    touched = _gross_of_single_trade([
        (100, 101, 99, 100), (100, 102, 99, 101),
        (101, 102, 94, 96),    # opens 101, trades down through 95 -> fills at 95
    ])
    gapped = _gross_of_single_trade([
        (100, 101, 99, 100), (100, 102, 99, 101),
        (92, 93, 90, 91),      # opens 92, already through 95 -> fills at 92
    ])
    assert touched < 0 and gapped < 0
    expected = (_ENTRY - (92 - slippage_per_share(92))) / (_ENTRY - (95 - slippage_per_share(95)))
    assert gapped / touched == pytest.approx(expected, rel=1e-9)
    assert gapped < touched  # the gap costs more than the stop distance


def test_gap_fill_can_be_switched_off_for_attribution(monkeypatch):
    # RISK is a frozen dataclass: swap the engine's reference for an edited copy.
    monkeypatch.setattr(base_module, "RISK", dataclasses.replace(RISK, gap_through_stop_at_open=False))
    rows_touched = [(100, 101, 99, 100), (100, 102, 99, 101), (101, 102, 94, 96)]
    rows_gapped = [(100, 101, 99, 100), (100, 102, 99, 101), (92, 93, 90, 91)]
    # Old behaviour: both book the stop price, so the losses are equal.
    assert _gross_of_single_trade(rows_gapped) == pytest.approx(_gross_of_single_trade(rows_touched))


def test_stop_fill_price_long_and_short():
    # Long: a gap down through the stop fills lower; no gap fills at the stop.
    assert stop_fill_price(95, 92, is_buy=True) == 92
    assert stop_fill_price(95, 101, is_buy=True) == 95
    # Short: a gap up through the stop fills higher; no gap fills at the stop.
    assert stop_fill_price(105, 108, is_buy=False) == 108
    assert stop_fill_price(105, 99, is_buy=False) == 105
    # A missing open falls back to the stop instead of propagating NaN.
    assert stop_fill_price(95, float("nan"), is_buy=True) == 95


def test_slippage_is_at_least_one_tick_per_share():
    # Rs 60 share: 5 basis points would be Rs 0.03, less than the Rs 0.05 tick.
    assert slippage_per_share(60.0) == pytest.approx(0.05)
    assert slippage_per_share(100.0) == pytest.approx(0.05)      # where the two meet
    assert slippage_per_share(4000.0) == pytest.approx(2.0)      # 5 basis points
    # The engine uses it on both sides: a Rs 60 long that exits flat at Rs 60 loses 2 ticks a share.
    df = _make_df([(60, 60.2, 59.8, 60), (60, 60.2, 59.8, 60), (60, 60.2, 59.8, 60)])
    sim = _FixedSignalStrategy(sl=57, tp=66).simulate(df)        # still open at the end: marked to the last close
    assert len(sim["gross_trades"]) == 1
    qty = round(sim["gross_trades"][0] / -0.10)
    assert qty > 0 and sim["gross_trades"][0] == pytest.approx(-0.10 * qty)


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
