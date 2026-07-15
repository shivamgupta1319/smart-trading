"""POST /api/engine/custom-backtest — backtest a user-built rule spec."""
import yfinance as yf
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any
from sqlalchemy import text

from strategies.custom import CustomRuleStrategy
from routers.backtest import load_historical
from routers.history import TIMEFRAME_CONFIG, upsert_ohlcv
from db.client import engine

router = APIRouter()


MIN_BARS = 60


def ensure_stock_loaded(symbol: str, timeframe: str) -> int:
    """Return the Stock id for `symbol`, transparently creating the row and
    downloading its OHLCV from yfinance if it isn't loaded yet. Lets the
    Strategy Builder backtest any searchable NSE stock without a manual
    'add stock' step first."""
    symbol = symbol.upper()
    if timeframe not in TIMEFRAME_CONFIG:
        raise HTTPException(status_code=400, detail=f"Unsupported timeframe {timeframe}")

    # Find-or-create the Stock row (idempotent under concurrent runs).
    with engine.begin() as conn:
        row = conn.execute(
            text('SELECT id FROM "Stock" WHERE symbol = :s'), {"s": symbol}
        ).fetchone()
        if row:
            stock_id = row[0]
        else:
            stock_id = conn.execute(
                text(
                    'INSERT INTO "Stock" (symbol) VALUES (:s) '
                    'ON CONFLICT (symbol) DO UPDATE SET symbol = EXCLUDED.symbol '
                    'RETURNING id'
                ),
                {"s": symbol},
            ).scalar()

    # Only fetch if we don't already have enough candles for this timeframe.
    with engine.connect() as conn:
        bars = conn.execute(
            text('SELECT COUNT(*) FROM "HistoricalData" WHERE "stockId" = :id AND "timeframe" = :tf'),
            {"id": stock_id, "tf": timeframe},
        ).scalar() or 0

    if bars < MIN_BARS:
        cfg = TIMEFRAME_CONFIG[timeframe]
        yf_sym = symbol if symbol.endswith(".NS") else symbol + ".NS"
        try:
            df = yf.Ticker(yf_sym).history(period=cfg["period"], interval=cfg["interval"])
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Failed to download data for {symbol}: {e}")
        if df.empty:
            raise HTTPException(
                status_code=404,
                detail=f"No market data found for {symbol} on Yahoo Finance — check the symbol.",
            )
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
        upsert_ohlcv(stock_id, df, timeframe)

    return stock_id


class CustomBacktestRequest(BaseModel):
    symbol: str
    spec: dict[str, Any]
    timeframe: str | None = None


@router.post("/custom-backtest")
def custom_backtest(req: CustomBacktestRequest):
    try:
        strategy = CustomRuleStrategy(req.spec)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    timeframe = req.timeframe or strategy.timeframe
    stock_id = ensure_stock_loaded(req.symbol, timeframe)
    df = load_historical(stock_id, timeframe)
    if len(df) < MIN_BARS:
        raise HTTPException(status_code=400, detail="Need >= 60 bars to backtest")

    try:
        metrics = strategy.run_backtest(df)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Backtest failed: {e}")

    return {
        "symbol": req.symbol.upper(),
        "name": strategy.name,
        "timeframe": timeframe,
        "metrics": metrics,
    }
