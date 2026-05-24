"""FastAPI main application for the trading engine."""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from routers.history import router as history_router
from routers.backtest import router as backtest_router
from routers.analysis import router as analysis_router

load_dotenv()

app = FastAPI(
    title="Smart Trading Engine",
    description="Python backtesting and live data engine for the Smart Trading platform",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(history_router, prefix="/api/engine", tags=["history"])
app.include_router(backtest_router, prefix="/api/engine", tags=["backtest"])
app.include_router(analysis_router, prefix="/api/engine/analysis", tags=["analysis"])


@app.get("/health")
def health():
    return {"status": "ok", "service": "trading-engine"}


@app.get("/api/engine/strategies")
def list_strategies():
    from strategies import STRATEGY_REGISTRY, STRATEGY_TIMEFRAMES
    return [
        {"name": name, "timeframe": STRATEGY_TIMEFRAMES[name]}
        for name in STRATEGY_REGISTRY.keys()
    ]
