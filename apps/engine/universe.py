"""Which stocks are tested, and for what.

Two lists:
  * SWING: every active stock. Daily candles only. Since 2026-11-23 this is the NIFTY 500
    above a floor on the value traded per day, so thin stocks, whose backtest fills could
    never be had in real life, stay out.
  * INTRADAY: the stocks with `Stock.intraday` set. 5- and 15-minute candles are fetched
    for these only, and intraday strategies are tested and may trade here only. Intraday
    is decided by costs against the size of the move, so the list is the most liquid
    stocks that move the most in a day.

Both are chosen from measurements of the stored daily candles (`measure`), not by hand.
`tools/universe.py` is the command-line front end.
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import text

from strategies import STRATEGY_HOLD_DURATIONS

MEASURE_DAYS = 60
INTRADAY_TIMEFRAMES = ["15m", "5m"]


def is_intraday_strategy(strategy_name: str) -> bool:
    return STRATEGY_HOLD_DURATIONS.get(strategy_name) == "INTRADAY"


def stocks_for(conn, strategy_name: str | None = None) -> list[tuple[int, str]]:
    """(id, symbol) of the stocks a strategy is tested on: active stocks, and for an
    intraday strategy only those on the intraday list. No strategy: every active stock."""
    only_intraday = strategy_name is not None and is_intraday_strategy(strategy_name)
    rows = conn.execute(text(
        'SELECT id, symbol, intraday FROM "Stock" WHERE "isActive" ORDER BY symbol'
    )).fetchall()
    return [(r[0], r[1]) for r in rows if r[2] or not only_intraday]


def active_stocks(conn) -> list[tuple[int, str, bool]]:
    """(id, symbol, on the intraday list) for every active stock."""
    rows = conn.execute(text('SELECT id, symbol, intraday FROM "Stock" WHERE "isActive" ORDER BY symbol')).fetchall()
    return [(r[0], r[1], bool(r[2])) for r in rows]


def timeframes_for(on_intraday_list: bool, wanted: list[str]) -> list[str]:
    """The timeframes to fetch for a stock: daily for all, intraday only for the list."""
    return [tf for tf in wanted if tf == "1D" or on_intraday_list]


def figures(daily: pd.DataFrame, days: int = MEASURE_DAYS) -> dict | None:
    """Liquidity and movement of one stock from its daily candles (Open/High/Low/Close/
    Volume), over the last `days` sessions. None when there is too little history.

    traded_value_cr: median of close x volume per day, in crore rupees. The median, so
        one freak day does not make a thin stock look liquid.
    day_range_pct: median of (high - low) / close, in percent: how far it moves in a day.
    """
    recent = daily.tail(days)
    recent = recent[(recent["Close"] > 0) & (recent["Volume"] >= 0)]
    if len(recent) < max(20, days // 2):
        return None
    value = (recent["Close"] * recent["Volume"]).median() / 1e7
    day_range = ((recent["High"] - recent["Low"]) / recent["Close"]).median() * 100
    return {
        "traded_value_cr": round(float(value), 2),
        "day_range_pct": round(float(day_range), 2),
        "last_close": round(float(recent["Close"].iloc[-1]), 2),
    }


def pick_intraday(rows: list[dict], top: int, min_value_cr: float, min_price: float, max_price: float) -> list[dict]:
    """The intraday list: among stocks liquid enough and priced inside the band, the `top`
    that move the most in a day. rows: [{symbol, traded_value_cr, day_range_pct, last_close}].

    Why a price band: under about Rs 50 one tick (Rs 0.05) is a large slice of a tight
    stop; above the ceiling one share can already break the risk limit.
    """
    ok = [
        r for r in rows
        if r.get("traded_value_cr") is not None and r.get("day_range_pct") is not None
        and r["traded_value_cr"] >= min_value_cr and min_price <= r["last_close"] <= max_price
    ]
    return sorted(ok, key=lambda r: (-r["day_range_pct"], r["symbol"]))[:top]
