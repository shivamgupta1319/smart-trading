"""Auto-select: pick the best (stock × strategy) cells and mark them active.

Strict / quality-first selection. For every strategy we backtest each stock that
has data, then put survivors through the SAME out-of-sample gauntlet the manual
"Validate" button uses — walk-forward consistency + a Monte-Carlo distribution —
before ranking on a risk-adjusted (Calmar-like) score and promoting the top N.

The picks are written straight into `ActiveConfiguration` (the table the live
scanner reads via get_active_configs), i.e. the same surface as the manual
`POST /api/configs/toggle` toggle.
"""
import os

import numpy as np
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from db.client import engine
from strategies import STRATEGY_REGISTRY, STRATEGY_TIMEFRAMES
from routers.backtest import load_historical

router = APIRouter()


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# Gate thresholds (all env-tunable). Tuned to "quality over coverage" — still
# reject losing / inconsistent cells, but don't demand a flawless edge that no
# real strategy clears. Raise these back up for a stricter selection.
MIN_TRADES = int(_f("AUTOSELECT_MIN_TRADES", 10))          # min sample size
MAX_DD_PCT = _f("AUTOSELECT_MAX_DD_PCT", 40.0)             # drawdown cap (% of slot)
MIN_PROFIT_FACTOR = _f("AUTOSELECT_MIN_PROFIT_FACTOR", 1.05)
MIN_ROI = _f("AUTOSELECT_MIN_ROI", 0.0)                    # in-sample ROI must be >0
MIN_PROFITABLE_FOLDS = _f("AUTOSELECT_MIN_PROFITABLE_FOLDS", 40.0)  # % of OOS folds
# Require the strict "low variance" consistency flag too (std <= |mean|)? Off by
# default — we still require mean OOS ROI > 0, just not low dispersion.
WF_REQUIRE_CONSISTENT = os.getenv("AUTOSELECT_WF_REQUIRE_CONSISTENT", "false").lower() == "true"
MC_MIN_PROB = _f("AUTOSELECT_MC_MIN_PROB", 55.0)           # % bootstrap paths profitable
WF_FOLDS = int(_f("AUTOSELECT_WF_FOLDS", 5))
MC_ITERS = int(_f("AUTOSELECT_MC_ITERS", 1000))
TOP_N = int(_f("AUTOSELECT_TOP_N", 3))
MIN_BARS = int(_f("AUTOSELECT_MIN_BARS", 60))


class AutoSelectRequest(BaseModel):
    strategies: list[str] | None = None  # default: all
    topN: int = TOP_N
    clearExisting: bool = True           # wipe ActiveConfiguration first
    dryRun: bool = False                 # compute but don't write


def _walk_forward(strategy, df) -> dict:
    """Rolling out-of-sample folds. Mirrors /run-walk-forward, on an in-memory df."""
    folds = max(2, min(WF_FOLDS, 12))
    n = len(df)
    size = n // folds
    rois, traded = [], 0
    for k in range(folds):
        start = k * size
        end = n if k == folds - 1 else (k + 1) * size
        window = df.iloc[start:end]
        if len(window) < 30:
            continue
        try:
            m = strategy.run_backtest(window)
        except Exception:
            continue
        if m["totalTrades"] > 0:
            traded += 1
            rois.append(m["roiPercentage"])
    if not rois:
        return {"consistent": False, "pctProfitableFolds": 0.0, "meanOosRoi": 0.0}
    mean, std = float(np.mean(rois)), float(np.std(rois))
    pct_prof = len([r for r in rois if r > 0]) / len(rois) * 100
    return {
        "consistent": bool(mean > 0 and std <= abs(mean)),
        "pctProfitableFolds": round(pct_prof, 2),
        "meanOosRoi": round(mean, 2),
    }


def _monte_carlo(strategy, df) -> dict:
    """Bootstrapped outcome distribution. Mirrors /run-monte-carlo, in-memory."""
    sim = strategy.simulate(df)
    trades = np.array(sim["net_trades"], dtype=float)
    if trades.size < 5:
        return {"p5Roi": None, "probabilityOfProfit": None, "ok": False}
    from backtest_config import RISK
    capital = RISK.slot_capital
    rng = np.random.default_rng(42)
    final_rois = np.empty(MC_ITERS)
    for it in range(MC_ITERS):
        seq = rng.choice(trades, size=trades.size, replace=True)
        equity = capital + np.cumsum(seq)
        final_rois[it] = (equity[-1] - capital) / capital * 100
    return {
        "p5Roi": round(float(np.percentile(final_rois, 5)), 2),
        "probabilityOfProfit": round(float((final_rois > 0).mean() * 100), 2),
        "ok": True,
    }


def _score(roi: float, dd_pct: float, trades: int) -> float:
    """Calmar-like, divide-by-zero safe, shrunk for small samples."""
    calmar = roi / dd_pct if dd_pct > 0.1 else roi
    confidence = min(1.0, trades / float(MIN_TRADES))
    return round(calmar * confidence, 3)


def _upsert_active(conn, stock_id: int, strategy_name: str, timeframe: str):
    conn.execute(text("""
        INSERT INTO "ActiveConfiguration" ("stockId", "strategyName", "timeframe", "createdAt", "updatedAt")
        VALUES (:sid, :sn, :tf, NOW(), NOW())
        ON CONFLICT ("stockId", "strategyName")
        DO UPDATE SET "timeframe" = EXCLUDED."timeframe", "updatedAt" = NOW()
    """), {"sid": stock_id, "sn": strategy_name, "tf": timeframe})


def _save_report(conn, stock_id: int, strategy_name: str, timeframe: str, metrics: dict):
    """Persist a BacktestReport row (mirrors routers.backtest.save_report) so the
    monitor's latest-snapshot lookup finds a current report for each pick."""
    conn.execute(text("""
        INSERT INTO "BacktestReport"
          ("stockId", "strategyName", "timeframe", "winRate", "totalTrades",
           "maxDrawdown", "netProfit", "roiPercentage", "createdAt")
        VALUES (:sid, :sn, :tf, :wr, :tt, :md, :np, :roi, NOW())
    """), {
        "sid": stock_id, "sn": strategy_name, "tf": timeframe,
        "wr": float(metrics["winRate"]), "tt": int(metrics["totalTrades"]),
        "md": float(metrics["maxDrawdown"]), "np": float(metrics["netProfit"]),
        "roi": float(metrics["roiPercentage"]),
    })


@router.post("/auto-select")
def auto_select(req: AutoSelectRequest):
    strategy_names = req.strategies or list(STRATEGY_REGISTRY.keys())
    strategy_names = [s for s in strategy_names if s in STRATEGY_REGISTRY]
    top_n = max(1, min(req.topN, 20))

    with engine.connect() as conn:
        stocks = conn.execute(text('SELECT id, symbol FROM "Stock"')).fetchall()

    summary = []
    all_picks = []  # (stock_id, strategy, timeframe)

    for sname in strategy_names:
        strategy = STRATEGY_REGISTRY[sname]
        timeframe = STRATEGY_TIMEFRAMES.get(sname, getattr(strategy, "timeframe", "1D"))
        candidates, rejections = [], []

        for stock_id, symbol in stocks:
            try:
                df = load_historical(stock_id, timeframe)
            except Exception:
                continue
            if len(df) < MIN_BARS:
                continue

            try:
                m = strategy.run_backtest(df)
            except Exception as e:
                rejections.append({"symbol": symbol, "gate": "backtest-error", "detail": str(e)[:120]})
                continue

            # Gate 1 — in-sample quality
            if m["totalTrades"] < MIN_TRADES:
                rejections.append({"symbol": symbol, "gate": "trades", "value": m["totalTrades"]})
                continue
            if m["roiPercentage"] <= MIN_ROI:
                rejections.append({"symbol": symbol, "gate": "roi", "value": m["roiPercentage"]})
                continue
            if m["profitFactor"] < MIN_PROFIT_FACTOR:
                rejections.append({"symbol": symbol, "gate": "profitFactor", "value": m["profitFactor"]})
                continue
            if m["maxDrawdownPct"] > MAX_DD_PCT:
                rejections.append({"symbol": symbol, "gate": "drawdown", "value": m["maxDrawdownPct"]})
                continue

            # Gate 2 — out-of-sample: mean fold ROI must be positive and enough
            # folds profitable. Optionally also demand the strict low-variance flag.
            wf = _walk_forward(strategy, df)
            wf_ok = wf["meanOosRoi"] > 0 and wf["pctProfitableFolds"] >= MIN_PROFITABLE_FOLDS
            if WF_REQUIRE_CONSISTENT:
                wf_ok = wf_ok and wf["consistent"]
            if not wf_ok:
                rejections.append({"symbol": symbol, "gate": "walk-forward", "value": wf})
                continue

            # Gate 3 — distribution (Monte-Carlo): majority of bootstrapped paths
            # must be profitable (worst-case p5 ROI kept for reporting).
            mc = _monte_carlo(strategy, df)
            if not mc["ok"] or mc["probabilityOfProfit"] is None or mc["probabilityOfProfit"] < MC_MIN_PROB:
                rejections.append({"symbol": symbol, "gate": "monte-carlo", "value": mc})
                continue

            candidates.append({
                "symbol": symbol,
                "stockId": stock_id,
                "score": _score(m["roiPercentage"], m["maxDrawdownPct"], m["totalTrades"]),
                "roiPercentage": m["roiPercentage"],
                "winRate": m["winRate"],
                "profitFactor": m["profitFactor"],
                "maxDrawdownPct": m["maxDrawdownPct"],
                "trades": m["totalTrades"],
                "oosProfitableFolds": wf["pctProfitableFolds"],
                "mcP5Roi": mc["p5Roi"],
                "mcProbProfit": mc["probabilityOfProfit"],
                "_metrics": m,  # full metrics, persisted as a BacktestReport for the pick
            })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        picks = candidates[:top_n]
        for p in picks:
            all_picks.append((p["stockId"], sname, timeframe, p["_metrics"]))

        summary.append({
            "strategy": sname,
            "timeframe": timeframe,
            "evaluated": len(stocks),
            "passedGates": len(candidates),
            "picked": [{k: p[k] for k in (
                "symbol", "score", "roiPercentage", "winRate", "profitFactor",
                "maxDrawdownPct", "trades", "oosProfitableFolds", "mcP5Roi", "mcProbProfit",
            )} for p in picks],
            "rejectedSample": rejections[:8],
        })

    written = 0
    if not req.dryRun:
        with engine.begin() as conn:
            if req.clearExisting:
                conn.execute(text('DELETE FROM "ActiveConfiguration"'))
            for stock_id, sname, timeframe, metrics in all_picks:
                _upsert_active(conn, stock_id, sname, timeframe)
                # Persist a fresh BacktestReport so the monitor shows numbers
                # immediately instead of "no backtest — Re-run".
                _save_report(conn, stock_id, sname, timeframe, metrics)
                written += 1

    return {
        "strategiesEvaluated": len(strategy_names),
        "totalPicks": len(all_picks),
        "written": written,
        "dryRun": req.dryRun,
        "clearedExisting": req.clearExisting and not req.dryRun,
        "gates": {
            "minTrades": MIN_TRADES,
            "minRoiPct": MIN_ROI,
            "minProfitFactor": MIN_PROFIT_FACTOR,
            "maxDrawdownPct": MAX_DD_PCT,
            "minProfitableFoldsPct": MIN_PROFITABLE_FOLDS,
            "walkForwardRequireConsistent": WF_REQUIRE_CONSISTENT,
            "monteCarloMinProbProfitPct": MC_MIN_PROB,
            "topNPerStrategy": top_n,
        },
        "summary": summary,
        "disclaimer": (
            "Picks passed in-sample quality (positive ROI, profit factor, drawdown "
            "cap) + positive out-of-sample walk-forward ROI + a majority-profitable "
            "Monte-Carlo distribution. This stacks the odds but is not a guarantee — "
            "past performance does not assure future returns."
        ),
    }
