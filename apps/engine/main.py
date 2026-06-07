"""FastAPI main application for the trading engine."""
import os
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from auth import require_api_key, llm_rate_limiter
from routers.history import router as history_router
from routers.backtest import router as backtest_router
from routers.advanced_backtest import router as advanced_backtest_router
from routers.custom_strategy import router as custom_strategy_router
from routers.broker import router as broker_router
from routers.regime import router as regime_router
from routers.analysis import router as analysis_router

load_dotenv()

app = FastAPI(
    title="Smart Trading Engine",
    description="Python backtesting and live data engine for the Smart Trading platform",
    version="1.0.0",
)

_cors_origins = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# All engine routers require the shared API key (no-op when API_KEY is unset).
app.include_router(
    history_router, prefix="/api/engine", tags=["history"],
    dependencies=[Depends(require_api_key)],
)
app.include_router(
    backtest_router, prefix="/api/engine", tags=["backtest"],
    dependencies=[Depends(require_api_key)],
)
app.include_router(
    advanced_backtest_router, prefix="/api/engine", tags=["advanced-backtest"],
    dependencies=[Depends(require_api_key)],
)
app.include_router(
    custom_strategy_router, prefix="/api/engine", tags=["custom-strategy"],
    dependencies=[Depends(require_api_key)],
)
app.include_router(
    broker_router, prefix="/api/engine/broker", tags=["broker"],
    dependencies=[Depends(require_api_key)],
)
app.include_router(
    regime_router, prefix="/api/engine", tags=["regime"],
    dependencies=[Depends(require_api_key)],
)
# Analysis hits paid LLMs — also rate-limited per IP.
app.include_router(
    analysis_router, prefix="/api/engine/analysis", tags=["analysis"],
    dependencies=[Depends(require_api_key), Depends(llm_rate_limiter)],
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "trading-engine"}


@app.get("/api/engine/strategies")
def list_strategies():
    from strategies import STRATEGY_REGISTRY, STRATEGY_TIMEFRAMES, STRATEGY_HOLD_DURATIONS
    return [
        {
            "name": name,
            "timeframe": STRATEGY_TIMEFRAMES[name],
            "holdDuration": STRATEGY_HOLD_DURATIONS.get(name, "UNKNOWN"),
        }
        for name in STRATEGY_REGISTRY.keys()
    ]

