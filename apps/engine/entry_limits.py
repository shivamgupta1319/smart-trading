"""Per-cell entry limits — one rule set for the backtest and the live scanner.

Why this exists: neither path limited how often a (stock, strategy) cell could
re-enter. A strategy whose condition stays true bar after bar (EMA20_Pullback)
re-fired the moment its previous trade stopped out: 1,557 live trades at about
three per stock per day, −₹6.56 lakh, while its backtest looked fine.

Two limits, INTRADAY cells only (a swing cell is already bounded by its daily bar):
  * max trades per cell per trading day
  * a cooldown after any exit before the next entry

`strategies/base.simulate` and `scanner/live_scanner` both call `entry_allowed`,
so the two cannot drift. Times are IST-naive datetimes in both callers.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from backtest_config import _i


@dataclass(frozen=True)
class EntryLimits:
    max_trades_per_day: int   # 0 = unlimited
    cooldown_minutes: int     # 0 = none


# Env-tunable; 0 disables that limit. The scanner and the engine read the same
# code defaults — do not set these in one compose service and not the other.
INTRADAY_LIMITS = EntryLimits(
    max_trades_per_day=_i("ENTRY_MAX_TRADES_PER_DAY_INTRADAY", 2),
    cooldown_minutes=_i("ENTRY_COOLDOWN_MINUTES_INTRADAY", 30),
)


def limits_for_bucket(bucket: str | None) -> EntryLimits | None:
    """Limits for a hold bucket, or None when the bucket is not limited."""
    return INTRADAY_LIMITS if bucket == "INTRADAY" else None


def entry_allowed(
    limits: EntryLimits | None,
    trades_today: int,
    last_exit: datetime | None,
    now: datetime,
) -> tuple[bool, str]:
    """Whether a cell may open a new trade at `now`.

    trades_today: trades this cell already ENTERED on now's trading day.
    last_exit:    when this cell's most recent trade closed (None if never).
    Returns (allowed, reason); reason is empty when allowed.
    """
    if limits is None:
        return True, ""
    if limits.max_trades_per_day > 0 and trades_today >= limits.max_trades_per_day:
        return False, f"daily limit reached ({trades_today}/{limits.max_trades_per_day})"
    if limits.cooldown_minutes > 0 and last_exit is not None:
        wait = timedelta(minutes=limits.cooldown_minutes) - (now - last_exit)
        if wait > timedelta(0):
            return False, f"cooldown ({int(wait.total_seconds() // 60) + 1} min left)"
    return True, ""
