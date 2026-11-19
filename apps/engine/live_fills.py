"""What price a LIVE paper trade is booked at — entries and stop/target exits.

The scanner used to book an entry at the close of the last completed candle (for a
daily strategy that is YESTERDAY's close) and a stop-out at exactly the stop price.
Neither is a price the trade could have got: the signal is only seen after the bar
has closed, and the exit is a market order sent when a poll notices the level broke.

Rules (IST polling scanner, paper book):
  * Entry      — the live quote when the signal is found. This is the live twin of
                 the backtest's next-bar-open entry.
  * Stop hit   — the WORSE of the stop and the live price (price is already through).
  * Target hit — the target itself, never the better live price (conservative; the
                 backtest also books the target level).
"""
from __future__ import annotations

import math


def entry_geometry_ok(is_buy: bool, entry: float, stop: float, target: float) -> tuple[bool, str]:
    """A live entry is only valid with the stop on the losing side and the target on
    the winning side — the same check `strategies/base.simulate` applies. Price can
    run past either level between the candle close and the poll that sees the signal.
    """
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (entry, stop, target)) or entry <= 0:
        return False, "missing price"
    if is_buy and not (stop < entry < target):
        return False, f"live ₹{entry} is outside stop ₹{stop} .. target ₹{target}"
    if not is_buy and not (target < entry < stop):
        return False, f"live ₹{entry} is outside target ₹{target} .. stop ₹{stop}"
    return True, ""


def stop_exit_price(is_buy: bool, stop: float, live: float) -> float:
    """Booked price for a stop-out noticed at `live`: the worse of the two."""
    return min(stop, live) if is_buy else max(stop, live)


def target_exit_price(target: float) -> float:
    """Booked price for a target hit: the level, not the (better) live price."""
    return target
