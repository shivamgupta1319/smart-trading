"""The market-condition label stamped on every trade.

Run from apps/engine:  python -m pytest test/test_market_condition.py -q
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_condition import aligned, breadth_pct, direction_from_moves, move_from_day_open  # noqa: E402


def _intraday(day_open, last_close, prev_day_close=100.0):
    idx = pd.to_datetime(["2026-11-18 15:15", "2026-11-19 09:15", "2026-11-19 09:30", "2026-11-19 09:45"])
    return pd.DataFrame({"Open": [prev_day_close, day_open, day_open, day_open],
                         "High": 0.0, "Low": 0.0,
                         "Close": [prev_day_close, day_open, day_open, last_close]}, index=idx)


def test_move_is_measured_from_todays_open_not_yesterdays_close():
    # Gapped up 5% overnight, then flat: the day's move is 0, not +5%.
    assert move_from_day_open(_intraday(105.0, 105.0)) == 0.0
    assert round(move_from_day_open(_intraday(200.0, 201.0)), 3) == 0.5
    assert move_from_day_open(pd.DataFrame()) is None


def test_direction_needs_enough_stocks_and_a_clear_median():
    assert direction_from_moves([0.5] * 7) == (None, None)            # 7 stocks is not a market
    assert direction_from_moves([0.5] * 8)[0] == "UP"
    assert direction_from_moves([-0.4] * 9)[0] == "DOWN"
    assert direction_from_moves([0.1, -0.1, 0.05, -0.05, 0.12, -0.12, 0.0, 0.14])[0] == "FLAT"
    # One huge mover does not decide it: the MEDIAN stock does.
    assert direction_from_moves([9.0] + [-0.3] * 8)[0] == "DOWN"


def test_breadth_is_the_share_of_stocks_above_their_open():
    assert breadth_pct([0.2, 0.1, -0.3, -0.1]) == 50.0
    assert breadth_pct([]) is None


def test_aligned_with_the_market():
    assert aligned("BUY", "UP") is True and aligned("SELL", "DOWN") is True
    assert aligned("BUY", "DOWN") is False and aligned("SELL", "UP") is False
    assert aligned("BUY", "FLAT") is None and aligned("SELL", None) is None


def test_scanner_reads_direction_from_the_cycles_candles_and_labels_the_payload():
    import scanner.live_scanner as scanner

    cache = {(f"S{i}", "15m"): _intraday(100.0, 100.6) for i in range(9)}
    cache[("S0", "5m")] = _intraday(100.0, 90.0)        # a second timeframe of the same stock is not counted twice
    cache[("S1", "1D")] = _intraday(100.0, 50.0)        # daily frames say nothing about today's direction
    scanner.market_state.update({"regime": "RANGING", "direction": None, "breadth": None,
                                 "regime_checked": 10**12})   # skip the network refresh of the regime
    scanner.refresh_market_state(cache)
    assert scanner.market_state["direction"] == "UP" and scanner.market_state["breadth"] == 100.0
    src = open(os.path.join(os.path.dirname(__file__), "..", "scanner", "live_scanner.py")).read()
    for field in ('"marketRegime"', '"marketDirection"', '"marketBreadthPct"', '"alignedWithMarket"'):
        assert field in src


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
