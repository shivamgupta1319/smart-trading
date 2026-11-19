"""Live paper-fill rules (scanner entries and stop/target exits).

Run from apps/engine:  python -m pytest test/test_live_fills.py -q
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live_fills import entry_geometry_ok, stop_exit_price, target_exit_price  # noqa: E402


def test_long_entry_needs_stop_below_and_target_above():
    assert entry_geometry_ok(True, 100, 98, 104) == (True, "")
    # Price ran through the target before the poll saw the signal: nothing left to take.
    assert entry_geometry_ok(True, 105, 98, 104)[0] is False
    # Price already at/below the stop.
    assert entry_geometry_ok(True, 98, 98, 104)[0] is False


def test_short_entry_is_the_mirror():
    assert entry_geometry_ok(False, 100, 102, 96) == (True, "")
    assert entry_geometry_ok(False, 95, 102, 96)[0] is False
    assert entry_geometry_ok(False, 102.5, 102, 96)[0] is False


@pytest.mark.parametrize("entry,stop,target", [
    (0, 98, 104), (-5, 98, 104), (float("nan"), 98, 104), (100, float("nan"), 104), (100, 98, None),
])
def test_missing_or_bad_prices_are_rejected(entry, stop, target):
    ok, why = entry_geometry_ok(True, entry, stop, target)
    assert ok is False and why == "missing price"


def test_stop_out_books_the_worse_of_stop_and_live():
    # Long: the poll sees 97.4 with the stop at 98 → the fill is 97.4, not 98.
    assert stop_exit_price(True, 98, 97.4) == 97.4
    assert stop_exit_price(True, 98, 98) == 98
    # Short: the poll sees 102.6 with the stop at 102 → 102.6.
    assert stop_exit_price(False, 102, 102.6) == 102.6
    assert stop_exit_price(False, 102, 102) == 102


def test_target_books_the_level_not_the_better_live_price():
    assert target_exit_price(104) == 104


def test_scanner_uses_these_rules():
    """Guard against the scanner drifting back to booking the candle close / stop price."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "scanner", "live_scanner.py")).read()
    assert "entry_geometry_ok(" in src and "stop_exit_price(" in src and "target_exit_price(" in src
    assert '"entryPrice": round(float(latest[\'Close\']), 2)' not in src


# ── Scanner: candles completed between polls ─────────────────────────────────

def _bars(signals):
    import pandas as pd
    idx = pd.date_range("2026-11-19 09:15", periods=len(signals), freq="5min")
    return pd.DataFrame({"Close": 100.0, "signal": signals}, index=idx)


def test_first_evaluation_only_looks_at_the_newest_candle():
    from scanner.live_scanner import pick_signal_row
    df = _bars([1, 0, 0])                       # an old signal must not replay on start-up
    assert pick_signal_row(df, None) is None
    assert pick_signal_row(_bars([0, 0, -1]), None)["signal"] == -1


def test_a_signal_on_a_candle_completed_mid_cycle_is_not_lost():
    from scanner.live_scanner import pick_signal_row
    df = _bars([0, 0, 1, 0])                    # signal on the 09:25 candle; newest is 09:30
    seen = df.index[1]                          # last cycle evaluated up to 09:20
    row = pick_signal_row(df, seen)
    assert row is not None and row.name == df.index[2]
    # Already evaluated through the newest candle: nothing new to act on.
    assert pick_signal_row(df, df.index[-1]) is None


def test_catch_up_is_bounded_and_takes_the_most_recent_signal():
    from scanner.live_scanner import pick_signal_row
    df = _bars([1, 0, 0, 0, 0, 0])              # signal 5 candles back
    assert pick_signal_row(df, df.index[0] - (df.index[1] - df.index[0])) is None   # outside the 3-candle window
    df2 = _bars([0, 1, 0, -1, 0])
    assert pick_signal_row(df2, df2.index[0])["signal"] == -1                        # newest of the two


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
