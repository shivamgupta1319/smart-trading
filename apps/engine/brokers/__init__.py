"""Market-data facade: route live prices + historical candles to the configured
source with automatic fallback to yfinance.

Env:
  * BROKER       — which broker client to use: `dhan` (default) or `upstox`
  * DATA_SOURCE  — `auto` (default: broker if configured, else yfinance),
                   `broker` (force broker, fall back only on hard failure),
                   or `yfinance` (original behaviour)
"""
from __future__ import annotations
import os
from typing import Optional

import pandas as pd

from . import dhan, upstox

_CLIENTS = {"dhan": dhan, "upstox": upstox}


def _broker_name() -> str:
    return os.getenv("BROKER", "dhan").lower()


def _client():
    return _CLIENTS.get(_broker_name(), dhan)


def _mode() -> str:
    return os.getenv("DATA_SOURCE", "auto").lower()


def active_source() -> str:
    """Which source will actually be used (for diagnostics / the status endpoint)."""
    if _mode() == "yfinance":
        return "yfinance"
    return _broker_name() if _client().is_configured() else "yfinance"


def _use_broker() -> bool:
    return _mode() in ("auto", "broker") and _client().is_configured()


def get_live_price(symbol: str) -> Optional[dict]:
    """{price, change, change_pct} from the broker if available, else yfinance."""
    if _use_broker():
        q = _client().get_live_price(symbol)
        if q is not None:
            return q
        if _mode() == "broker":
            return None  # forced broker, no silent yfinance fallback
    return _yf_live(symbol)


def get_historical(symbol: str, timeframe: str) -> pd.DataFrame:
    """OHLCV DataFrame (IST-naive index) from the broker if available, else yfinance."""
    if _use_broker():
        df = _client().get_historical(symbol, timeframe)
        if not df.empty:
            return df
        if _mode() == "broker":
            return df
    return _yf_historical(symbol, timeframe)


# ── yfinance fallback ──────────────────────────────────────────────────────
def _yf_live(symbol: str) -> Optional[dict]:
    import yfinance as yf

    yf_sym = symbol if symbol.endswith(".NS") else symbol + ".NS"
    try:
        info = yf.Ticker(yf_sym).fast_info
        last = info.last_price
        prev = info.previous_close
        change = last - prev if prev else 0
        change_pct = (change / prev * 100) if prev else 0
        return {"price": round(last, 2), "change": round(change, 2), "change_pct": round(change_pct, 2)}
    except Exception:
        return None


def _yf_historical(symbol: str, timeframe: str) -> pd.DataFrame:
    import yfinance as yf

    from routers.history import TIMEFRAME_CONFIG, normalize_to_ist_naive

    cfg = TIMEFRAME_CONFIG.get(timeframe)
    if not cfg:
        return pd.DataFrame()
    yf_sym = symbol if symbol.endswith(".NS") else symbol + ".NS"
    try:
        df = yf.Ticker(yf_sym).history(period=cfg["period"], interval=cfg["interval"])
        if df.empty:
            return df
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
        return normalize_to_ist_naive(df)
    except Exception:
        return pd.DataFrame()
