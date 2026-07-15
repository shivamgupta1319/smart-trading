"""Broker data-source status + helpers.

Dhan needs no OAuth — just DHAN_ACCESS_TOKEN + DHAN_CLIENT_ID in the engine env.
The /status endpoint confirms what the engine will actually use. The Upstox
helpers exist only if you switch BROKER=upstox (it uses a daily OAuth token).
"""
from fastapi import APIRouter
from pydantic import BaseModel

import brokers
from brokers import dhan, upstox

router = APIRouter()


@router.get("/status")
def status():
    return {
        "broker": brokers._broker_name(),
        "dataSource": brokers.active_source(),
        "dhanConfigured": dhan.is_configured(),
        "upstoxConfigured": upstox.is_configured(),
        "dhanToken": dhan.token_status(),
        # Dhan historical needs the PAID Data API; we keep historical on free
        # yfinance and use Dhan only for (free) live quotes.
        "liveSource": brokers.active_source(),
        "historicalSource": "yfinance (Dhan historical requires paid Data API)",
    }


class DhanToken(BaseModel):
    token: str


@router.post("/dhan/token")
def set_dhan_token(body: DhanToken):
    """Refresh the daily Dhan access token WITHOUT restarting the container."""
    dhan.save_token(body.token)
    return {"ok": True, "tokenStatus": dhan.token_status(), "dataSource": brokers.active_source()}


@router.get("/probe/{symbol}")
def probe(symbol: str):
    """Quick check that the active source returns a live price for a symbol."""
    return {"symbol": symbol.upper(), "source": brokers.active_source(),
            "quote": brokers.get_live_price(symbol)}


# ── Upstox-only OAuth helpers (ignored when BROKER=dhan) ───────────────────
class UpstoxCode(BaseModel):
    code: str


@router.get("/upstox/login-url")
def upstox_login_url():
    return {"loginUrl": upstox.login_url()}


@router.post("/upstox/token")
def upstox_token(body: UpstoxCode):
    """Exchange an Upstox auth code for an access token (set it as UPSTOX_ACCESS_TOKEN)."""
    return upstox.exchange_code(body.code)
