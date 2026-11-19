"""The market's condition at the moment a trade is opened: the label every trade carries.

Why: on the old paper book, intraday trades taken WITH the market's direction averaged
+0.215R and trades against it +0.049R, and long-only swing trades lost through a falling
market. Nothing recorded the condition, so the pattern could only be dug out afterwards.
This module produces the label; the scanner sends it with each signal; the API stores it on
the trade. It does not block anything: first the evidence, then (later) rules built on it.

Two parts, both simple on purpose:
  * regime     NIFTY 50 on daily bars: TRENDING_UP / TRENDING_DOWN / RANGING / VOLATILE
               (the existing classifier in routers/regime.py).
  * direction  what the roster's stocks are doing TODAY: the median stock's move from its
               day open. UP above +0.15%, DOWN below -0.15%, else FLAT. This is the same
               measure, with the same thresholds, as the analysis that found the pattern.
"""
from __future__ import annotations

from statistics import median

import pandas as pd

DIRECTION_THRESHOLD_PCT = 0.15   # median move from the day's open, in percent
MIN_STOCKS_FOR_DIRECTION = 8     # fewer than this is not a "market"


def move_from_day_open(df: pd.DataFrame) -> float | None:
    """Percent move of the last completed bar's close from that same day's first open,
    for one stock's intraday frame. None when it cannot be computed."""
    if df is None or df.empty or not isinstance(df.index, pd.DatetimeIndex):
        return None
    last_day = df.index[-1].date()
    today = df[df.index.date == last_day]
    if today.empty:
        return None
    day_open = float(today["Open"].iloc[0])
    last = float(today["Close"].iloc[-1])
    if day_open <= 0 or last <= 0:
        return None
    return (last / day_open - 1.0) * 100.0


def direction_from_moves(moves: list[float]) -> tuple[str | None, float | None]:
    """('UP' | 'DOWN' | 'FLAT', median move %) from the stocks' moves, or (None, None)
    when too few stocks have data to call it a market."""
    if len(moves) < MIN_STOCKS_FOR_DIRECTION:
        return None, None
    med = float(median(moves))
    if med > DIRECTION_THRESHOLD_PCT:
        return "UP", med
    if med < -DIRECTION_THRESHOLD_PCT:
        return "DOWN", med
    return "FLAT", med


def breadth_pct(moves: list[float]) -> float | None:
    """Share of stocks trading above their day open, in percent."""
    return round(100.0 * sum(1 for m in moves if m > 0) / len(moves), 1) if moves else None


def aligned(signal_type: str, direction: str | None) -> bool | None:
    """True when the trade goes with the market, False against it, None when the market
    is flat or unknown."""
    if direction == "UP":
        return signal_type == "BUY"
    if direction == "DOWN":
        return signal_type == "SELL"
    return None
