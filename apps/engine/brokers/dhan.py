"""DhanHQ (free) market-data client for paper trading.

Paper trading in SmartTrader = SmartTrader's own *simulated* fills (the Trade
ledger + the realistic fill/cost model) driven by *real* market data. DhanHQ
supplies that real data for free; no real orders are placed here.

Auth is simple (no daily OAuth): generate an access token from the Dhan web app
(Profile → DhanHQ Trading APIs → Access Token) and note your Client ID. Put both
in the engine env:  DHAN_ACCESS_TOKEN, DHAN_CLIENT_ID.

Endpoint shapes follow DhanHQ API v2. Field names can change — see
docs/dhan-paper-trading.md and verify against current Dhan docs.
"""
from __future__ import annotations
import base64
import io
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import pandas as pd

from cache import cache_get, cache_set

API = "https://api.dhan.co/v2"
# Dhan instrument master (symbol -> numeric securityId).
SCRIP_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"
SCRIP_TTL = 12 * 3600
NSE_EQ = "NSE_EQ"
# Optional file that overrides DHAN_ACCESS_TOKEN. Because apps/engine is volume
# mounted, you can refresh the daily token here (or via POST /broker/dhan/token)
# WITHOUT restarting the container — _access_token() re-reads it on every call.
TOKEN_FILE = os.getenv("DHAN_TOKEN_FILE", "/app/.dhan_token")


def _env(name: str) -> str:
    return os.getenv(name, "")


def _access_token() -> str:
    try:
        if os.path.exists(TOKEN_FILE):
            tok = open(TOKEN_FILE).read().strip()
            if tok:
                return tok
    except Exception:
        pass
    return _env("DHAN_ACCESS_TOKEN")


def is_configured() -> bool:
    return bool(_access_token() and _env("DHAN_CLIENT_ID"))


def token_status() -> dict:
    """Decode the JWT `exp` (no signature check) so the 24h expiry is visible."""
    tok = _access_token()
    if not tok or tok.count(".") != 2:
        return {"present": bool(tok), "expiresAt": None, "expired": None, "hoursLeft": None}
    try:
        payload = tok.split(".")[1]
        payload += "=" * (-len(payload) % 4)  # pad base64url
        exp = json.loads(base64.urlsafe_b64decode(payload)).get("exp")
        if not exp:
            return {"present": True, "expiresAt": None, "expired": None, "hoursLeft": None}
        when = datetime.fromtimestamp(exp, tz=timezone.utc)
        left = (when - datetime.now(timezone.utc)).total_seconds()
        return {
            "present": True,
            "expiresAt": when.astimezone().isoformat(),
            "expired": left <= 0,
            "hoursLeft": round(left / 3600, 1),
        }
    except Exception:
        return {"present": True, "expiresAt": None, "expired": None, "hoursLeft": None}


def save_token(token: str) -> None:
    """Persist a new daily token to the token file (no container restart needed)."""
    with open(TOKEN_FILE, "w") as f:
        f.write(token.strip())


def _headers() -> dict:
    return {
        "access-token": _access_token(),
        "client-id": _env("DHAN_CLIENT_ID"),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ── Instrument resolution (symbol -> securityId) ───────────────────────────
def _scrip_map() -> dict:
    cached = cache_get("dhan:scrips", SCRIP_TTL)
    if cached is not None:
        return cached
    mapping: dict[str, str] = {}
    try:
        r = httpx.get(SCRIP_MASTER_URL, timeout=60)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text), low_memory=False)
        # NSE equity cash series only.
        exch = "SEM_EXM_EXCH_ID"
        seg = "SEM_SEGMENT"
        sym = "SEM_TRADING_SYMBOL"
        sid = "SEM_SMST_SECURITY_ID"
        series = "SEM_SERIES" if "SEM_SERIES" in df.columns else None
        mask = (df[exch] == "NSE") & (df[seg] == "E")
        if series:
            mask &= (df[series] == "EQ")
        for _, row in df[mask].iterrows():
            mapping[str(row[sym]).upper()] = str(int(row[sid]))
    except Exception as e:  # pragma: no cover - network dependent
        print(f"[dhan] scrip master download failed: {e}")
    cache_set("dhan:scrips", mapping)
    return mapping


def security_id(symbol: str) -> Optional[str]:
    return _scrip_map().get(symbol.upper().replace(".NS", ""))


# ── Live quote ─────────────────────────────────────────────────────────────
def get_live_price(symbol: str) -> Optional[dict]:
    sid = security_id(symbol)
    if not sid:
        return None
    try:
        r = httpx.post(
            f"{API}/marketfeed/quote",
            json={NSE_EQ: [int(sid)]},
            headers=_headers(),
            timeout=10,
        )
        r.raise_for_status()
        node = r.json().get("data", {}).get(NSE_EQ, {}).get(str(sid), {})
        last = node.get("last_price")
        if last is None:
            return None
        prev_close = (node.get("ohlc") or {}).get("close") or last
        change = last - prev_close
        change_pct = (change / prev_close * 100) if prev_close else 0
        return {"price": round(last, 2), "change": round(change, 2), "change_pct": round(change_pct, 2)}
    except Exception as e:
        print(f"[dhan] live price failed for {symbol}: {e}")
        return None


# ── Historical candles ─────────────────────────────────────────────────────
# timeframe -> (endpoint, interval_minutes|None, lookback_days)
_TF = {
    "1D": ("historical", None, 1825),
    "15m": ("intraday", "15", 60),
    "5m": ("intraday", "5", 60),
}


def get_historical(symbol: str, timeframe: str) -> pd.DataFrame:
    # Dhan historical candles require the PAID Data API (HTTP 451 otherwise), so
    # this is OFF by default — the facade falls back to free yfinance instantly,
    # avoiding a failing round-trip on every backtest. Flip the env to re-enable
    # if you subscribe to Dhan Data APIs.
    if os.getenv("DHAN_HISTORICAL_ENABLED", "false").lower() != "true":
        return pd.DataFrame()
    sid = security_id(symbol)
    if not sid or timeframe not in _TF:
        return pd.DataFrame()
    endpoint, interval, lookback = _TF[timeframe]
    to_date = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=lookback)).strftime("%Y-%m-%d")
    body = {
        "securityId": str(sid),
        "exchangeSegment": NSE_EQ,
        "instrument": "EQUITY",
        "fromDate": from_date,
        "toDate": to_date,
    }
    if interval:
        body["interval"] = interval
    else:
        body["expiryCode"] = 0
    try:
        r = httpx.post(f"{API}/charts/{endpoint}", json=body, headers=_headers(), timeout=30)
        r.raise_for_status()
        d = r.json()
        if not d.get("timestamp"):
            return pd.DataFrame()
        df = pd.DataFrame({
            "Open": d["open"], "High": d["high"], "Low": d["low"],
            "Close": d["close"], "Volume": d["volume"],
        })
        # Dhan timestamps are epoch seconds (UTC) -> IST-naive.
        idx = pd.to_datetime(d["timestamp"], unit="s", utc=True)
        df.index = idx.tz_convert("Asia/Kolkata").tz_localize(None)
        return df.sort_index()
    except Exception as e:
        print(f"[dhan] historical failed for {symbol}: {e}")
        return pd.DataFrame()
