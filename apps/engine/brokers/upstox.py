"""Upstox (free) market-data client for paper trading.

Paper trading in SmartTrader = SmartTrader's own *simulated* fills (the Trade
ledger + the realistic fill/cost model) driven by *real* market data. Upstox
supplies that real data for free; no real orders are ever placed here.

Auth is Upstox OAuth2 (daily token, expires ~03:30 IST next day):
  1. Open the login URL (login_url()), authorize, copy the `code` from the redirect.
  2. Exchange it for an access token (exchange_code()) and store it as
     UPSTOX_ACCESS_TOKEN in the engine env.

Endpoint shapes follow Upstox API v2 (quotes) / v3 (historical). Field names can
change — see docs/upstox-paper-trading.md and verify against current Upstox docs.
"""
from __future__ import annotations
import gzip
import io
import json
import os
from datetime import datetime, timedelta
from typing import Optional

import httpx
import pandas as pd

from cache import cache_get, cache_set

API = "https://api.upstox.com"
# Upstox publishes instrument masters here; NSE-only keeps the download small.
INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
INSTRUMENTS_TTL = 12 * 3600  # refresh twice a day


def _env(name: str) -> str:
    return os.getenv(name, "")


def is_configured() -> bool:
    """True only when an access token is present — otherwise callers fall back."""
    return bool(_env("UPSTOX_ACCESS_TOKEN"))


def _auth_headers() -> dict:
    return {
        "Authorization": f"Bearer {_env('UPSTOX_ACCESS_TOKEN')}",
        "Accept": "application/json",
    }


# ── OAuth helpers ──────────────────────────────────────────────────────────
def login_url(state: str = "smarttrader") -> str:
    return (
        f"{API}/v2/login/authorization/dialog?response_type=code"
        f"&client_id={_env('UPSTOX_API_KEY')}"
        f"&redirect_uri={_env('UPSTOX_REDIRECT_URI')}"
        f"&state={state}"
    )


def exchange_code(code: str) -> dict:
    """Exchange an authorization `code` for an access token (valid for the day)."""
    resp = httpx.post(
        f"{API}/v2/login/authorization/token",
        data={
            "code": code,
            "client_id": _env("UPSTOX_API_KEY"),
            "client_secret": _env("UPSTOX_API_SECRET"),
            "redirect_uri": _env("UPSTOX_REDIRECT_URI"),
            "grant_type": "authorization_code",
        },
        headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


# ── Instrument key resolution (symbol -> NSE_EQ|ISIN) ──────────────────────
def _instrument_map() -> dict:
    cached = cache_get("upstox:instruments", INSTRUMENTS_TTL)
    if cached is not None:
        return cached
    mapping: dict[str, str] = {}
    try:
        r = httpx.get(INSTRUMENTS_URL, timeout=30)
        r.raise_for_status()
        raw = gzip.GzipFile(fileobj=io.BytesIO(r.content)).read()
        for row in json.loads(raw):
            # Equity cash segment only.
            if row.get("segment") == "NSE_EQ" and row.get("instrument_type") == "EQ":
                ts = row.get("trading_symbol") or row.get("tradingsymbol")
                key = row.get("instrument_key")
                if ts and key:
                    mapping[ts.upper()] = key
    except Exception as e:  # pragma: no cover - network dependent
        print(f"[upstox] instrument map download failed: {e}")
    cache_set("upstox:instruments", mapping)
    return mapping


def instrument_key(symbol: str) -> Optional[str]:
    return _instrument_map().get(symbol.upper().replace(".NS", ""))


# ── Live quote ─────────────────────────────────────────────────────────────
def get_live_price(symbol: str) -> Optional[dict]:
    """Return {price, change, change_pct} for one NSE symbol, or None."""
    key = instrument_key(symbol)
    if not key:
        return None
    try:
        r = httpx.get(
            f"{API}/v2/market-quote/quotes",
            params={"instrument_key": key},
            headers=_auth_headers(),
            timeout=10,
        )
        r.raise_for_status()
        data = r.json().get("data", {})
        # Response is keyed like "NSE_EQ:RELIANCE"; take the only entry.
        if not data:
            return None
        q = next(iter(data.values()))
        last = q.get("last_price")
        if last is None:
            return None
        net_change = q.get("net_change", 0) or 0
        prev = last - net_change
        change_pct = (net_change / prev * 100) if prev else 0
        return {"price": round(last, 2), "change": round(net_change, 2), "change_pct": round(change_pct, 2)}
    except Exception as e:
        print(f"[upstox] live price failed for {symbol}: {e}")
        return None


# ── Historical candles ─────────────────────────────────────────────────────
_TF_TO_UNIT = {
    "1D": ("days", 1, 1825),    # ~5y
    "15m": ("minutes", 15, 60),
    "5m": ("minutes", 5, 60),
}


def get_historical(symbol: str, timeframe: str) -> pd.DataFrame:
    """Return an OHLCV DataFrame (IST-naive index) for one symbol, or empty."""
    key = instrument_key(symbol)
    if not key or timeframe not in _TF_TO_UNIT:
        return pd.DataFrame()
    unit, interval, lookback_days = _TF_TO_UNIT[timeframe]
    to_date = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    try:
        r = httpx.get(
            f"{API}/v3/historical-candle/{key}/{unit}/{interval}/{to_date}/{from_date}",
            headers=_auth_headers(),
            timeout=30,
        )
        r.raise_for_status()
        candles = r.json().get("data", {}).get("candles", [])
        if not candles:
            return pd.DataFrame()
        # Upstox candle: [timestamp, open, high, low, close, volume, oi]
        df = pd.DataFrame(candles, columns=["ts", "Open", "High", "Low", "Close", "Volume", "OI"])
        idx = pd.to_datetime(df["ts"])
        if idx.dt.tz is not None:
            idx = idx.dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
        df.index = idx
        df = df[["Open", "High", "Low", "Close", "Volume"]].sort_index()
        return df
    except Exception as e:
        print(f"[upstox] historical failed for {symbol}: {e}")
        return pd.DataFrame()
