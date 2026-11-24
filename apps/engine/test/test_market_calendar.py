"""Is the exchange trading today? Holidays, weekends and a market that is not moving.

Run from apps/engine:  python -m pytest test/test_market_calendar.py -q
"""
import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import market_calendar as mc  # noqa: E402


def test_the_holiday_that_exposed_the_bug_is_not_a_trading_day():
    # 24 November 2026, a Tuesday: the scanner opened four paper trades at stale prices.
    assert not mc.is_trading_day(date(2026, 11, 24))
    assert mc.is_trading_day(date(2026, 11, 23))
    assert mc.is_trading_day(date(2026, 11, 25))


def test_fixed_holidays_and_weekends_are_closed():
    assert not mc.is_trading_day(date(2026, 1, 26))    # Republic Day, a Monday
    assert not mc.is_trading_day(date(2026, 12, 25))   # Christmas, a Friday
    assert not mc.is_trading_day(date(2026, 11, 21))   # Saturday
    assert not mc.is_trading_day(date(2026, 11, 22))   # Sunday


def test_a_special_saturday_session_counts():
    assert mc.is_trading_day(date(2025, 2, 1))         # Union Budget day


def test_beyond_what_the_calendar_knows_a_weekday_is_assumed_open():
    assert mc.is_trading_day(date(2035, 3, 6))         # a Tuesday far past the calendar
    assert not mc.is_trading_day(date(2035, 3, 4))     # a Sunday


def test_without_a_calendar_it_falls_back_to_weekdays(monkeypatch):
    monkeypatch.setattr(mc, "_calendar", None)
    monkeypatch.setattr(mc, "_calendar_failed", True)
    assert mc.is_trading_day(date(2026, 11, 24))       # cannot know it is a holiday...
    assert not mc.is_trading_day(date(2026, 11, 22))


def test_the_market_is_live_only_with_a_fresh_candle_from_today():
    now = datetime(2026, 11, 24, 9, 45)
    # ...which is why the second check exists: on that holiday the newest index candle
    # was yesterday's 15:25.
    assert not mc.session_is_live(datetime(2026, 11, 23, 15, 25), now)
    assert not mc.session_is_live(None, now)
    assert mc.session_is_live(datetime(2026, 11, 24, 9, 40), now)
    # A feed that stopped an hour ago is not live either.
    assert not mc.session_is_live(datetime(2026, 11, 24, 8, 40), now)
