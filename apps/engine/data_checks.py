"""Checks on candle data: what may be stored, and which stocks need a human to look.

Until now nothing checked the candles under every backtest and every signal, and a bad row
or a stitched price series produced confident, wrong numbers with no warning. Three jobs:

1. `clean_candles`   Before candles are stored: rows that cannot be real (missing values,
                     zero or negative prices, a high below the open or close, an intraday
                     bar outside market hours, a repeated timestamp) are left
                     out and COUNTED. Nothing is dropped silently: the caller reports it.

2. `price_jumps` /   A daily close that moves more than 20% is either a real market event
   `unexplained_jumps`  or a fault in the data (a demerger the source does not adjust for, or
                     history stitched across a split). Prices alone cannot tell them apart,
                     so each one must be reviewed and listed in config/known_price_actions.json.
                     A stock with an unlisted jump is flagged.

3. `back_adjust`     For a reviewed demerger, earlier prices are scaled by the size of the
                     step so indicators and backtests see one continuous series, the way a
                     stock split is treated.

`adjustment_shift` detects the other fault: the source re-scaled its whole history (a split
or dividend), so newly fetched bars no longer line up with stored ones and the stored
series must be fetched again in full.

All frames use an IST clock-time index with no timezone, like the stored history.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, time
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

OHLC = ("Open", "High", "Low", "Close")
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
JUMP_LOG_RETURN = 0.20      # |ln(close / previous close)| above this needs review
ADJUSTMENT_TOLERANCE = 0.005  # stored vs re-fetched closes differing by more than 0.5%
KINDS = frozenset({"real_move", "demerger"})

_HERE = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Problem:
    check: str
    rows: int
    detail: str = ""

    def __str__(self) -> str:
        return f"{self.check}: {self.rows} row(s){' — ' + self.detail if self.detail else ''}"


def clean_candles(df: pd.DataFrame, timeframe: str) -> tuple[pd.DataFrame, list[Problem]]:
    """The rows fit to store, and a count of every kind of row that was left out."""
    problems: list[Problem] = []
    if df.empty:
        return df, problems
    out = df.copy()

    def drop(mask: pd.Series, check: str, detail: str = "") -> None:
        nonlocal out
        n = int(mask.sum())
        if n:
            first = out.index[mask.to_numpy()][0]
            problems.append(Problem(check, n, detail or f"first at {first}"))
            out = out[~mask.to_numpy()]

    drop(out[list(OHLC)].isna().any(axis=1), "missing_value")
    drop((out[list(OHLC)] <= 0).any(axis=1), "non_positive_price")
    if "Volume" in out.columns:
        drop(out["Volume"].fillna(0) < 0, "negative_volume")
    body_high = out[["Open", "Close"]].max(axis=1)
    body_low = out[["Open", "Close"]].min(axis=1)
    drop((out["High"] < body_high) | (out["Low"] > body_low) | (out["High"] < out["Low"]), "high_low_inconsistent")

    # Weekend bars are NOT dropped: NSE holds real sessions on some Saturdays (Budget day)
    # and a short Muhurat session at Diwali. Only intraday bars outside normal hours go,
    # because session-based strategies (opening range, VWAP) would misread them.
    if isinstance(out.index, pd.DatetimeIndex):
        if timeframe != "1D":
            t = out.index.time
            outside = pd.Series([(x < MARKET_OPEN) or (x >= MARKET_CLOSE) for x in t], index=out.index)
            drop(outside, "outside_market_hours")
        dup = pd.Series(out.index.duplicated(keep="last"), index=out.index)
        drop(dup, "duplicate_timestamp")
        if not out.index.is_monotonic_increasing:
            out = out.sort_index()
            problems.append(Problem("unsorted", len(out), "re-sorted by time"))
    return out, problems


# ── price jumps ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Jump:
    day: date
    pct: float  # simple return, e.g. -64.9

    def __str__(self) -> str:
        return f"{self.day.isoformat()} {self.pct:+.1f}%"


def price_jumps(daily_close: pd.Series, threshold: float = JUMP_LOG_RETURN) -> list[Jump]:
    """Every daily close-to-close move larger than the threshold."""
    close = daily_close.dropna()
    if len(close) < 2:
        return []
    log_ret = np.log(close / close.shift())
    hits = log_ret[log_ret.abs() > threshold]
    return [Jump(pd.Timestamp(ts).date(), float((np.exp(v) - 1) * 100)) for ts, v in hits.items()]


def _known_path() -> Path:
    if os.getenv("KNOWN_PRICE_ACTIONS_PATH"):
        return Path(os.environ["KNOWN_PRICE_ACTIONS_PATH"])
    inside_image = _HERE / "config" / "known_price_actions.json"
    if inside_image.is_file() or len(_HERE.parents) < 2:
        return inside_image
    return _HERE.parents[1] / "config" / "known_price_actions.json"


@lru_cache(maxsize=1)
def load_known_actions() -> dict[str, list[dict]]:
    """{SYMBOL: [{date, kind, note}]}. An unknown kind is an error, not a shrug: a safety
    list that tolerates typos is not a safety list."""
    raw = json.loads(_known_path().read_text())
    known: dict[str, list[dict]] = {}
    for symbol, entries in raw.items():
        if symbol.startswith("_"):
            continue
        parsed = []
        for e in entries:
            if e["kind"] not in KINDS:
                raise ValueError(f"{symbol} {e['date']}: kind {e['kind']!r} is not one of {sorted(KINDS)}")
            parsed.append({"date": date.fromisoformat(e["date"]), "kind": e["kind"], "note": e.get("note", "")})
        known[symbol.upper()] = parsed
    return known


def unexplained_jumps(symbol: str, daily_close: pd.Series, known: dict[str, list[dict]] | None = None) -> list[Jump]:
    """Jumps on dates nobody has reviewed. Empty means the stock's history is accounted for."""
    known = load_known_actions() if known is None else known
    reviewed = {e["date"] for e in known.get(symbol.upper(), [])}
    return [j for j in price_jumps(daily_close) if j.day not in reviewed]


def back_adjust(df: pd.DataFrame, symbol: str, known: dict[str, list[dict]] | None = None) -> pd.DataFrame:
    """Scale prices BEFORE each reviewed demerger by the size of the step on that day.

    The step is measured from the frame itself: the last close before the date against the
    first price on it (the close on daily bars; the open on intraday bars, so the day's own
    movement is not counted). Applied when history is loaded, never written back, so it is
    safe to call on every load. A frame that does not span the date is returned unchanged.
    """
    known = load_known_actions() if known is None else known
    demergers = sorted(e["date"] for e in known.get(symbol.upper(), []) if e["kind"] == "demerger")
    if not demergers or df.empty or not isinstance(df.index, pd.DatetimeIndex):
        return df
    out = df
    daily = (out.index.normalize() == out.index).all()
    for day in demergers:
        cut = pd.Timestamp(day)
        before = out.index < cut
        after = ~before
        if not before.any() or not after.any():
            continue
        prev_close = float(out.loc[before, "Close"].iloc[-1])
        first = out.loc[after].iloc[0]
        ref = float(first["Close"] if daily else first["Open"])
        if prev_close <= 0 or ref <= 0:
            continue
        factor = ref / prev_close
        cols = [c for c in OHLC if c in out.columns]
        if out is df:
            out = df.copy()
            out[cols] = out[cols].astype(float)  # whole-number prices cannot hold the scaled values
        out.loc[before, cols] = out.loc[before, cols] * factor
    return out


def adjustment_shift(stored_close: pd.Series, fetched_close: pd.Series,
                     tolerance: float = ADJUSTMENT_TOLERANCE) -> float | None:
    """How far re-fetched closes sit from the stored ones on the same timestamps, as a
    ratio (fetched / stored), when that is more than the tolerance; otherwise None.

    A consistent ratio away from 1 on bars that are already final means the source has
    re-scaled its history (a split or dividend adjustment) and the stored series is now on
    the old scale. The newest overlapping bar is ignored: it may still have been forming
    when it was stored.
    """
    both = pd.concat([stored_close.rename("stored"), fetched_close.rename("fetched")], axis=1).dropna()
    both = both.iloc[:-1] if len(both) > 1 else both.iloc[0:0]
    both = both[(both["stored"] > 0) & (both["fetched"] > 0)]
    if len(both) < 2:
        return None
    ratio = float((both["fetched"] / both["stored"]).median())
    return ratio if abs(ratio - 1.0) > tolerance else None
