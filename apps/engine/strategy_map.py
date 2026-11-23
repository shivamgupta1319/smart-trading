"""Where each strategy works: across most stocks, on particular stocks, or nowhere.

Built from the stored backtest of every cell (refreshed by the daily luck check) and the
live rule. For each strategy:
  tested      stocks where it took at least one trade
  profitable  of those, how many have a positive average after costs
  meets       the stocks whose backtest meets the live rule (selection_rule.py)
and a verdict in plain words:
  "Works broadly"            passes the luck check and is profitable on most stocks tested
  "Works on some stocks"     at least one stock meets the live rule, but it is not broad
  "No stock meets the rule"  nothing to put live
The same rows, turned round, say which strategies suit a particular stock.
"""
from __future__ import annotations

from statistics import median

from sqlalchemy import text

from db.client import engine
import selection_rule
from strategies import STRATEGY_HOLD_DURATIONS, STRATEGY_REGISTRY

BROAD_SHARE = 0.60   # profitable on at least this share of the stocks tested


def classify(tested: int, profitable: int, meets: int, passes_luck: bool | None) -> str:
    if meets == 0:
        return "No stock meets the rule"
    broad = tested > 0 and profitable / tested >= BROAD_SHARE
    if broad and passes_luck is not False:
        return "Works broadly"
    return "Works on some stocks"


def build(rows: list[dict], lucky: set[str] | None) -> list[dict]:
    """rows: one stored backtest per cell {symbol, strategy, + the metrics the rule reads}."""
    by_strategy: dict[str, list[dict]] = {name: [] for name in STRATEGY_REGISTRY}
    for r in rows:
        if r["strategy"] in by_strategy:
            by_strategy[r["strategy"]].append(r)
    out = []
    for name, cells in by_strategy.items():
        bucket = STRATEGY_HOLD_DURATIONS.get(name)
        passes_luck = None if lucky is None else name in lucky
        traded = [c for c in cells if (c.get("totalTrades") or 0) > 0]
        profitable = [c for c in traded if (c.get("avgRMultiple") or 0) > 0]
        meets = [c for c in traded if not selection_rule.misses(c, bucket, passes_luck)]
        meets.sort(key=lambda c: -(c["netProfit"] / max(c.get("maxDrawdown") or 0, 1.0)))
        out.append({
            "strategy": name,
            "bucket": bucket,
            "tested": len(traded),
            "profitable": len(profitable),
            "medianAvgR": round(median(c["avgRMultiple"] or 0 for c in traded), 2) if traded else None,
            "passesLuck": passes_luck,
            "meets": [{"symbol": c["symbol"], "avgR": c["avgRMultiple"], "trades": c["totalTrades"],
                       "roiPct": c["roiPercentage"]} for c in meets],
            "verdict": classify(len(traded), len(profitable), len(meets), passes_luck),
        })
    order = {"Works broadly": 0, "Works on some stocks": 1, "No stock meets the rule": 2}
    return sorted(out, key=lambda s: (order[s["verdict"]], -len(s["meets"]), s["strategy"]))


def latest() -> dict:
    with engine.connect() as conn:
        found = conn.execute(text("""
            SELECT s.symbol, br."strategyName", br."totalTrades", br."avgRMultiple", br."rFirstHalf",
                   br."rSecondHalf", br."profitFactor", br."netProfit", br."maxDrawdown",
                   br."roiPercentage", br."updatedAt"
            FROM "BacktestReport" br JOIN "Stock" s ON s.id = br."stockId"
            WHERE s."isActive"
        """)).fetchall()
        stocks = conn.execute(text('SELECT count(*), count(*) FILTER (WHERE intraday) FROM "Stock" WHERE "isActive"')).fetchone()
    rows = [{"symbol": r[0], "strategy": r[1], "totalTrades": r[2], "avgRMultiple": r[3], "rFirstHalf": r[4],
             "rSecondHalf": r[5], "profitFactor": r[6], "netProfit": r[7], "maxDrawdown": r[8],
             "roiPercentage": r[9]} for r in found]
    try:
        lucky = selection_rule.strategies_passing_luck()
    except Exception:
        lucky = None
    updated = max((r[10] for r in found), default=None)
    return {
        "stocks": stocks[0],
        "intradayStocks": stocks[1],
        "updatedAt": updated.isoformat() + "Z" if updated else None,
        "broadShare": BROAD_SHARE,
        "strategies": build(rows, lucky),
    }
