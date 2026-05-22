"""POST /api/engine/run-backtest — Runs a strategy on historical data"""
import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from db.client import engine
from strategies import STRATEGY_REGISTRY

router = APIRouter()


class BacktestRequest(BaseModel):
    symbol: str
    strategy: str
    timeframe: str


def get_stock_id(symbol: str) -> int:
    with engine.connect() as conn:
        result = conn.execute(
            text('SELECT id FROM "Stock" WHERE symbol = :sym'),
            {"sym": symbol.upper()}
        ).fetchone()
        if not result:
            raise HTTPException(status_code=404, detail=f"Stock {symbol} not found")
        return result[0]


def load_historical(stock_id: int, timeframe: str) -> pd.DataFrame:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT timestamp, open, high, low, close, volume
            FROM "HistoricalData"
            WHERE "stockId" = :sid AND timeframe = :tf
            ORDER BY timestamp ASC
        """), {"sid": stock_id, "tf": timeframe}).fetchall()

    if not rows:
        raise HTTPException(
            status_code=400,
            detail=f"No historical data for timeframe {timeframe}. Run fetch-history first."
        )

    df = pd.DataFrame(rows, columns=['timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.set_index('timestamp')
    return df


def save_report(stock_id: int, strategy_name: str, timeframe: str, metrics: dict):
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO "BacktestReport"
              ("stockId", "strategyName", "timeframe", "winRate", "totalTrades", "maxDrawdown", "expectancy", "createdAt")
            VALUES (:sid, :sn, :tf, :wr, :tt, :md, :ex, NOW())
        """), {
            "sid": stock_id, "sn": strategy_name, "tf": timeframe,
            "wr": float(metrics['winRate']), "tt": int(metrics['totalTrades']),
            "md": float(metrics['maxDrawdown']), "ex": float(metrics['expectancy'])
        })
        conn.commit()


@router.post("/run-backtest")
def run_backtest(req: BacktestRequest):
    symbol = req.symbol.upper()

    if req.strategy not in STRATEGY_REGISTRY:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown strategy '{req.strategy}'. Available: {list(STRATEGY_REGISTRY.keys())}"
        )

    stock_id = get_stock_id(symbol)
    strategy = STRATEGY_REGISTRY[req.strategy]

    df = load_historical(stock_id, req.timeframe)

    if len(df) < 30:
        raise HTTPException(status_code=400, detail="Insufficient data (< 30 bars) for backtest")

    metrics = strategy.run_backtest(df)
    save_report(stock_id, req.strategy, req.timeframe, metrics)

    return {
        "symbol": symbol,
        "strategy": req.strategy,
        "timeframe": req.timeframe,
        "metrics": metrics,
    }
