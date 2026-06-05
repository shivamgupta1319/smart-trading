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
              ("stockId", "strategyName", "timeframe", "winRate", "totalTrades", "maxDrawdown", "netProfit", "roiPercentage", "createdAt")
            VALUES (:sid, :sn, :tf, :wr, :tt, :md, :np, :roi, NOW())
        """), {
            "sid": stock_id, "sn": strategy_name, "tf": timeframe,
            "wr": float(metrics['winRate']), "tt": int(metrics['totalTrades']),
            "md": float(metrics['maxDrawdown']), "np": float(metrics['netProfit']),
            "roi": float(metrics['roiPercentage'])
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


class RunAllStrategiesRequest(BaseModel):
    symbol: str

@router.post("/run-all-strategies")
def run_all_strategies(req: RunAllStrategiesRequest):
    symbol = req.symbol.upper()
    stock_id = get_stock_id(symbol)

    results = []

    # Iterate through all registered strategies
    for strategy_name, strategy in STRATEGY_REGISTRY.items():
        timeframe = getattr(strategy, 'timeframe', '1D') # fallback to 1D
        
        try:
            df = load_historical(stock_id, timeframe)
            if len(df) < 30:
                continue

            metrics = strategy.run_backtest(df)
            save_report(stock_id, strategy_name, timeframe, metrics)
            
            results.append({
                "strategy": strategy_name,
                "timeframe": timeframe,
                "metrics": metrics
            })
        except Exception as e:
            # Skip if no history for that timeframe or other error
            pass

    return {
        "symbol": symbol,
        "results": results
    }


class RunStrategyAllStocksRequest(BaseModel):
    strategy: str
    timeframe: str | None = None

@router.post("/run-strategy-all-stocks")
def run_strategy_all_stocks(req: RunStrategyAllStocksRequest):
    if req.strategy not in STRATEGY_REGISTRY:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown strategy '{req.strategy}'. Available: {list(STRATEGY_REGISTRY.keys())}"
        )

    strategy = STRATEGY_REGISTRY[req.strategy]
    timeframe = req.timeframe or getattr(strategy, 'timeframe', '1D')

    with engine.connect() as conn:
        stocks = conn.execute(text('SELECT id, symbol FROM "Stock"')).fetchall()

    results = []
    for stock_id, symbol in stocks:
        try:
            df = load_historical(stock_id, timeframe)
            if len(df) < 30:
                continue

            metrics = strategy.run_backtest(df)
            save_report(stock_id, req.strategy, timeframe, metrics)
            
            results.append({
                "symbol": symbol,
                "metrics": metrics
            })
        except Exception:
            pass

    # Sort results by roiPercentage descending
    results.sort(key=lambda x: x['metrics']['roiPercentage'], reverse=True)

    return {
        "strategy": req.strategy,
        "timeframe": timeframe,
        "results": results
    }
