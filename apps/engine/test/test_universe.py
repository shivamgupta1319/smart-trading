"""The stock lists: who is tested for swing, who for intraday, and how they are measured.

Run from apps/engine:  python -m pytest test/test_universe.py -q
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import universe  # noqa: E402


def daily(close, volume, spread_pct, days=80):
    idx = pd.bdate_range("2026-07-01", periods=days)
    c = np.full(days, float(close))
    return pd.DataFrame({"Open": c, "High": c * (1 + spread_pct / 200), "Low": c * (1 - spread_pct / 200),
                         "Close": c, "Volume": np.full(days, float(volume))}, index=idx)


def test_figures_are_value_traded_and_daily_range():
    f = universe.figures(daily(close=500, volume=2_000_000, spread_pct=3.0))
    assert f == {"traded_value_cr": 100.0, "day_range_pct": 3.0, "last_close": 500.0}   # 500 x 20 lakh = Rs 100 crore


def test_one_freak_day_does_not_make_a_thin_stock_liquid():
    df = daily(close=100, volume=10_000, spread_pct=2.0)
    df.iloc[-1, df.columns.get_loc("Volume")] = 50_000_000      # one day of Rs 500 crore
    assert universe.figures(df)["traded_value_cr"] == 0.1       # the median still says Rs 10 lakh


def test_too_little_history_is_not_measured():
    assert universe.figures(daily(100, 1000, 2.0, days=15)) is None


def test_only_the_intraday_list_gets_intraday_candles():
    assert universe.timeframes_for(True, ["1D", "15m", "5m"]) == ["1D", "15m", "5m"]
    assert universe.timeframes_for(False, ["1D", "15m", "5m"]) == ["1D"]
    assert universe.timeframes_for(False, ["15m"]) == []


def test_intraday_strategies_are_known_by_their_bucket():
    assert universe.is_intraday_strategy("RVOL_ORB")
    assert not universe.is_intraday_strategy("Golden_Cross")


def test_the_intraday_list_is_the_liquid_stocks_that_move_most():
    rows = [
        {"symbol": "CALM", "traded_value_cr": 900, "day_range_pct": 1.1, "last_close": 1500},
        {"symbol": "LIVELY", "traded_value_cr": 400, "day_range_pct": 3.4, "last_close": 300},
        {"symbol": "WILD_BUT_THIN", "traded_value_cr": 12, "day_range_pct": 6.0, "last_close": 200},
        {"symbol": "PENNY", "traded_value_cr": 300, "day_range_pct": 5.0, "last_close": 18},
        {"symbol": "PRICEY", "traded_value_cr": 500, "day_range_pct": 4.0, "last_close": 9000},
        {"symbol": "STEADY", "traded_value_cr": 250, "day_range_pct": 2.2, "last_close": 800},
        {"symbol": "UNMEASURED", "traded_value_cr": None, "day_range_pct": None, "last_close": None},
    ]
    picked = universe.pick_intraday(rows, top=2, min_value_cr=100, min_price=50, max_price=5000)
    assert [r["symbol"] for r in picked] == ["LIVELY", "STEADY"]
