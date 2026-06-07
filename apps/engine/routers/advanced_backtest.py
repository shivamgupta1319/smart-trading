"""Advanced backtesting: walk-forward (out-of-sample) + Monte-Carlo.

These directly address the #1 review finding — "you can't trust a single
in-sample ROI." Walk-forward shows whether a strategy holds up across rolling
out-of-sample windows; Monte-Carlo bootstraps the trade sequence to show the
*distribution* of outcomes (drawdown / ROI percentiles) instead of one number.
"""
import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from db.client import engine
from strategies import STRATEGY_REGISTRY
from backtest_config import RISK
from routers.backtest import get_stock_id, load_historical

router = APIRouter()


@router.get("/leaderboard")
def leaderboard():
    """Rank strategies by a RISK-ADJUSTED score across all saved backtest reports,
    instead of raw ROI. Score ≈ avg ROI / avg max-drawdown% (a Calmar-like ratio)
    weighted down when the sample is tiny."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT "strategyName" AS s,
                   count(*) AS reports,
                   avg("winRate") AS avg_win,
                   avg("roiPercentage") AS avg_roi,
                   avg("maxDrawdown") AS avg_dd,
                   avg("totalTrades") AS avg_trades,
                   sum("netProfit") AS total_net
            FROM "BacktestReport"
            GROUP BY "strategyName"
        """)).fetchall()

    out = []
    initial = RISK.initial_capital
    for r in rows:
        avg_roi = float(r.avg_roi or 0)
        avg_dd_pct = float(r.avg_dd or 0) / initial * 100
        reports = int(r.reports)
        # Calmar-like, divide-by-zero safe; shrink toward 0 for tiny samples.
        calmar = avg_roi / avg_dd_pct if avg_dd_pct > 0.1 else avg_roi
        confidence = min(1.0, reports / 10.0)
        out.append({
            "strategy": r.s,
            "reports": reports,
            "avgWinRate": round(float(r.avg_win or 0), 2),
            "avgRoi": round(avg_roi, 2),
            "avgMaxDrawdownPct": round(avg_dd_pct, 2),
            "avgTrades": round(float(r.avg_trades or 0), 1),
            "totalNetProfit": round(float(r.total_net or 0), 2),
            "riskAdjustedScore": round(calmar * confidence, 3),
        })

    out.sort(key=lambda x: x["riskAdjustedScore"], reverse=True)
    return {
        "leaderboard": out,
        "metric": "riskAdjustedScore = (avg ROI / avg max-drawdown%) × sample-confidence",
        "disclaimer": "In-sample aggregate of stored backtests. Validate a candidate with walk-forward before trusting it.",
    }


class WalkForwardRequest(BaseModel):
    symbol: str
    strategy: str
    timeframe: str
    folds: int = 5


class MonteCarloRequest(BaseModel):
    symbol: str
    strategy: str
    timeframe: str
    iterations: int = 1000


def _resolve(strategy_name: str, symbol: str, timeframe: str):
    if strategy_name not in STRATEGY_REGISTRY:
        raise HTTPException(status_code=400, detail=f"Unknown strategy '{strategy_name}'")
    stock_id = get_stock_id(symbol.upper())
    strategy = STRATEGY_REGISTRY[strategy_name]
    df = load_historical(stock_id, timeframe)
    if len(df) < 60:
        raise HTTPException(status_code=400, detail="Need >= 60 bars for advanced backtests")
    return strategy, df


@router.post("/run-walk-forward")
def run_walk_forward(req: WalkForwardRequest):
    strategy, df = _resolve(req.strategy, req.symbol, req.timeframe)
    folds = max(2, min(req.folds, 12))
    n = len(df)
    size = n // folds

    fold_results = []
    for k in range(folds):
        start = k * size
        end = n if k == folds - 1 else (k + 1) * size
        window = df.iloc[start:end]
        if len(window) < 30:
            continue
        m = strategy.run_backtest(window)
        fold_results.append({
            "fold": k + 1,
            "bars": len(window),
            "trades": m["totalTrades"],
            "roiPercentage": m["roiPercentage"],
            "winRate": m["winRate"],
            "profitFactor": m["profitFactor"],
        })

    traded = [f for f in fold_results if f["trades"] > 0]
    rois = [f["roiPercentage"] for f in traded]
    profitable = [f for f in traded if f["roiPercentage"] > 0]
    aggregate = {
        "foldsEvaluated": len(fold_results),
        "foldsWithTrades": len(traded),
        "pctProfitableFolds": round(len(profitable) / len(traded) * 100, 2) if traded else 0.0,
        "meanOosRoi": round(float(np.mean(rois)), 2) if rois else 0.0,
        "stdOosRoi": round(float(np.std(rois)), 2) if rois else 0.0,
        # Consistency: low std relative to mean is good; flag erratic strategies.
        "consistent": bool(rois and np.mean(rois) > 0 and np.std(rois) <= abs(np.mean(rois))),
    }
    return {
        "symbol": req.symbol.upper(),
        "strategy": req.strategy,
        "timeframe": req.timeframe,
        "folds": fold_results,
        "aggregate": aggregate,
        "disclaimer": (
            "Out-of-sample rolling windows. A strategy that is only profitable "
            "in a few folds (low pctProfitableFolds) or has high stdOosRoi is "
            "likely overfit / regime-dependent — do not trust its in-sample ROI."
        ),
    }


@router.post("/run-monte-carlo")
def run_monte_carlo(req: MonteCarloRequest):
    strategy, df = _resolve(req.strategy, req.symbol, req.timeframe)
    sim = strategy.simulate(df)
    trades = np.array(sim["net_trades"], dtype=float)
    if trades.size < 5:
        raise HTTPException(status_code=400, detail="Need >= 5 trades to bootstrap a distribution")

    iters = max(100, min(req.iterations, 20000))
    capital = RISK.initial_capital
    # Deterministic seed so results are reproducible across calls.
    rng = np.random.default_rng(42)

    final_rois = np.empty(iters)
    max_dds = np.empty(iters)
    for it in range(iters):
        # Bootstrap: resample the trade outcomes WITH replacement, random order.
        seq = rng.choice(trades, size=trades.size, replace=True)
        equity = capital + np.cumsum(seq)
        running_peak = np.maximum.accumulate(np.concatenate([[capital], equity]))
        dd = running_peak[1:] - equity
        final_rois[it] = (equity[-1] - capital) / capital * 100
        max_dds[it] = dd.max() / capital * 100

    def pct(a, p):
        return round(float(np.percentile(a, p)), 2)

    return {
        "symbol": req.symbol.upper(),
        "strategy": req.strategy,
        "timeframe": req.timeframe,
        "tradesSampled": int(trades.size),
        "iterations": iters,
        "roi": {"p5": pct(final_rois, 5), "p50": pct(final_rois, 50), "p95": pct(final_rois, 95),
                "mean": round(float(final_rois.mean()), 2)},
        "maxDrawdownPct": {"p5": pct(max_dds, 5), "p50": pct(max_dds, 50), "p95": pct(max_dds, 95),
                           "worst": round(float(max_dds.max()), 2)},
        "probabilityOfProfit": round(float((final_rois > 0).mean() * 100), 2),
        "disclaimer": (
            "Bootstrapped distribution of outcomes from the historical trade set. "
            "The p5 ROI and p95 drawdown are realistic 'bad case' figures — size "
            "risk against those, not the median."
        ),
    }
