"""Auto-select: put every cell whose backtest meets the live rule on the roster.

For every strategy and every stock with data it runs the backtest and asks
`selection_rule.py`, the one rule that decides whether a backtest is good enough to go
live. Every cell that passes is written into `ActiveConfiguration` (the table the live
scanner reads), the same place the Set Live button writes to.

By default it APPENDS: cells already on the roster are left alone. Pass
clearExisting=true to empty the roster first.

A run takes a few minutes, so it runs in the background: POST starts it, GET
/auto-select/status reports on it.
"""
import os
import threading
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from db.client import engine
from strategies import STRATEGY_REGISTRY, STRATEGY_TIMEFRAMES, STRATEGY_HOLD_DURATIONS
import selection_rule
from routers.backtest import load_historical
from routers.history import fetch_and_store
from reports import save_report as _save_report  # shared UPSERT writer (one row per cell)


router = APIRouter()


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# Sample size at which a cell's score counts in full (ranking only; the rule decides).
MIN_TRADES = int(_f("AUTOSELECT_MIN_TRADES", 10))
MIN_BARS = int(_f("AUTOSELECT_MIN_BARS", 60))
# Persistent denylist so manually-pruned losers are NOT re-promoted every run.
# Comma-separated entries; each matches either a whole strategy ("Fibonacci_Golden_Zone")
# or a specific cell ("BSE|15m_ORB"). Env: AUTOSELECT_DENYLIST.
DENYLIST = {e.strip() for e in os.getenv("AUTOSELECT_DENYLIST", "").split(",") if e.strip()}


class AutoSelectRequest(BaseModel):
    strategies: list[str] | None = None  # default: all
    # Append by default: keep the existing active configs, add only the new
    # picks, and skip any (stock × strategy) cell already active. Set true to
    # wipe ActiveConfiguration first (old "replace" behavior).
    clearExisting: bool = False
    # Pull the latest candles before backtesting: full history for stocks with no
    # data yet (e.g. just added on the dashboard), incremental top-up for the rest.
    refreshData: bool = True
    dryRun: bool = False                 # compute but don't write
    # Wait for the result in this request. Off by default: a run takes several
    # minutes and the public address cuts a request off after 120 seconds, so the
    # run starts in the background and GET /auto-select/status reports on it.
    wait: bool = False


def _score(avg_r: float, dd_pct: float, trades: int) -> float:
    """Rank by NET avg R-multiple (risk-adjusted edge), shrunk for small samples
    and lightly penalized for drawdown. R-multiple — unlike ROI — is independent
    of compounding and backtest horizon, so it compares cells on real edge, not
    on which lucky curve compounded hardest. Env: AUTOSELECT_DD_PENALTY."""
    confidence = min(1.0, trades / float(MIN_TRADES))
    dd_penalty = 1.0 / (1.0 + max(dd_pct, 0.0) / 100.0)  # 0%DD→1.0, 25%DD→0.8, 50%DD→0.67
    return round(avg_r * confidence * dd_penalty, 3)


def _upsert_active(conn, stock_id: int, strategy_name: str, timeframe: str):
    conn.execute(text("""
        INSERT INTO "ActiveConfiguration" ("stockId", "strategyName", "timeframe", "createdAt", "updatedAt")
        VALUES (:sid, :sn, :tf, NOW(), NOW())
        ON CONFLICT ("stockId", "strategyName")
        DO UPDATE SET "timeframe" = EXCLUDED."timeframe", "updatedAt" = NOW()
    """), {"sid": stock_id, "sn": strategy_name, "tf": timeframe})


# One run at a time, kept in memory (the engine is a single process). `_job` is what
# GET /auto-select/status returns.
_job_lock = threading.Lock()
_job: dict = {"status": "idle"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _progress(stage: str, done: int, total: int) -> None:
    _job.update({"stage": stage, "done": done, "total": total})


def _run_job(req: AutoSelectRequest) -> None:
    try:
        result = run_auto_select(req, _progress)
        _job.update({"status": "done", "finishedAt": _now(), "result": result, "error": None})
    except Exception as exc:  # the run must never leave the job stuck on "running"
        _job.update({"status": "failed", "finishedAt": _now(), "error": f"{type(exc).__name__}: {exc}"[:300]})
    finally:
        _job_lock.release()


@router.get("/auto-select/status")
def auto_select_status():
    """Where the current or the last run stands: idle, running (with a stage and a
    count), done (with the result) or failed (with the reason)."""
    return dict(_job)


@router.post("/auto-select")
def auto_select(req: AutoSelectRequest):
    """Start a run. Returns at once with the job; poll GET /auto-select/status.
    A second call while one is running returns that run instead of starting another."""
    if not _job_lock.acquire(blocking=False):
        return dict(_job)
    _job.clear()
    _job.update({"status": "running", "startedAt": _now(), "stage": "Starting", "done": 0, "total": 0,
                 "dryRun": req.dryRun, "result": None, "error": None})
    if req.wait:
        _run_job(req)
        return dict(_job)
    threading.Thread(target=_run_job, args=(req,), daemon=True, name="auto-select").start()
    return dict(_job)


def run_auto_select(req: AutoSelectRequest, progress=lambda stage, done, total: None) -> dict:
    strategy_names = req.strategies or list(STRATEGY_REGISTRY.keys())
    strategy_names = [s for s in strategy_names if s in STRATEGY_REGISTRY]

    import universe
    with engine.connect() as conn:
        listed = universe.active_stocks(conn)          # (id, symbol, on the intraday list)
    stocks = [(sid, symbol) for sid, symbol, _on in listed]
    intraday_list = {symbol for _sid, symbol, on in listed if on}

    # Refresh data first so backtests run on the latest candles. Only the
    # timeframes the selected strategies actually use are pulled. New stocks
    # (no stored data) get a full download; existing ones a quick incremental
    # top-up. A per-stock fetch failure must not abort the whole run.
    refreshed = 0
    if req.refreshData and not req.dryRun:
        timeframes_needed = sorted({
            STRATEGY_TIMEFRAMES.get(s, getattr(STRATEGY_REGISTRY[s], "timeframe", "1D"))
            for s in strategy_names
        })
        for n, (_sid, symbol) in enumerate(stocks):
            progress("Getting the latest prices", n, len(stocks))
            try:
                fetch_and_store(symbol, universe.timeframes_for(symbol in intraday_list, timeframes_needed))
                refreshed += 1
            except Exception:
                continue

    summary = []
    all_picks = []  # (stock_id, strategy, timeframe)
    try:
        lucky = selection_rule.strategies_passing_luck()   # None: no luck check stored yet
    except Exception:
        lucky = None
    rules = selection_rule.selection_rules()

    for k, sname in enumerate(strategy_names):
        progress("Testing strategies", k, len(strategy_names))
        # Denylisted strategy — never re-promote (persists manual prunes).
        if sname in DENYLIST:
            summary.append({"strategy": sname, "skipped": "denylisted"})
            continue
        strategy = STRATEGY_REGISTRY[sname]
        timeframe = STRATEGY_TIMEFRAMES.get(sname, getattr(strategy, "timeframe", "1D"))
        bucket = STRATEGY_HOLD_DURATIONS.get(sname)
        passes_luck = None if lucky is None else sname in lucky
        candidates, rejections = [], []

        for stock_id, symbol in stocks:
            if timeframe != "1D" and symbol not in intraday_list:
                continue  # intraday strategies run on the intraday list only
            if f"{symbol}|{sname}" in DENYLIST:
                continue  # denylisted cell
            try:
                df = load_historical(stock_id, timeframe)
            except Exception:
                continue
            # Drop the trailing bar: during market hours it's a still-forming candle
            # that a pre-backtest refresh mutates, so leaving it in makes repeat
            # auto-select runs non-deterministic (different picks each run). Dropping
            # one completed bar off a long history costs nothing.
            if len(df) > MIN_BARS:
                df = df.iloc[:-1]
            if len(df) < MIN_BARS:
                continue

            try:
                m = strategy.run_backtest(df)
            except Exception as e:
                rejections.append({"symbol": symbol, "gate": "backtest-error", "detail": str(e)[:120]})
                continue

            # The one live rule (selection_rule.py): the same checks the roster and the
            # Set Live warning use. It replaced this endpoint's own gates on 2026-11-23,
            # which let through cells the roster rule refused, and the other way round.
            missed = selection_rule.misses(m, bucket, passes_luck)
            if missed:
                rejections.append({"symbol": symbol, "gate": "live rule", "detail": "; ".join(missed)})
                continue

            candidates.append({
                "symbol": symbol,
                "stockId": stock_id,
                "score": _score(m.get("avgRMultiple", 0.0), m["maxDrawdownPct"], m["totalTrades"]),
                "avgRMultiple": m.get("avgRMultiple", 0.0),
                "roiPercentage": m["roiPercentage"],
                "winRate": m["winRate"],
                "profitFactor": m["profitFactor"],
                "maxDrawdownPct": m["maxDrawdownPct"],
                "returnDdRatio": round(m["roiPercentage"] / max(m["maxDrawdownPct"], 0.5), 2),
                "trades": m["totalTrades"],
                "_metrics": m,  # full metrics, persisted as a BacktestReport for the pick
            })

        # Every cell that meets the rule is picked: the rule is the filter, not a
        # "best three per strategy" cut.
        candidates.sort(key=lambda x: x["score"], reverse=True)
        picks = candidates
        for p in picks:
            all_picks.append((p["stockId"], sname, timeframe, p["_metrics"]))

        summary.append({
            "strategy": sname,
            "timeframe": timeframe,
            "evaluated": len(stocks),
            "passedGates": len(candidates),
            "picked": [{k: p[k] for k in (
                "symbol", "score", "avgRMultiple", "roiPercentage", "winRate", "profitFactor",
                "maxDrawdownPct", "returnDdRatio", "trades",
            )} for p in picks],
            "rejectedSample": rejections[:8],
        })

    progress("Saving the picks", len(strategy_names), len(strategy_names))
    written = 0
    skipped = 0
    if not req.dryRun:
        with engine.begin() as conn:
            if req.clearExisting:
                conn.execute(text('DELETE FROM "ActiveConfiguration"'))
                existing = set()
            else:
                # Append mode: remember the (stock × strategy) cells already
                # active so we keep them untouched and only add genuinely new ones.
                rows = conn.execute(
                    text('SELECT "stockId", "strategyName" FROM "ActiveConfiguration"')
                ).fetchall()
                existing = {(r[0], r[1]) for r in rows}
            for stock_id, sname, timeframe, metrics in all_picks:
                if (stock_id, sname) in existing:
                    skipped += 1  # already active — leave the old config in place
                    continue
                _upsert_active(conn, stock_id, sname, timeframe)
                # Persist a fresh BacktestReport so the monitor shows numbers
                # immediately instead of "no backtest — Re-run".
                _save_report(conn, stock_id, sname, timeframe, metrics)
                existing.add((stock_id, sname))
                written += 1

    return {
        "strategiesEvaluated": len(strategy_names),
        "totalPicks": len(all_picks),
        "stocksRefreshed": refreshed,  # stocks whose candles were pulled before backtesting
        "written": written,
        "skipped": skipped,  # picks already active, left untouched
        "dryRun": req.dryRun,
        "clearedExisting": req.clearExisting and not req.dryRun,
        "rule": {
            "minAvgR": rules.min_avg_r,
            "minTradesIntraday": rules.min_trades_intraday,
            "minTradesSwing": rules.min_trades_swing,
            "minProfitFactor": rules.min_profit_factor,
            "minProfitToDrawdown": rules.min_profit_to_drawdown,
            "minRoiPct": rules.min_roi_pct,
            "bothHalvesPositive": True,
            "swingStrategyMustPassLuckTest": lucky is not None,
        },
        "summary": summary,
        "disclaimer": (
            "Every pick meets the live rule on its backtest after costs. That earns a place "
            "on the roster; only the cell's own paper trades keep it there."
        ),
    }
