"""Strategy logic fixes from the 2026-11 review (docs/strategies.md).

Run from apps/engine:  python -m pytest test/test_strategy_fixes.py -q
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategies import STRATEGY_REGISTRY  # noqa: E402
from strategies.intraday.gap_and_go import GapAndGoStrategy  # noqa: E402
from strategies.swing.bb_squeeze import BBSqueezeStrategy  # noqa: E402
from strategies.swing.fibonacci_golden_zone import FibonacciGoldenZoneStrategy  # noqa: E402
from strategies.swing.mtf_alignment import MTFAlignmentStrategy  # noqa: E402
from strategies.swing.rsi_divergence import RSIDivergenceStrategy  # noqa: E402


def test_retired_strategies_are_gone():
    for name in ("EMA20_Pullback", "Volume_Profile_POC", "VWAP_Supertrend"):
        assert name not in STRATEGY_REGISTRY
    assert len(STRATEGY_REGISTRY) == 28


# ── Gap_And_Go ────────────────────────────────────────────────────────────────

def _five_min_day(day, bars):
    """bars: list of (open, high, low, close) from 09:15."""
    idx = pd.date_range(f"{day} 09:15", periods=len(bars), freq="5min")
    o, h, l, c = zip(*bars)
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Volume": 1000}, index=idx)


def _gap_frame(second_day_bars):
    flat = [(100, 100.2, 99.8, 100)] * 12
    return pd.concat([_five_min_day("2026-11-18", flat), _five_min_day("2026-11-19", second_day_bars)])


def test_gap_and_go_signals_on_the_0925_candle_the_scanner_can_see():
    # Gap up 1% (prev close 100 → open 101), first candle green, gap still held at 09:30.
    day2 = [(101, 101.6, 100.9, 101.5), (101.5, 101.8, 101.3, 101.6), (101.6, 102.0, 101.4, 101.9)] \
        + [(101.9, 102.0, 101.7, 101.9)] * 9
    out = GapAndGoStrategy().generate_signals(_gap_frame(day2))
    fired = out[out["signal"] != 0]
    assert len(fired) == 1
    row = fired.iloc[0]
    assert fired.index[0].time().strftime("%H:%M") == "09:25"   # not the 09:15 candle
    assert row["signal"] == 1
    assert row["stop_loss"] == 100.9                             # low of the day so far
    assert row["target"] == 101.9 + 2 * (101.9 - 100.9)


def test_gap_and_go_skips_a_gap_that_failed_in_the_first_15_minutes():
    # Gap up, but by 09:30 price is back below the day's open.
    day2 = [(101, 101.6, 100.9, 101.5), (101.5, 101.5, 100.7, 100.8), (100.8, 100.9, 100.4, 100.5)] \
        + [(100.5, 100.6, 100.4, 100.5)] * 9
    out = GapAndGoStrategy().generate_signals(_gap_frame(day2))
    assert (out["signal"] == 0).all()


def test_gap_and_go_short_mirror_and_no_gap_no_trade():
    day2 = [(99, 99.1, 98.4, 98.5), (98.5, 98.7, 98.2, 98.4), (98.4, 98.6, 98.0, 98.1)] \
        + [(98.1, 98.3, 98.0, 98.1)] * 9
    out = GapAndGoStrategy().generate_signals(_gap_frame(day2))
    fired = out[out["signal"] != 0]
    assert len(fired) == 1 and fired.iloc[0]["signal"] == -1
    assert fired.iloc[0]["stop_loss"] == 99.1                    # high of the day so far

    no_gap = [(100.1, 100.6, 100.0, 100.5), (100.5, 100.8, 100.4, 100.7), (100.7, 101.0, 100.6, 100.9)] \
        + [(100.9, 101.0, 100.8, 100.9)] * 9
    assert (GapAndGoStrategy().generate_signals(_gap_frame(no_gap))["signal"] == 0).all()


# ── Fibonacci_Golden_Zone ─────────────────────────────────────────────────────

def _daily(closes, spread=0.5, green_last=True):
    idx = pd.date_range("2025-01-01", periods=len(closes), freq="D")
    closes = np.asarray(closes, dtype=float)
    opens = closes - 0.3
    df = pd.DataFrame({"Open": opens, "High": closes + spread, "Low": opens - spread,
                       "Close": closes, "Volume": 1000}, index=idx)
    return df


def test_fibonacci_fires_on_a_pullback_in_an_upswing_but_not_in_a_downswing():
    # Up-move 100 → 130 (low first, then high), then a pullback into the 50–61.8% zone.
    up = list(np.linspace(100, 130, 30)) + [124, 119, 115.5]
    out_up = FibonacciGoldenZoneStrategy().generate_signals(_daily(up))
    assert (out_up["signal"] == 1).any()

    # Down-move 130 → 100 (high first, then low), then a bounce into the same price zone.
    down = list(np.linspace(130, 100, 30)) + [104, 109, 113.5]
    out_down = FibonacciGoldenZoneStrategy().generate_signals(_daily(down))
    assert (out_down["signal"] == 0).all()


# ── BB_Squeeze ────────────────────────────────────────────────────────────────

def test_bb_squeeze_fires_on_a_breakout_out_of_a_squeeze():
    rng = np.random.default_rng(1)
    wide = 100 + np.cumsum(rng.standard_normal(150) * 1.5)          # normal volatility
    # Squeeze: a steady ±0.05 wiggle, so the bandwidth sits exactly at its 6-month low.
    tight = wide[-1] + 0.05 * np.array([(-1) ** k for k in range(40)])
    breakout = [tight[-1] + 4.0, tight[-1] + 5.0]                   # closes far above the band
    out = BBSqueezeStrategy().generate_signals(_daily(list(wide) + list(tight) + breakout))
    assert out["signal"].iloc[-2] == 1          # the breakout bar itself
    assert out["signal"].iloc[-1] == 0          # edge-triggered: not again on the next bar


# ── RSI_Divergence ────────────────────────────────────────────────────────────

def test_rsi_divergence_never_signals_on_consecutive_bars():
    rng = np.random.default_rng(5)
    for seed in range(6):
        rng = np.random.default_rng(seed)
        closes = 200 + np.cumsum(rng.standard_normal(600) * 2.0 - 0.05)
        sig = RSIDivergenceStrategy().generate_signals(_daily(np.maximum(closes, 5)))["signal"].to_numpy()
        assert not ((sig[1:] == 1) & (sig[:-1] == 1)).any()


# ── MTF_Alignment ─────────────────────────────────────────────────────────────

def test_mtf_alignment_runs_on_stored_history_index_names():
    rng = np.random.default_rng(2)
    closes = 100 + np.cumsum(rng.standard_normal(420) * 0.8 + 0.15)   # rising, so it can signal
    for index_name in ("timestamp", "Date", None):
        df = _daily(closes)
        df.index.name = index_name
        out = MTFAlignmentStrategy().generate_signals(df)            # used to raise KeyError('Date')
        assert {"signal", "stop_loss", "target"} <= set(out.columns)
        assert MTFAlignmentStrategy().run_backtest(df)["totalTrades"] >= 0
    assert (out["signal"] == 1).any()


def test_mtf_alignment_does_not_modify_the_callers_frame():
    df = _daily(100 + np.arange(300) * 0.1)
    before = list(df.columns)
    MTFAlignmentStrategy().generate_signals(df)
    assert list(df.columns) == before


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
