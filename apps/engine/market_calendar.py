"""Is the exchange trading today?

The scanner used to ask only "is it a weekday between 09:15 and 15:30?". On an exchange
holiday (Guru Nanak Jayanti, 24 November 2026) it therefore opened paper trades at
yesterday's closing prices, as if they were live. Two checks now stand in the way:

  1. `is_trading_day` asks a maintained exchange calendar (the `exchange_calendars`
     package, calendar XBOM: BSE, which keeps the same equity holidays and hours as NSE).
     Indian holidays move every year and are announced by circular, so they are not typed
     in here from memory. The package knows dates about a year ahead; beyond that, or if
     it cannot be loaded, a weekday is assumed to be a trading day and check 2 decides.
  2. `session_is_live` looks at the market itself: the NIFTY's newest intraday candle must
     be from today and recent. This catches a holiday the calendar does not know, a
     special closure, and a price feed that has stopped.

The scanner opens and manages trades only when both say yes.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

SESSION_STALE_AFTER = timedelta(minutes=30)   # newest candle older than this = not live

_calendar = None
_calendar_failed = False


def _get_calendar():
    global _calendar, _calendar_failed
    if _calendar is None and not _calendar_failed:
        try:
            import exchange_calendars as xc
            _calendar = xc.get_calendar("XBOM")
        except Exception as exc:   # package missing or broken: fall back to weekdays
            _calendar_failed = True
            print(f"  [WARN] exchange calendar not available ({type(exc).__name__}: {exc}); "
                  f"treating every weekday as a trading day")
    return _calendar


def is_trading_day(day: date) -> bool:
    """Whether the exchange holds a normal session on `day`.

    Inside the calendar's known range the calendar decides (it also knows the rare
    Saturday sessions). Outside it, or without a calendar: Monday to Friday.
    """
    cal = _get_calendar()
    if cal is not None:
        try:
            if cal.first_session.date() <= day <= cal.last_session.date():
                return bool(cal.is_session(day.isoformat()))
        except Exception:
            pass
    return day.weekday() < 5


def session_is_live(newest_candle: datetime | None, now: datetime) -> bool:
    """Whether the market is actually trading at `now`, judged from the time of the newest
    index candle (both IST, naive): it must be from today and not older than
    SESSION_STALE_AFTER. None means there is no candle at all."""
    if newest_candle is None:
        return False
    return newest_candle.date() == now.date() and now - newest_candle <= SESSION_STALE_AFTER
