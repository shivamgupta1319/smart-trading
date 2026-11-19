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


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
