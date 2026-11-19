"""Per-cell entry limits: daily cap + cooldown, shared by backtest and scanner.

Run from apps/engine:  python -m pytest test/test_entry_limits.py -q
"""
import os
import sys
from datetime import datetime

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import strategies.base as base_module  # noqa: E402
from entry_limits import EntryLimits, entry_allowed, limits_for_bucket  # noqa: E402
from strategies.base import BaseStrategy  # noqa: E402

T = datetime(2026, 11, 19, 11, 0)


def test_only_intraday_is_limited():
    assert limits_for_bucket("INTRADAY") is not None
    for bucket in ("SHORT_SWING", "MID_SWING", "LONG_POSITIONAL", None, "UNKNOWN"):
        assert limits_for_bucket(bucket) is None


def test_no_limits_always_allows():
    assert entry_allowed(None, trades_today=99, last_exit=T, now=T) == (True, "")


def test_daily_cap_blocks_at_the_limit():
    lim = EntryLimits(max_trades_per_day=2, cooldown_minutes=0)
    assert entry_allowed(lim, 1, None, T)[0] is True
    ok, why = entry_allowed(lim, 2, None, T)
    assert ok is False and "daily limit" in why


def test_cooldown_blocks_until_it_has_fully_passed():
    lim = EntryLimits(max_trades_per_day=0, cooldown_minutes=30)
    assert entry_allowed(lim, 5, None, T)[0] is True                       # never traded
    assert entry_allowed(lim, 5, T.replace(minute=0), T.replace(minute=29))[0] is False
    assert entry_allowed(lim, 5, T.replace(minute=0), T.replace(minute=30))[0] is True
    assert entry_allowed(lim, 5, datetime(2026, 11, 18, 15, 15), T)[0] is True  # yesterday


def test_zero_disables_each_limit():
    lim = EntryLimits(max_trades_per_day=0, cooldown_minutes=0)
    assert entry_allowed(lim, 50, T, T)[0] is True


class _AlwaysLong(BaseStrategy):
    """Signals BUY on every bar — the state-based shape that churned live."""

    name = "15m_ORB"  # a registered INTRADAY name, so the engine uses that bucket
    timeframe = "15m"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["signal"] = 1
        df["stop_loss"] = 99.0
        df["target"] = 110.0
        return df


def _two_sessions_of_stop_outs() -> pd.DataFrame:
    """Two days of 15m bars (09:15–15:15) where every bar opens at 100 and trades
    down to 98.5, so each trade is stopped out on the bar it enters."""
    idx = []
    for day in ("2026-11-18", "2026-11-19"):
        idx += list(pd.date_range(f"{day} 09:15", f"{day} 15:15", freq="15min"))
    n = len(idx)
    return pd.DataFrame(
        {"Open": [100.0] * n, "High": [100.5] * n, "Low": [98.5] * n,
         "Close": [99.5] * n, "Volume": [1000] * n},
        index=pd.DatetimeIndex(idx),
    )


def _trades(monkeypatch, limits):
    monkeypatch.setattr(base_module, "limits_for_bucket", lambda bucket: limits)
    sim = _AlwaysLong().simulate(_two_sessions_of_stop_outs())
    return len(sim["net_trades"]), sim["skipped_limits"]


def test_backtest_without_limits_churns(monkeypatch):
    trades, skipped = _trades(monkeypatch, None)
    assert trades > 20 and skipped == 0


def test_backtest_daily_cap_holds_per_session(monkeypatch):
    trades, skipped = _trades(monkeypatch, EntryLimits(max_trades_per_day=2, cooldown_minutes=0))
    assert trades == 4          # 2 per day × 2 days: the cap resets each session
    assert skipped > 0


def test_backtest_cooldown_spaces_entries(monkeypatch):
    unlimited, _ = _trades(monkeypatch, None)
    cooled, skipped = _trades(monkeypatch, EntryLimits(max_trades_per_day=0, cooldown_minutes=60))
    assert 4 < cooled < unlimited
    assert skipped > 0


def test_default_limits_apply_to_a_real_intraday_cell():
    # No monkeypatch: the shipped defaults (2 per day) must bound the churn case.
    sim = _AlwaysLong().simulate(_two_sessions_of_stop_outs())
    assert len(sim["net_trades"]) <= 4


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
