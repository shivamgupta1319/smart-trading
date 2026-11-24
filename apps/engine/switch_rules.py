"""Switching by market condition: which strategies are worth running in which market.

Every trade carries the market's condition when it was opened (market_condition.py). This
module turns that into a rule table, from the backtest:

  1. `regime_series` labels every past day with the NIFTY regime it would have had that
     day, with the same thresholds as the live classifier (routers/regime.py), using only
     data up to that day.
  2. Every backtest trade is put in the bucket of the regime on the day BEFORE its entry
     (what was known when the trade was taken).
  3. For each strategy and regime: the number of trades and the average R. A strategy is
     switched OFF in a regime when it has enough trades there (MIN_TRADES) and still loses
     on average. With too few trades there is no evidence either way and it stays on.

Nothing is blocked by this table. The API stamps each new trade with what the table says
(`Trade.switchApproved`), and the Portfolio shows the "switch-approved" book beside all
trades. The switch earns control only if its book does better in live paper trading.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pandas_ta as ta

REGIMES = ["TRENDING_UP", "TRENDING_DOWN", "RANGING", "VOLATILE"]
MIN_TRADES = 50          # trades a strategy needs in a regime before it can be switched off there
OFF_BELOW_AVG_R = 0.0    # switched off when the average there is at or below this


def regime_series(df: pd.DataFrame) -> pd.Series:
    """The regime label of every day in `df` (NIFTY daily candles), each from data up to
    that day only. Same rules as `routers.regime._classify`; days with too little history
    are left out."""
    close = df["Close"]
    adx_df = ta.adx(df["High"], df["Low"], close, length=14)
    atr = ta.atr(df["High"], df["Low"], close, length=14)
    ema50 = ta.ema(close, length=50)
    ema200 = ta.ema(close, length=200).fillna(close)
    adx, dmp, dmn = adx_df["ADX_14"], adx_df["DMP_14"], adx_df["DMN_14"]
    atr_pct = atr / close * 100
    # "High for its own recent year": the 85th percentile of the last 252 sessions.
    atr_hi = atr_pct.rolling(252, min_periods=21).quantile(0.85)

    volatile = (atr_pct >= 3.0) | ((atr_pct >= atr_hi) & (atr_pct >= 1.5))
    up = (dmp >= dmn) & (close >= ema50)
    out = pd.Series(index=df.index, dtype=object)
    out[:] = "RANGING"
    lean_up = (adx >= 20) & (adx < 25) & (close > ema50) & (ema50 > ema200)
    out[lean_up] = "TRENDING_UP"
    out[(adx >= 25) & up] = "TRENDING_UP"
    out[(adx >= 25) & ~up] = "TRENDING_DOWN"
    out[volatile] = "VOLATILE"
    ready = adx.notna() & atr_pct.notna() & ema50.notna()
    return out[ready]


def regime_on_entry(regimes: pd.Series, entry_ts) -> str | None:
    """The regime known when a trade was entered: the label of the last session before the
    entry's calendar day."""
    day = pd.Timestamp(entry_ts).normalize()
    idx = regimes.index
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    pos = idx.normalize().searchsorted(day, side="left") - 1
    return None if pos < 0 else str(regimes.iloc[pos])


def build_rules(trades_by_strategy: dict[str, list[tuple[object, float]]], regimes: pd.Series) -> list[dict]:
    """One row per strategy and regime: {strategy, regime, trades, avgR, approved}.

    trades_by_strategy: {strategy: [(entry timestamp, R of the trade), ...]}.
    approved is False only with at least MIN_TRADES there and an average at or below
    OFF_BELOW_AVG_R; True with enough trades and a positive average; None (no evidence,
    treated as on) with fewer trades.
    """
    rows = []
    for strategy, trades in trades_by_strategy.items():
        buckets: dict[str, list[float]] = {r: [] for r in REGIMES}
        for entry_ts, r in trades:
            label = regime_on_entry(regimes, entry_ts)
            if label in buckets:
                buckets[label].append(float(r))
        for regime in REGIMES:
            rs = buckets[regime]
            avg = float(np.mean(rs)) if rs else None
            approved = None if len(rs) < MIN_TRADES else bool(avg > OFF_BELOW_AVG_R)
            rows.append({"strategy": strategy, "regime": regime, "trades": len(rs),
                         "avgR": None if avg is None else round(avg, 3), "approved": approved})
    return rows


def nifty_history() -> pd.DataFrame:
    """About eight years of NIFTY 50 daily candles (naive timestamps)."""
    import yfinance as yf

    df = yf.Ticker("^NSEI").history(period="8y", interval="1d")[["Open", "High", "Low", "Close", "Volume"]].dropna()
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    return df


def store(conn, rules: list[dict]) -> None:
    """Replace the stored rule table with `rules` (one transaction; the caller owns it)."""
    from sqlalchemy import text

    conn.execute(text('DELETE FROM "SwitchRule"'))
    for r in rules:
        conn.execute(text(
            'INSERT INTO "SwitchRule" ("strategyName", regime, trades, "avgR", approved, "updatedAt") '
            'VALUES (:s, :g, :n, :a, :ok, now())'
        ), {"s": r["strategy"], "g": r["regime"], "n": r["trades"], "a": r["avgR"], "ok": r["approved"]})


def latest() -> dict:
    """The stored rule table, grouped by strategy, for the API and the page."""
    from sqlalchemy import text
    from db.client import engine
    from strategies import STRATEGY_HOLD_DURATIONS

    with engine.connect() as conn:
        found = conn.execute(text(
            'SELECT "strategyName", regime, trades, "avgR", approved, "updatedAt" FROM "SwitchRule"'
        )).fetchall()
        roster = {r[0] for r in conn.execute(text('SELECT DISTINCT "strategyName" FROM "ActiveConfiguration"')).fetchall()}
    by: dict[str, dict] = {}
    for name, regime, trades, avg_r, approved, _ts in found:
        by.setdefault(name, {})[regime] = {"trades": trades, "avgR": avg_r, "approved": approved}
    updated = max((r[5] for r in found), default=None)
    strategies = [
        {"strategy": name, "bucket": STRATEGY_HOLD_DURATIONS.get(name), "onRoster": name in roster,
         "regimes": {g: cells.get(g, {"trades": 0, "avgR": None, "approved": None}) for g in REGIMES}}
        for name, cells in by.items()
    ]
    strategies.sort(key=lambda s: (not s["onRoster"], s["bucket"] == "INTRADAY", s["strategy"]))
    return {"regimes": REGIMES, "minTrades": MIN_TRADES, "updatedAt": updated.isoformat() + "Z" if updated else None,
            "strategies": strategies}
