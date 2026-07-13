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
       "maxDrawdown", "netProfit", "roiPercentage", "engineVersion",
       "createdAt", "updatedAt")
    VALUES (:sid, :sn, :tf, :wr, :tt, :md, :np, :roi, :ev, NOW(), NOW())
    ON CONFLICT ("stockId", "strategyName", "timeframe") DO UPDATE SET
      "winRate"       = EXCLUDED."winRate",
      "totalTrades"   = EXCLUDED."totalTrades",
      "maxDrawdown"   = EXCLUDED."maxDrawdown",
      "netProfit"     = EXCLUDED."netProfit",
      "roiPercentage" = EXCLUDED."roiPercentage",
      "engineVersion" = EXCLUDED."engineVersion",
      "updatedAt"     = NOW()
""")


def save_report(conn, stock_id: int, strategy_name: str, timeframe: str, metrics: dict) -> None:
    """UPSERT the latest backtest metrics for one cell, stamped ENGINE_VERSION."""
    conn.execute(_UPSERT, {
        "sid": stock_id,
        "sn": strategy_name,
        "tf": timeframe,
        "wr": float(metrics["winRate"]),
        "tt": int(metrics["totalTrades"]),
        "md": float(metrics["maxDrawdown"]),
        "np": float(metrics["netProfit"]),
        "roi": float(metrics["roiPercentage"]),
        "ev": ENGINE_VERSION,
    })
