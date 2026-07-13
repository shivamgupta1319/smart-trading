"""Integration test for the BacktestReport UPSERT writer (FEAT-001 Phase 1).

DB-gated: skips unless the engine's Postgres is reachable (i.e. runs inside the
engine container / CI with DATABASE_URL, self-skips on a dev box with no DB).
Uses a sentinel (stock × strategy × timeframe) cell and cleans it up.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from sqlalchemy import text
    from db.client import engine
    from reports import save_report
    from backtest_config import ENGINE_VERSION
    with engine.connect() as _c:
        _STOCK_ID = _c.execute(text('SELECT id FROM "Stock" LIMIT 1')).scalar()
    _DB_OK = _STOCK_ID is not None
except Exception:  # no DB / no Stock rows → skip the whole module
    _DB_OK = False

pytestmark = pytest.mark.skipif(not _DB_OK, reason="engine Postgres not reachable")

SENTINEL = "__UPSERT_TEST__"
TF = "1D"


def _fetch(conn):
    return conn.execute(text("""
        SELECT "netProfit", "totalTrades", "engineVersion", "createdAt", "updatedAt"
        FROM "BacktestReport"
        WHERE "stockId" = :sid AND "strategyName" = :sn AND "timeframe" = :tf
    """), {"sid": _STOCK_ID, "sn": SENTINEL, "tf": TF}).fetchall()


def _metrics(net, trades):
    return {"winRate": 50.0, "totalTrades": trades, "maxDrawdown": 10.0,
            "netProfit": net, "roiPercentage": net / 100.0}


def test_upsert_keeps_one_row_with_latest_metrics():
    try:
        with engine.begin() as conn:
            conn.execute(text('DELETE FROM "BacktestReport" WHERE "strategyName" = :sn'),
                         {"sn": SENTINEL})
            save_report(conn, _STOCK_ID, SENTINEL, TF, _metrics(111.0, 5))
        with engine.begin() as conn:
            save_report(conn, _STOCK_ID, SENTINEL, TF, _metrics(222.0, 9))

        with engine.connect() as conn:
            rows = _fetch(conn)
        assert len(rows) == 1, f"expected 1 row after two writes, got {len(rows)}"
        r = rows[0]
        assert float(r[0]) == 222.0, "netProfit should be the latest write"
        assert int(r[1]) == 9, "totalTrades should be the latest write"
        assert r[2] == ENGINE_VERSION, "engineVersion must be stamped"
        assert r[4] >= r[3], "updatedAt must be >= createdAt"
    finally:
        with engine.begin() as conn:
            conn.execute(text('DELETE FROM "BacktestReport" WHERE "strategyName" = :sn'),
                         {"sn": SENTINEL})
