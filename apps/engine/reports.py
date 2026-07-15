"""Single writer for BacktestReport rows.

UPSERTs exactly one row per (stock × strategy × timeframe) — no more append-only
duplicates — and stamps the engine version so stale-version numbers are
identifiable. Imported by BOTH routers.backtest and routers.auto_select so the
two never drift (they used to carry near-identical INSERT copies).

Takes an open SQLAlchemy `conn` and does NOT commit — the caller owns the
transaction (auto_select batches many writes in one; backtest wraps a single
write). Requires the unique key BacktestReport_stockId_strategyName_timeframe_key
(see prisma migration 20260713200000_backtest_report_upsert).
"""
from sqlalchemy import text

from backtest_config import ENGINE_VERSION

_UPSERT = text("""
    INSERT INTO "BacktestReport"
      ("stockId", "strategyName", "timeframe", "winRate", "totalTrades",
       "maxDrawdown", "netProfit", "roiPercentage", "avgRMultiple", "profitFactor",
       "maxDrawdownPct", "expectancy", "spanYears", "engineVersion",
       "createdAt", "updatedAt")
    VALUES (:sid, :sn, :tf, :wr, :tt, :md, :np, :roi, :ar, :pf, :mdp, :ex, :sy, :ev,
            NOW(), NOW())
    ON CONFLICT ("stockId", "strategyName", "timeframe") DO UPDATE SET
      "winRate"        = EXCLUDED."winRate",
      "totalTrades"    = EXCLUDED."totalTrades",
      "maxDrawdown"    = EXCLUDED."maxDrawdown",
      "netProfit"      = EXCLUDED."netProfit",
      "roiPercentage"  = EXCLUDED."roiPercentage",
      "avgRMultiple"   = EXCLUDED."avgRMultiple",
      "profitFactor"   = EXCLUDED."profitFactor",
      "maxDrawdownPct" = EXCLUDED."maxDrawdownPct",
      "expectancy"     = EXCLUDED."expectancy",
      "spanYears"      = EXCLUDED."spanYears",
      "engineVersion"  = EXCLUDED."engineVersion",
      "updatedAt"      = NOW()
""")


def _f(metrics: dict, key: str):
    """Optional float — None (not 0.0) when a writer didn't supply the metric, so the
    column reads as "not computed" rather than asserting a zero edge / zero drawdown."""
    v = metrics.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def save_report(conn, stock_id: int, strategy_name: str, timeframe: str, metrics: dict) -> None:
    """UPSERT the latest backtest metrics for one cell, stamped ENGINE_VERSION.

    Persists the EDGE metrics too (avgRMultiple/profitFactor/maxDrawdownPct/expectancy
    + spanYears). They were computed and dropped before — leaving roiPercentage, which
    is raw-cumulative and window-dependent, as the only thing the UI and leaderboard
    could rank on (audit 2026-07-15 F3).
    """
    conn.execute(_UPSERT, {
        "sid": stock_id,
        "sn": strategy_name,
        "tf": timeframe,
        "wr": float(metrics["winRate"]),
        "tt": int(metrics["totalTrades"]),
        "md": float(metrics["maxDrawdown"]),
        "np": float(metrics["netProfit"]),
        "roi": float(metrics["roiPercentage"]),
        "ar": _f(metrics, "avgRMultiple"),
        "pf": _f(metrics, "profitFactor"),
        "mdp": _f(metrics, "maxDrawdownPct"),
        "ex": _f(metrics, "expectancy"),
        "sy": _f(metrics, "spanYears"),
        "ev": ENGINE_VERSION,
    })
