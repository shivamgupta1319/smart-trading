"""The one rule that decides whether a backtest is good enough to go live.

Run from apps/engine:  python -m pytest test/test_selection_rule.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import selection_rule as rule  # noqa: E402


def cell(**over):
    good = {"totalTrades": 14, "avgRMultiple": 1.19, "rFirstHalf": 0.9, "rSecondHalf": 1.4, "profitFactor": 3.05,
            "netProfit": 3700.0, "maxDrawdown": 588.0, "roiPercentage": 37.0}
    return {**good, **over}


def test_a_sound_swing_cell_passes():
    assert rule.misses(cell(), "LONG_POSITIONAL", strategy_passes_luck=True) == []
    assert rule.verdict(cell(), "LONG_POSITIONAL", True) == {"passes": True, "misses": []}


def test_the_cell_that_exposed_the_hole_is_refused():
    # SBIN · MTF_Alignment as it went live on 2026-11-19: average +0.21R and both halves
    # positive, but Rs 463 of profit against a Rs 1,198 drawdown and a profit factor of 1.25.
    sbin = cell(totalTrades=15, avgRMultiple=0.21, rFirstHalf=0.1, rSecondHalf=0.3, profitFactor=1.25,
                netProfit=463.0, maxDrawdown=1198.0, roiPercentage=4.63)
    missed = rule.misses(sbin, "LONG_POSITIONAL", True)
    assert len(missed) == 3
    assert any("profit factor 1.25" in m for m in missed)
    assert any("0.4 times its worst drawdown" in m for m in missed)
    assert any("total return 4.6%" in m for m in missed)


def test_each_check_on_its_own():
    one = lambda **over: rule.misses(cell(**over), "MID_SWING", True)
    assert any("only 9 trades (needs 10)" in m for m in one(totalTrades=9))
    assert any("average per trade +0.10R" in m for m in one(avgRMultiple=0.10))      # must be ABOVE
    assert any("second half" in m for m in one(rSecondHalf=-0.02))
    assert any("first half" in m for m in one(rFirstHalf=0.0))
    assert any("two halves" in m for m in one(rFirstHalf=None, rSecondHalf=None))
    assert any("profit factor 1.49" in m for m in one(profitFactor=1.49))
    assert one(profitFactor=1.5) == []
    assert any("1.9 times" in m for m in one(netProfit=1900.0, maxDrawdown=1000.0, roiPercentage=19.0))
    assert one(netProfit=2000.0, maxDrawdown=1000.0, roiPercentage=20.0) == []
    assert any("total return 9.9%" in m for m in one(roiPercentage=9.9))
    assert any("it lost money" in m for m in one(netProfit=-50.0, roiPercentage=-0.5))
    # No drawdown at all is not a failure.
    assert one(maxDrawdown=0.0) == []


def test_long_hold_strategies_need_four_trades_not_ten():
    # Golden_Cross signals about twice per stock in five years.
    assert rule.misses(cell(totalTrades=4), "LONG_POSITIONAL", True) == []
    assert any("only 3 trades (needs 4)" in m for m in rule.misses(cell(totalTrades=3), "LONG_POSITIONAL", True))
    assert any("needs 10" in m for m in rule.misses(cell(totalTrades=9), "MID_SWING", True))
    assert any("needs 10" in m for m in rule.misses(cell(totalTrades=9), "SHORT_SWING", True))


def test_intraday_needs_thirty_trades_and_is_not_asked_about_the_luck_test():
    assert any("needs 30" in m for m in rule.misses(cell(totalTrades=29), "INTRADAY", None))
    assert rule.misses(cell(totalTrades=30), "INTRADAY", strategy_passes_luck=False) == []


def test_swing_needs_a_strategy_that_passes_the_luck_test():
    assert rule.misses(cell(), "MID_SWING", strategy_passes_luck=False) == ["its strategy does not pass the luck test"]
    # No luck check stored: that check is left out, not failed.
    assert rule.misses(cell(), "MID_SWING", strategy_passes_luck=None) == []


def test_run_backtest_reports_both_halves():
    import numpy as np
    import pandas as pd
    from strategies import STRATEGY_REGISTRY

    rng = np.random.default_rng(3)
    idx = pd.bdate_range("2021-01-01", periods=900)
    close = 100 * np.cumprod(1 + rng.normal(0.0006, 0.015, len(idx)))
    df = pd.DataFrame({"Open": close * 0.999, "High": close * 1.012, "Low": close * 0.988, "Close": close,
                       "Volume": rng.integers(1e5, 1e6, len(idx))}, index=idx)
    m = STRATEGY_REGISTRY["EMA_10_50_Cross"].run_backtest(df)
    assert "rFirstHalf" in m and "rSecondHalf" in m
    if m["totalTrades"] >= 2:
        assert m["rFirstHalf"] is not None and m["rSecondHalf"] is not None
    else:
        assert m["rFirstHalf"] is None
