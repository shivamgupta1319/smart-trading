"""POST /api/engine/fetch-history — Downloads OHLCV from yfinance and stores in PostgreSQL"""
import time
import pandas as pd
import yfinance as yf
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from sqlalchemy import text
from db.client import engine

router = APIRouter()

TIMEFRAME_CONFIG = {
    "1D": {"period": "5y", "interval": "1d"},
    "15m": {"period": "60d", "interval": "15m"},
    "5m": {"period": "60d", "interval": "5m"},
}


class FetchHistoryRequest(BaseModel):
    symbol: str
    timeframes: List[str] = ["1D", "15m", "5m"]


def get_stock_id(symbol: str) -> int:
    with engine.connect() as conn:
        result = conn.execute(
            text('SELECT id FROM "Stock" WHERE symbol = :sym'),
            {"sym": symbol.upper()}
        ).fetchone()
        if not result:
            raise HTTPException(status_code=404, detail=f"Stock {symbol} not found in DB. Add it first.")
        return result[0]


def upsert_ohlcv(stock_id: int, df: pd.DataFrame, timeframe: str):
    if df.empty:
        return 0

    rows = 0
    with engine.connect() as conn:
        for ts, row in df.iterrows():
            ts_str = pd.Timestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
            conn.execute(text("""
                INSERT INTO "HistoricalData" ("stockId", "timestamp", "open", "high", "low", "close", "volume", "timeframe")
                VALUES (:sid, :ts, :o, :h, :l, :c, :v, :tf)
                ON CONFLICT ("stockId", "timestamp", "timeframe") DO UPDATE
                SET open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
                    close=EXCLUDED.close, volume=EXCLUDED.volume
            """), {
                "sid": stock_id, "ts": ts_str,
                "o": float(row['Open']), "h": float(row['High']),
                "l": float(row['Low']), "c": float(row['Close']),
                "v": float(row.get('Volume', 0)), "tf": timeframe
            })
            rows += 1
        conn.commit()
    return rows


@router.post("/fetch-history")
def fetch_history(req: FetchHistoryRequest):
    original_symbol = req.symbol.upper()
    stock_id = get_stock_id(original_symbol)
    
    # Prepare symbol for Yahoo Finance
    yf_symbol = original_symbol
    if not yf_symbol.endswith(".NS"):
        yf_symbol = yf_symbol + ".NS"


    results = {}
    ticker = yf.Ticker(yf_symbol)

    for tf in req.timeframes:
        if tf not in TIMEFRAME_CONFIG:
            continue
        cfg = TIMEFRAME_CONFIG[tf]
        try:
            df = ticker.history(period=cfg["period"], interval=cfg["interval"])
            if df.empty:
                results[tf] = {"rows": 0, "status": "empty"}
                continue
            df = df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()
            rows = upsert_ohlcv(stock_id, df, tf)
            results[tf] = {"rows": rows, "status": "ok"}
        except Exception as e:
            results[tf] = {"rows": 0, "status": f"error: {str(e)}"}
        time.sleep(1)  # Rate limit friendly

    return {"symbol": original_symbol, "results": results}

class LivePriceRequest(BaseModel):
    symbols: List[str]

@router.post("/live-prices")
def get_live_prices(req: LivePriceRequest):
    results = {}
    for sym in req.symbols:
        yf_sym = sym if sym.endswith(".NS") else sym + ".NS"
        try:
            ticker = yf.Ticker(yf_sym)
            info = ticker.fast_info
            last_price = info.last_price
            prev_close = info.previous_close
            change = last_price - prev_close if prev_close else 0
            change_pct = (change / prev_close * 100) if prev_close else 0
            
            results[sym] = {
                "price": round(last_price, 2),
                "change": round(change, 2),
                "change_pct": round(change_pct, 2)
            }
        except Exception:
            results[sym] = None
    return results
